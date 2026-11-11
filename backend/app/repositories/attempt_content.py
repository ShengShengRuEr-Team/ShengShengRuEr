"""作答提交的准入、内容完整性、身份/版本与答案结构判定（T04）。

只读模块二既有表，复用 ``repositories/listening.py`` 的 ``student_access`` 与
映射换算逻辑；本模块不写库、不 commit、不写永久拒绝标记、不抛 HTTP 异常：

- ``check_submit_access``：6b 准入（调用模块二 ``student_access``，三条件缺一不可）；
- ``check_paper_integrity``：6b2 数据/音频完整性（严格映射复用
  ``listening.paper_letter_for`` / ``paper_options_for``，失败抛本地非 HTTP
  ``PaperUnavailable(reason)``，由 T06 映射 404 E14 且不写标记）；
- ``load_current_paper_questions``：按 6b 固定的 ``batch_id`` 读取整卷快照输入，
  供 T05 判分使用（不再自行取“当前批次”，避免换批窗口）；
- ``classify_loaded_ids``：6c 身份/版本分类（D-16 固定优先级）；
- ``validate_answers``：6a 答案结构校验（重复/集合外/他卷）。

判定顺序由 T06 编排：短路(T03) → 6a → **6b 准入** → 6b2 完整性 → 6c 身份
（版本优先于他卷/集合）→ 6d 限次；本模块不改变该顺序。
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models_listening import (
    AudioFile,
    ExamPaper,
    ImportBatch,
    Passage,
    Presentation,
    Question,
)
from app.repositories.listening import (
    PAPER_UNAVAILABLE_OPTION_MAPPING_INVALID,  # noqa: F401 - 供 T05/T06 与测试复用
    PaperUnavailable,
    paper_letter_for,
    paper_options_for,
    student_access,
)
from app.schemas_attempts import AttemptAnswerIn

# --------------------------------------------------------------------------- #
# 数据/音频完整性失败原因（T06 统一映射 404 E14，不写永久标记）
# --------------------------------------------------------------------------- #
PAPER_UNAVAILABLE_EXPECTED_COUNT_MISSING = "expected_count_missing"
PAPER_UNAVAILABLE_QUESTION_COUNT_MISMATCH = "question_count_mismatch"
PAPER_UNAVAILABLE_PRESENTATION_MISMATCH = "presentation_mismatch"
PAPER_UNAVAILABLE_QUESTION_NO_COVERAGE = "question_no_coverage"
PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE = "audio_unavailable"


# --------------------------------------------------------------------------- #
# 整卷快照输入（供 T05 判分；T05 只接收已换算好的原卷字母与选项文本）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class PaperQuestion:
    question_no: int
    question_id: int
    passage_type: str
    question_text: str
    options: tuple[str, str, str, str]
    correct_paper_letter: str
    explanation_text: str


# --------------------------------------------------------------------------- #
# 6b 准入：复用模块二学生可访问判定
# --------------------------------------------------------------------------- #
def check_submit_access(
    db: Session, exam_paper_id: int
) -> tuple[bool, ExamPaper | None, ImportBatch | None]:
    """返回 ``(visible, paper, batch)``；三条件（当前批次 ∧ 检查通过 ∧ 确认可见）缺一不可。

    这是提交链的第一步业务判定（6b），必须先于身份分类/内容核对，避免
    “加载后下线再同键重试”被错误升级为 400/404 语义。
    """

    return student_access(db, exam_paper_id)


# --------------------------------------------------------------------------- #
# 6b2 数据/音频完整性
# --------------------------------------------------------------------------- #
def _load_batch_rows(
    db: Session, batch_id: int
) -> tuple[list[Question], list[Presentation], dict[int, str]]:
    questions = db.scalars(
        select(Question).where(Question.batch_id == batch_id)
    ).all()
    presentations = db.scalars(
        select(Presentation).where(Presentation.batch_id == batch_id)
    ).all()
    passages = db.scalars(
        select(Passage).where(Passage.batch_id == batch_id)
    ).all()
    passage_type_by_id = {passage.id: passage.passage_type for passage in passages}
    return list(questions), list(presentations), passage_type_by_id


def _ensure_audio_readable(
    db: Session, paper: ExamPaper, settings: Settings
) -> None:
    if paper.playback_audio_id is None:
        raise PaperUnavailable(PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE)
    audio = db.get(AudioFile, paper.playback_audio_id)
    if audio is None:
        raise PaperUnavailable(PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE)
    audio_path = Path(settings.audio_storage_path) / audio.storage_key
    if not audio_path.is_file():
        raise PaperUnavailable(PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE)
    try:
        with audio_path.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        raise PaperUnavailable(PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE) from exc


def check_paper_integrity(
    db: Session,
    paper: ExamPaper,
    batch: ImportBatch,
    settings: Settings,
) -> None:
    """校验整卷结构、严格映射与提交时音频可读；失败抛 ``PaperUnavailable(reason)``。

    题量分母 ``N`` 必须取自 ``paper.expected_question_count``（不得用剩余题数），
    并验证题号完整覆盖 ``1..N``；任一失败 → 不判分、不写 attempt、不写永久标记。
    """

    expected = paper.expected_question_count
    if expected is None or not paper.expected_question_count_source:
        raise PaperUnavailable(PAPER_UNAVAILABLE_EXPECTED_COUNT_MISSING)

    questions, presentations, _passage_types = _load_batch_rows(db, batch.id)
    if len(questions) != expected:
        raise PaperUnavailable(PAPER_UNAVAILABLE_QUESTION_COUNT_MISMATCH)
    if len(presentations) != len(questions):
        raise PaperUnavailable(PAPER_UNAVAILABLE_PRESENTATION_MISMATCH)

    question_by_id = {question.id: question for question in questions}
    presentation_question_ids = [item.question_id for item in presentations]
    if len(set(presentation_question_ids)) != len(presentations):
        raise PaperUnavailable(PAPER_UNAVAILABLE_PRESENTATION_MISMATCH)
    if any(qid not in question_by_id for qid in presentation_question_ids):
        raise PaperUnavailable(PAPER_UNAVAILABLE_PRESENTATION_MISMATCH)

    question_nos = sorted(item.question_no for item in presentations)
    if question_nos != list(range(1, expected + 1)):
        raise PaperUnavailable(PAPER_UNAVAILABLE_QUESTION_NO_COVERAGE)

    for presentation in presentations:
        paper_letter_for(question_by_id[presentation.question_id], presentation)

    _ensure_audio_readable(db, paper, settings)


# --------------------------------------------------------------------------- #
# 6b 固定 batch 下的整卷读取（供 T05）
# --------------------------------------------------------------------------- #
def load_current_paper_questions(
    db: Session, exam_paper_id: int, batch_id: int
) -> list[PaperQuestion]:
    """按 6b 返回的 ``batch_id`` 读取整卷，按 ``question_no`` 升序返回快照输入。

    必须显式传入 ``batch_id``，不得再查询“当前批次”，否则换批窗口会破坏
    准入/身份/判分使用同一版本边界。
    """

    questions, presentations, passage_type_by_id = _load_batch_rows(db, batch_id)
    question_by_id = {question.id: question for question in questions}
    ordered = sorted(presentations, key=lambda item: item.question_no)
    result: list[PaperQuestion] = []
    for presentation in ordered:
        question = question_by_id.get(presentation.question_id)
        if question is None or presentation.exam_paper_id != exam_paper_id:
            raise PaperUnavailable(PAPER_UNAVAILABLE_PRESENTATION_MISMATCH)
        result.append(
            PaperQuestion(
                question_no=presentation.question_no,
                question_id=question.id,
                passage_type=passage_type_by_id.get(question.passage_id, ""),
                question_text=question.question_text,
                options=paper_options_for(question, presentation),
                correct_paper_letter=paper_letter_for(question, presentation),
                explanation_text=question.explanation_text,
            )
        )
    return result


# --------------------------------------------------------------------------- #
# 6c 身份/版本分类（D-16 固定优先级）
# --------------------------------------------------------------------------- #
class IdentityStatus(StrEnum):
    OK = "ok"
    VERSION_MISMATCH = "version_mismatch"
    INVALID_IDENTITY = "invalid_identity"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class IdentityOutcome:
    status: IdentityStatus
    old_batch_ids: tuple[int, ...] = ()
    foreign_ids: tuple[int, ...] = ()


def _current_batch_id_for(
    db: Session, current_ids: list[int], batch_id: int | None
) -> int | None:
    if batch_id is not None:
        return batch_id
    if not current_ids:
        return None
    rows = db.scalars(
        select(Question.batch_id).where(Question.id.in_(current_ids))
    ).all()
    distinct = set(rows)
    return distinct.pop() if len(distinct) == 1 else None


def classify_loaded_ids(
    db: Session,
    exam_paper_id: int,
    current_ids: list[int],
    loaded_ids: list[int],
    batch_id: int | None = None,
) -> IdentityOutcome:
    """按 D-16 分类加载时整卷题目身份集合。

    优先级：任一旧批次 → ``version_mismatch``；否则任一他卷/不存在 →
    ``invalid_identity``；否则真子集/不等 → ``incomplete``；集合完全一致
    （允许乱序）→ ``ok``。``batch_id`` 建议传 6b 固定批次；未传时以
    ``current_ids`` 的题目行推断，推断不唯一则按 ``invalid_identity`` fail-closed。
    """

    current_list = list(current_ids)
    loaded_list = list(loaded_ids)
    current_set = set(current_list)
    loaded_set = set(loaded_list)

    current_batch_id = _current_batch_id_for(db, current_list, batch_id)
    if current_batch_id is None:
        # 无法确认当前批次：fail-closed，不默认放行。
        return IdentityOutcome(
            IdentityStatus.INVALID_IDENTITY, foreign_ids=tuple(loaded_list)
        )

    extra = [qid for qid in loaded_list if qid not in current_set]
    if not extra:
        if loaded_set == current_set:
            return IdentityOutcome(IdentityStatus.OK)
        return IdentityOutcome(IdentityStatus.INCOMPLETE)

    question_rows = (
        db.scalars(select(Question).where(Question.id.in_(extra))).all()
        if extra
        else []
    )
    question_by_id = {question.id: question for question in question_rows}
    presentation_rows = (
        db.scalars(
            select(Presentation).where(Presentation.question_id.in_(extra))
        ).all()
        if extra
        else []
    )
    paper_by_question = {
        presentation.question_id: presentation.exam_paper_id
        for presentation in presentation_rows
    }

    old_batch_ids: list[int] = []
    foreign_ids: list[int] = []
    for question_id in extra:
        question = question_by_id.get(question_id)
        if question is None:
            # 题目行不存在（或已被物理删除）：无法证明版本，按参数非法 fail-closed。
            foreign_ids.append(question_id)
            continue
        owner_paper_id = paper_by_question.get(question_id)
        if owner_paper_id is None or owner_paper_id != exam_paper_id:
            foreign_ids.append(question_id)
            continue
        if question.batch_id == current_batch_id:
            # 同批次却不在当前整卷集合：调用方集合不可信，按参数非法 fail-closed。
            foreign_ids.append(question_id)
            continue
        old_batch_ids.append(question_id)

    if old_batch_ids:
        return IdentityOutcome(
            IdentityStatus.VERSION_MISMATCH, old_batch_ids=tuple(old_batch_ids)
        )
    if foreign_ids:
        return IdentityOutcome(
            IdentityStatus.INVALID_IDENTITY, foreign_ids=tuple(foreign_ids)
        )
    # extra 非空且既非旧批次也非他卷：理论上不可达，按集合不完整处理。
    return IdentityOutcome(IdentityStatus.INCOMPLETE)


# --------------------------------------------------------------------------- #
# 6a 答案结构校验（业务 400 E07；不写标记）
# --------------------------------------------------------------------------- #
ANSWER_REASON_DUPLICATE_LOADED = "duplicate_loaded_question_id"
ANSWER_REASON_DUPLICATE_ANSWER = "duplicate_answer_question_id"
ANSWER_REASON_NOT_IN_LOADED = "answer_not_in_loaded_set"
ANSWER_REASON_NOT_IN_CURRENT = "answer_not_in_current_batch"


@dataclass(frozen=True, slots=True)
class AnswerValidation:
    ok: bool
    reason: str | None = None
    offending_ids: tuple[int, ...] = ()


def _duplicates(values: list[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    duplicated: list[int] = []
    for value in values:
        if value in seen:
            if value not in duplicated:
                duplicated.append(value)
        else:
            seen.add(value)
    return tuple(duplicated)


def validate_answers(
    loaded_ids: list[int],
    current_ids: list[int],
    answers: list[AttemptAnswerIn],
) -> AnswerValidation:
    """校验答案结构：重复身份、答案集合外/他卷；失败返回结构化原因（T06 → 400 E07）。

    只做“结构与集合归属”校验；题目正确性/判分不属于本函数。
    """

    duplicate_loaded = _duplicates(list(loaded_ids))
    if duplicate_loaded:
        return AnswerValidation(
            False,
            ANSWER_REASON_DUPLICATE_LOADED,
            duplicate_loaded,
        )

    answer_ids = [answer.question_id for answer in answers]
    duplicate_answers = _duplicates(answer_ids)
    if duplicate_answers:
        return AnswerValidation(
            False, ANSWER_REASON_DUPLICATE_ANSWER, duplicate_answers
        )

    loaded_set = set(loaded_ids)
    current_set = set(current_ids)
    outside_loaded = tuple(
        dict.fromkeys(qid for qid in answer_ids if qid not in loaded_set)
    )
    if outside_loaded:
        return AnswerValidation(
            False, ANSWER_REASON_NOT_IN_LOADED, outside_loaded
        )

    outside_current = tuple(
        dict.fromkeys(qid for qid in answer_ids if qid not in current_set)
    )
    if outside_current:
        return AnswerValidation(
            False, ANSWER_REASON_NOT_IN_CURRENT, outside_current
        )

    return AnswerValidation(True)
