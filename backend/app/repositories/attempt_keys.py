"""作答系统幂等仓储：查键、永久拒绝标记、限次计数、请求指纹与两把事务锁。

边界（开发文档 2.6、2.6.3、2.6.4；任务卡 T03）：

- 只做数据访问：**不 commit**、不抛业务 ``AppError``、不判分、不做准入/内容核对；
  判定顺序与事务边界由 T06 编排；
- ``resolve_existing`` 只按 ``(student_id, attempt_key)`` 短路，返回四态；
- 永久拒绝标记写入使用 ``INSERT ... ON CONFLICT DO NOTHING`` + 同事务读回，
  重复写入返回同一行，避免异常把调用方事务打成 aborted；
- 锁键算法固定为 ``sha256(text)[:4]`` 大端有符号 int32，**禁止** Python 内置
  ``hash()``（进程随机化）与数据库 ``hashtext()``（随版本变化）。
"""

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models_attempt import Attempt, AttemptAnswer, AttemptRejection
from app.schemas_attempts import AttemptSubmitIn

# 永久拒绝标记的两类业务原因（与 T01 模型 CHECK 取值一致）。
REJECTION_KIND_PAPER_NOT_ACCESSIBLE = "paper_not_accessible"
REJECTION_KIND_CONTENT_VERSION_MISMATCH = "content_version_mismatch"

# 两把事务锁的命名空间：1=键锁，2=学生+试卷限次锁。
LOCK_CLASS_ATTEMPT_KEY = 1
LOCK_CLASS_STUDENT_PAPER = 2

# 请求指纹规范化的版本前缀（只用于判断“同键是否同内容/同试卷”）。
FINGERPRINT_VERSION = "v1"
FINGERPRINT_HEX_LENGTH = 64

_LOCK_OBJID_BYTES = 4


# --------------------------------------------------------------------------- #
# 请求指纹
# --------------------------------------------------------------------------- #
def build_request_fingerprint(
    exam_paper_id: int, payload: AttemptSubmitIn
) -> str:
    """按开发文档 2.6.1 的规范化串取 SHA-256（hex，64 字符）。

    规范串：``v1|<exam_paper_id>|<loaded ids 升序逗号>|<answers 按 question_id
    升序 "qid:letter" 逗号>``。幂等键本身不参与指纹；答案/题目集合顺序不影响结果。
    只用于“同键是否同内容/同试卷”，不参与判分。
    """

    loaded = ",".join(str(qid) for qid in sorted(payload.loaded_question_ids))
    answers = ",".join(
        f"{answer.question_id}:{answer.selected_option}"
        for answer in sorted(payload.answers, key=lambda item: item.question_id)
    )
    canonical = f"{FINGERPRINT_VERSION}|{exam_paper_id}|{loaded}|{answers}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 锁键算法与两把事务锁
# --------------------------------------------------------------------------- #
def lock_objid(lock_text: str) -> int:
    """``int.from_bytes(sha256(text)[:4], "big", signed=True)``（固定公式）。"""

    digest = hashlib.sha256(lock_text.encode("utf-8")).digest()
    return int.from_bytes(digest[:_LOCK_OBJID_BYTES], "big", signed=True)


def attempt_key_lock_text(student_id: int, attempt_key: str) -> str:
    """键锁文本：``attempt-key:{student_id}:{attempt_key}``（classid=1）。"""

    return f"attempt-key:{student_id}:{attempt_key}"


def attempt_limit_lock_text(student_id: int, exam_paper_id: int) -> str:
    """限次锁文本：``attempt-limit:{student_id}:{exam_paper_id}``（classid=2）。"""

    return f"attempt-limit:{student_id}:{exam_paper_id}"


def lock_attempt_key(db: Session, student_id: int, attempt_key: str) -> None:
    """获取键级事务锁（``pg_advisory_xact_lock``，事务结束自动释放）。"""

    db.execute(
        text("SELECT pg_advisory_xact_lock(:class_id, :obj_id)"),
        {
            "class_id": LOCK_CLASS_ATTEMPT_KEY,
            "obj_id": lock_objid(
                attempt_key_lock_text(student_id, attempt_key)
            ),
        },
    )


def lock_student_paper(db: Session, student_id: int, exam_paper_id: int) -> None:
    """获取“学生+试卷”限次事务锁（classid=2）；须在键锁之后获取。"""

    db.execute(
        text("SELECT pg_advisory_xact_lock(:class_id, :obj_id)"),
        {
            "class_id": LOCK_CLASS_STUDENT_PAPER,
            "obj_id": lock_objid(
                attempt_limit_lock_text(student_id, exam_paper_id)
            ),
        },
    )


