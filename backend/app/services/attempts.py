"""API-1 提交编排：固定判定顺序、单事务落库、拒绝标记提交与安全日志。

顺序（开发文档 2.6.2，不可交换）：认证(401)/角色(403)/Header 与 body schema
由路由层完成；本服务从请求指纹开始：

    指纹 → 键锁 → 5a/5b/5c 短路 → 6a 答案结构 → **6b 准入** → 6b2 完整性
    → 6c 身份/版本（版本优先）→ 6d 限次 → 判分 → 单事务写 attempts+answers
    → 一次 commit → 200

拒绝标记必须先 commit 成功再抛业务错误；成功记录与永久标记不得同键并存
（键级事务锁 + 唯一约束 + 本顺序保证）。数据库异常按 2.6.4 结束失败事务、
新事务取键锁重读；按 2.7.3 只记录安全字段，最终转换 ``AppError``，不把原始
SQL/异常链交给全局异常处理器。
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, bad_request, not_found
from app.db.models_attempt import Attempt, AttemptAnswer
from app.repositories.attempt_content import (
    IdentityStatus,
    PaperUnavailable,
    check_paper_integrity,
    check_submit_access,
    classify_loaded_ids,
    load_current_paper_questions,
    validate_answers,
)
from app.repositories.attempt_keys import (
    REJECTION_KIND_CONTENT_VERSION_MISMATCH,
    REJECTION_KIND_PAPER_NOT_ACCESSIBLE,
    ResolveStatus,
    build_request_fingerprint,
    count_success_attempts,
    insert_attempt_with_answers,
    insert_rejection,
    lock_attempt_key,
    lock_student_paper,
    resolve_existing,
)
from app.schemas_attempts import (
    MSG_E03_PAPER_NOT_ACCESSIBLE,
    MSG_E04_CONTENT_VERSION_MISMATCH,
    MSG_E08_ATTEMPT_LIMIT,
    MSG_E09_KEY_REUSED,
    AttemptSubmitData,
    AttemptSubmitIn,
    PracticeScoreData,
    msg_e07,
)
from app.services.grading import (
    AnswerInput,
    GradingDataError,
    QuestionSnapshotInput,
    grade,
)

logger = logging.getLogger(__name__)

MSG_INTERNAL = "服务器内部错误"

# P1 未生效时的同卷限次（BR-18a；D11 默认 A 草稿口径，待拍板）。
ATTEMPT_LIMIT_PER_PAPER = 1

_ANSWER_REASON_TEXT = {
    "duplicate_loaded_question_id": "题目身份重复",
    "duplicate_answer_question_id": "答案题目重复",
    "answer_not_in_loaded_set": "答案包含整卷集合之外的题目",
    "answer_not_in_current_batch": "答案包含非当前批次的题目",
}

_ALLOWED_PRACTICE_REASONS = {
    "not_standard_25",
    "question_type_missing",
    "unknown_type",
    "type_count_mismatch",
}


# --------------------------------------------------------------------------- #
# 安全日志与错误辅助（2.7.3：只记录白名单字段，不记录请求体/答案/解析/正文/完整键）
# --------------------------------------------------------------------------- #
def _sqlstate(error: BaseException) -> str | None:
    orig = getattr(error, "orig", None)
    for candidate in (orig, error):
        for attr in ("sqlstate", "pgcode"):
            value = getattr(candidate, attr, None)
            if value:
                return str(value)
    return None


def _safe_log(
    stage: str,
    *,
    student_id: int | None = None,
    exam_paper_id: int | None = None,
    attempt_code: str | None = None,
    error: BaseException | None = None,
    reason: str | None = None,
) -> None:
    parts = [f"stage={stage}"]
    if student_id is not None:
        parts.append(f"student_id={student_id}")
    if exam_paper_id is not None:
        parts.append(f"exam_paper_id={exam_paper_id}")
    if attempt_code is not None:
        parts.append(f"attempt_code={attempt_code}")
    if error is not None:
        parts.append(f"error_type={type(error).__name__}")
        sqlstate = _sqlstate(error)
        if sqlstate:
            parts.append(f"sqlstate={sqlstate}")
    if reason is not None:
        parts.append(f"reason={reason}")
    logger.warning("attempt submit failure %s", " ".join(parts))


def _rejection_error(rejection) -> AppError:
    if rejection.rejection_kind == REJECTION_KIND_CONTENT_VERSION_MISMATCH:
        return bad_request(MSG_E04_CONTENT_VERSION_MISMATCH)
    return not_found(MSG_E03_PAPER_NOT_ACCESSIBLE)


def _known_practice_reason(value: object) -> str | None:
    return value if value in _ALLOWED_PRACTICE_REASONS else None


def _data_from_attempt(attempt: Attempt) -> AttemptSubmitData:
    """短路回放：只从已持久化的 attempt 汇总字段重建响应（不重新判分）。"""

    breakdown = attempt.score_breakdown or {}
    available = bool(breakdown.get("available"))
    reason = None if available else _known_practice_reason(breakdown.get("reason"))
    return AttemptSubmitData(
        attempt_code=attempt.attempt_code,
        exam_paper_id=attempt.exam_paper_id,
        submitted_at=attempt.submitted_at,
        question_count=attempt.question_count,
        correct_count=attempt.correct_count,
        correct_rate=attempt.correct_rate,
        practice_score=PracticeScoreData(
            available=available,
            value=attempt.practice_score if available else None,
            reason=reason,
        ),
    )


def _data_from_result(result, attempt: Attempt) -> AttemptSubmitData:
    practice = result.practice_score
    return AttemptSubmitData(
        attempt_code=attempt.attempt_code,
        exam_paper_id=attempt.exam_paper_id,
        submitted_at=attempt.submitted_at,
        question_count=result.question_count,
        correct_count=result.correct_count,
        correct_rate=result.correct_rate,
        practice_score=PracticeScoreData(
            available=practice.available,
            value=practice.value,
            max=practice.max,
            label=practice.label,
            reason=practice.reason,
        ),
    )


# --------------------------------------------------------------------------- #
# 拒绝标记：先 commit 成功，再由调用方抛业务错误
# --------------------------------------------------------------------------- #
def _persist_rejection(
    db: Session,
    *,
    student_id: int,
    exam_paper_id: int,
    attempt_key: str,
    fingerprint: str,
    rejection_kind: str,
    detail: dict | None = None,
) -> None:
    insert_rejection(
        db,
        student_id=student_id,
        exam_paper_id=exam_paper_id,
        attempt_key=attempt_key,
        request_fingerprint=fingerprint,
        rejection_kind=rejection_kind,
        detail=detail,
    )
    db.commit()


# --------------------------------------------------------------------------- #
# 首次提交（已持有键锁）：6a → 6b → 6b2 → 6c → 6d → 判分 → 单事务写入
# --------------------------------------------------------------------------- #
def _first_submit(
    db: Session,
    *,
    student_id: int,
    exam_paper_id: int,
    attempt_key: str,
    fingerprint: str,
    payload: AttemptSubmitIn,
    settings: Settings,
) -> AttemptSubmitData:
    # 6a 前置判空：整卷题目集合为空直接 400 E07，先于准入，不写永久标记。
    if not payload.loaded_question_ids:
        raise bad_request(msg_e07("整卷题目集合不能为空"))

    # 6a 答案结构（重复/集合外；此时尚未准入，current 用 loaded 自校验）
    validation = validate_answers(
        list(payload.loaded_question_ids),
        list(payload.loaded_question_ids),
        list(payload.answers),
    )
    if not validation.ok:
        raise bad_request(
            msg_e07(_ANSWER_REASON_TEXT.get(validation.reason, "请求内容不合法"))
        )

    # 6b 准入（先于身份分类；失败写 paper_not_accessible 标记并 commit）
    visible, paper, batch = check_submit_access(db, exam_paper_id)
    if not visible or paper is None or batch is None:
        _persist_rejection(
            db,
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            fingerprint=fingerprint,
            rejection_kind=REJECTION_KIND_PAPER_NOT_ACCESSIBLE,
        )
        raise not_found(MSG_E03_PAPER_NOT_ACCESSIBLE)

    # 6b2 数据/音频完整性（E14：404 且不写永久标记）
    try:
        check_paper_integrity(db, paper, batch, settings)
    except PaperUnavailable as exc:
        _safe_log(
            "paper_integrity",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            reason=exc.reason,
        )
        raise not_found(MSG_E03_PAPER_NOT_ACCESSIBLE) from None

    # 6c 身份/版本：固定使用 6b 返回的 batch_id
    try:
        questions = load_current_paper_questions(db, paper.id, batch.id)
    except PaperUnavailable as exc:
        _safe_log(
            "paper_integrity",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            reason=exc.reason,
        )
        raise not_found(MSG_E03_PAPER_NOT_ACCESSIBLE) from None

    current_ids = [item.question_id for item in questions]
    identity = classify_loaded_ids(
        db,
        paper.id,
        current_ids,
        list(payload.loaded_question_ids),
        batch_id=batch.id,
    )
    if identity.status is IdentityStatus.VERSION_MISMATCH:
        _persist_rejection(
            db,
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            fingerprint=fingerprint,
            rejection_kind=REJECTION_KIND_CONTENT_VERSION_MISMATCH,
            detail={"old_batch_question_ids": list(identity.old_batch_ids)},
        )
        raise bad_request(MSG_E04_CONTENT_VERSION_MISMATCH)
    if identity.status is IdentityStatus.INVALID_IDENTITY:
        raise bad_request(msg_e07(_ANSWER_REASON_TEXT["answer_not_in_current_batch"]))
    if identity.status is IdentityStatus.INCOMPLETE:
        raise bad_request(msg_e07("整卷题目集合不完整"))

    # 6d 限次（同事务内：先锁“学生+试卷”，再计数）
    lock_student_paper(db, student_id, exam_paper_id)
    if count_success_attempts(db, student_id, exam_paper_id) >= ATTEMPT_LIMIT_PER_PAPER:
        raise bad_request(MSG_E08_ATTEMPT_LIMIT)

    # 判分 + 单事务写入（flush 不构成提交，唯一一次 commit 在下面）
    snapshot_inputs = [
        QuestionSnapshotInput(
            question_no=item.question_no,
            question_id=item.question_id,
            passage_type=item.passage_type,
            question_text=item.question_text,
            options=item.options,
            correct_paper_letter=item.correct_paper_letter,
            explanation_text=item.explanation_text,
        )
        for item in questions
    ]
    answer_inputs = [
        AnswerInput(
            question_id=answer.question_id,
            selected_option=answer.selected_option,
        )
        for answer in payload.answers
    ]
    result = grade(snapshot_inputs, answer_inputs)

    attempt = Attempt(
        attempt_code=str(uuid4()),
        student_id=student_id,
        exam_paper_id=paper.id,
        import_batch_id=batch.id,
        attempt_key=attempt_key,
        request_fingerprint=fingerprint,
        submitted_at=datetime.now(UTC),
        question_count=result.question_count,
        correct_count=result.correct_count,
        correct_rate=result.correct_rate,
        practice_score=result.practice_score.value,
        score_breakdown=result.practice_score.score_breakdown,
    )
    answer_rows = [
        AttemptAnswer(
            question_no=draft.question_no,
            question_id=draft.question_id,
            passage_type=draft.passage_type,
            question_text=draft.question_text,
            option_a=draft.option_a,
            option_b=draft.option_b,
            option_c=draft.option_c,
            option_d=draft.option_d,
            correct_option=draft.correct_option,
            selected_option=draft.selected_option,
            is_correct=draft.is_correct,
            explanation_text=draft.explanation_text,
        )
        for draft in result.answer_drafts
    ]
    insert_attempt_with_answers(db, attempt, answer_rows)
    db.commit()
    return _data_from_result(result, attempt)


# --------------------------------------------------------------------------- #
# 事务失败恢复（2.6.4）：结束失败事务 → 新事务取键锁 → 重读两表
# --------------------------------------------------------------------------- #
def _recover(
    db: Session,
    *,
    student_id: int,
    exam_paper_id: int,
    attempt_key: str,
    fingerprint: str,
    payload: AttemptSubmitIn,
    settings: Settings,
    allow_retry: bool,
    stage: str,
    error: BaseException,
) -> AttemptSubmitData:
    _safe_log(
        f"{stage}_failure",
        student_id=student_id,
        exam_paper_id=exam_paper_id,
        error=error,
    )
    try:
        db.rollback()
    except Exception as rollback_error:  # noqa: BLE001 - 安全记录状态，不掩盖 COMMIT 未知
        _safe_log(
            f"{stage}_rollback_failure",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            error=rollback_error,
        )

    try:
        lock_attempt_key(db, student_id, attempt_key)
        outcome = resolve_existing(db, student_id, attempt_key, fingerprint)
        if outcome.status is ResolveStatus.REPLAY_SUCCESS:
            return _data_from_attempt(outcome.attempt)
        if outcome.status is ResolveStatus.REJECTED:
            raise _rejection_error(outcome.rejection)
        if outcome.status is ResolveStatus.KEY_CONFLICT:
            raise bad_request(MSG_E09_KEY_REUSED)
    except AppError:
        raise
    except SQLAlchemyError as read_error:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001 - 重读失败只记录安全状态
            pass
        _safe_log(
            f"{stage}_reread_failure",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            error=read_error,
        )
        raise AppError(500, MSG_INTERNAL) from None

    if allow_retry:
        _safe_log(
            f"{stage}_retry",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
        )
        return _run_submission(
            db,
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            fingerprint=fingerprint,
            payload=payload,
            settings=settings,
            allow_retry=False,
        )

    _safe_log(
        f"{stage}_unresolved",
        student_id=student_id,
        exam_paper_id=exam_paper_id,
    )
    raise AppError(500, MSG_INTERNAL) from None


def _run_submission(
    db: Session,
    *,
    student_id: int,
    exam_paper_id: int,
    attempt_key: str,
    fingerprint: str,
    payload: AttemptSubmitIn,
    settings: Settings,
    allow_retry: bool,
) -> AttemptSubmitData:
    try:
        lock_attempt_key(db, student_id, attempt_key)
        outcome = resolve_existing(db, student_id, attempt_key, fingerprint)
        if outcome.status is ResolveStatus.REPLAY_SUCCESS:
            return _data_from_attempt(outcome.attempt)
        if outcome.status is ResolveStatus.KEY_CONFLICT:
            raise bad_request(MSG_E09_KEY_REUSED)
        if outcome.status is ResolveStatus.REJECTED:
            raise _rejection_error(outcome.rejection)
        return _first_submit(
            db,
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            fingerprint=fingerprint,
            payload=payload,
            settings=settings,
        )
    except AppError:
        raise
    except PaperUnavailable as exc:
        db.rollback()
        _safe_log(
            "paper_integrity",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            reason=exc.reason,
        )
        raise not_found(MSG_E03_PAPER_NOT_ACCESSIBLE) from None
    except GradingDataError as exc:
        db.rollback()
        _safe_log(
            "grading_data",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            error=exc,
        )
        raise AppError(500, MSG_INTERNAL) from None
    except IntegrityError as exc:
        return _recover(
            db,
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            fingerprint=fingerprint,
            payload=payload,
            settings=settings,
            allow_retry=allow_retry,
            stage="integrity_conflict",
            error=exc,
        )
    except SQLAlchemyError as exc:
        return _recover(
            db,
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            fingerprint=fingerprint,
            payload=payload,
            settings=settings,
            allow_retry=allow_retry,
            stage="database",
            error=exc,
        )
    except Exception as exc:  # noqa: BLE001 - 未预期异常必须安全转换（R7-05）
        try:
            db.rollback()
        except Exception:  # noqa: BLE001 - rollback 失败只记录安全状态
            pass
        _safe_log(
            "unexpected",
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            error=exc,
        )
        raise AppError(500, MSG_INTERNAL) from None


# --------------------------------------------------------------------------- #
# 对外入口（路由层已完成 401/403/schema/E05）
# --------------------------------------------------------------------------- #
def submit_attempt(
    db: Session,
    *,
    student_id: int,
    exam_paper_id: int,
    idempotency_key: str,
    payload: AttemptSubmitIn,
    settings: Settings,
) -> AttemptSubmitData:
    fingerprint = build_request_fingerprint(exam_paper_id, payload)
    return _run_submission(
        db,
        student_id=student_id,
        exam_paper_id=exam_paper_id,
        attempt_key=idempotency_key,
        fingerprint=fingerprint,
        payload=payload,
        settings=settings,
        allow_retry=True,
    )