# --------------------------------------------------------------------------- #
# 键查询与限次计数
# --------------------------------------------------------------------------- #
def get_attempt_by_key(
    db: Session, student_id: int, attempt_key: str
) -> Attempt | None:
    """按 ``(student_id, attempt_key)`` 取成功作答记录。"""

    return db.scalar(
        select(Attempt).where(
            Attempt.student_id == student_id,
            Attempt.attempt_key == attempt_key,
        )
    )


def get_rejection_by_key(
    db: Session, student_id: int, attempt_key: str
) -> AttemptRejection | None:
    """按 ``(student_id, attempt_key)`` 取永久拒绝标记。"""

    return db.scalar(
        select(AttemptRejection).where(
            AttemptRejection.student_id == student_id,
            AttemptRejection.attempt_key == attempt_key,
        )
    )


def count_success_attempts(
    db: Session, student_id: int, exam_paper_id: int
) -> int:
    """同学生同卷的成功 attempt 数（BR-18a 限次计数）。"""

    return db.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(
            Attempt.student_id == student_id,
            Attempt.exam_paper_id == exam_paper_id,
        )
    ) or 0


# --------------------------------------------------------------------------- #
# 写入（只 add/flush，不 commit）
# --------------------------------------------------------------------------- #
def insert_attempt_with_answers(
    db: Session,
    attempt: Attempt,
    answers: list[AttemptAnswer],
) -> Attempt:
    """写入 attempt 与其逐题事实（只 add/flush，不 commit）。

    调用方负责在同一事务内提交；成功记录与全部逐题事实必须一次提交。
    """

    db.add(attempt)
    db.flush()
    for answer in answers:
        answer.attempt_id = attempt.id
        db.add(answer)
    db.flush()
    return attempt


def insert_rejection(
    db: Session,
    *,
    student_id: int,
    exam_paper_id: int,
    attempt_key: str,
    request_fingerprint: str,
    rejection_kind: str,
    detail: dict | None = None,
) -> AttemptRejection:
    """写入永久拒绝标记；同键已存在时读回原行（不新增、不抛唯一冲突）。

    ``ON CONFLICT DO NOTHING`` 让“并发/重试写入同一键”自然收敛到一行，
    且不会把当前事务打成 aborted；是否提交由调用方决定（拒绝分支需先
    commit 成功再向客户端返回拒绝）。
    """

    statement = (
        pg_insert(AttemptRejection)
        .values(
            student_id=student_id,
            exam_paper_id=exam_paper_id,
            attempt_key=attempt_key,
            request_fingerprint=request_fingerprint,
            rejection_kind=rejection_kind,
            detail=detail,
        )
        .on_conflict_do_nothing(index_elements=["student_id", "attempt_key"])
    )
    db.execute(statement)
    marker = get_rejection_by_key(db, student_id, attempt_key)
    if marker is None:
        # 唯一约束保证写入/读回必须可见；读不到说明事务/并发异常，交调用方转安全 500。
        raise RuntimeError("拒绝标记写入后无法读回")
    return marker


# --------------------------------------------------------------------------- #
# 短路判定
# --------------------------------------------------------------------------- #
class ResolveStatus(StrEnum):
    """同键短路四态（开发文档 2.6.2 的 5a/5b/5c/无记录）。"""

    REPLAY_SUCCESS = "replay_success"
    KEY_CONFLICT = "key_conflict"
    REJECTED = "rejected"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ResolveOutcome:
    """短路结果：REPLAY_SUCCESS 携带原 attempt，REJECTED 携带原标记。"""

    status: ResolveStatus
    attempt: Attempt | None = None
    rejection: AttemptRejection | None = None


def resolve_existing(
    db: Session,
    student_id: int,
    attempt_key: str,
    fingerprint: str,
) -> ResolveOutcome:
    """按 ``(student_id, attempt_key)`` 判定同键短路结果。

    成功记录与永久标记各自唯一约束；跨表互斥由应用层“键锁 + 本函数 +
    首次写入”保证（数据库无法建跨表唯一约束）。
    """

    attempt = get_attempt_by_key(db, student_id, attempt_key)
    if attempt is not None:
        if attempt.request_fingerprint == fingerprint:
            return ResolveOutcome(ResolveStatus.REPLAY_SUCCESS, attempt=attempt)
        return ResolveOutcome(ResolveStatus.KEY_CONFLICT, attempt=attempt)

    rejection = get_rejection_by_key(db, student_id, attempt_key)
    if rejection is not None:
        return ResolveOutcome(ResolveStatus.REJECTED, rejection=rejection)

    return ResolveOutcome(ResolveStatus.NONE)
