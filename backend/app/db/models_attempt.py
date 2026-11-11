"""作答系统模型（模块编号待定）：attempts / attempt_answers / attempt_rejections。

范围与口径（开发文档 2.3）：
- ``attempts`` 一次成功提交一行；``attempt_answers`` 保存逐题事实与判分快照；
  ``attempt_rejections`` 保存永久幂等拒绝标记。
- 只新增表，不改模块一/模块二既有表；继承同一个 ``Base`` 与 ``NAMING_CONVENTION``。
- 主键 ``BIGINT`` 自增，时间列 ``TIMESTAMPTZ`` + UTC；提交后只读（不设 updated_at）。
- 快照自足：逐题事实保存题干、选项、答案、解析、篇章类型，读取时不依赖题库当前值。
- 成功与拒绝的引用完整性不同：``attempts`` 对 users / exam_papers / import_batches
  保留 ``RESTRICT`` 外键；``attempt_rejections.exam_paper_id`` 只作追溯、不设外键，
  确保“试卷不存在”的准入拒绝也能落永久标记。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attempt(Base):
    """一次成功提交的整卷作答记录（内部 id 不对外）。"""

    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint(
            "attempt_code", name="uq_attempts_attempt_code"
        ),
        UniqueConstraint(
            "student_id",
            "attempt_key",
            name="uq_attempts_student_attempt_key",
        ),
        CheckConstraint("question_count > 0", name="question_count_positive"),
        CheckConstraint(
            "correct_count BETWEEN 0 AND question_count",
            name="correct_count_range",
        ),
        CheckConstraint(
            "correct_rate BETWEEN 0 AND 100", name="correct_rate_range"
        ),
        CheckConstraint(
            "practice_score IS NULL OR practice_score BETWEEN 0 AND 249",
            name="practice_score_range",
        ),
        Index("ix_attempts_student_paper", "student_id", "exam_paper_id"),
        Index("ix_attempts_paper", "exam_paper_id"),
        Index("ix_attempts_submitted_at", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 对外唯一标识，uuid4 字符串；日志与追溯使用它而非内部 id。
    attempt_code: Mapped[str] = mapped_column(String(36), nullable=False)
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exam_papers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 提交时批次标识，仅追溯，不参与准入判定。
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("import_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # 应用侧显式写入 UTC；DB now() 仅作兜底。
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # 整数百分比（BR-16/R4）。
    correct_rate: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # 0–249；不可用时为 NULL（BR-16a）。
    practice_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # 题型分组快照、规则版本、可用性与原因；不可用时也要写 reason/rule。
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AttemptAnswer(Base):
    """逐题事实 + 判分快照；字母均为原卷字母空间。"""

    __tablename__ = "attempt_answers"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "question_no",
            name="uq_attempt_answers_attempt_question_no",
        ),
        UniqueConstraint(
            "attempt_id",
            "question_id",
            name="uq_attempt_answers_attempt_question_id",
        ),
        CheckConstraint(
            "is_correct = (selected_option IS NOT NULL"
            " AND selected_option = correct_option)",
            name="correctness",
        ),
        CheckConstraint("question_id > 0", name="question_id_positive"),
        CheckConstraint("question_no > 0", name="question_no_positive"),
        CheckConstraint(
            "correct_option IN ('A', 'B', 'C', 'D')", name="correct_option_domain"
        ),
        CheckConstraint(
            "selected_option IS NULL OR selected_option IN ('A', 'B', 'C', 'D')",
            name="selected_option_domain",
        ),
        Index("ix_attempt_answers_attempt", "attempt_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 仅同一聚合内允许级联；应用不删除 attempt。
    attempt_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 提交时的原卷题号（S-2）。
    question_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 题库题目身份，仅追溯/换批检测；不设外键，避免题库清理影响快照。
    question_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    passage_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default=""
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 按原卷 A–D 顺序的选项文本快照（S-4）。
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    option_c: Mapped[str] = mapped_column(Text, nullable=False)
    option_d: Mapped[str] = mapped_column(Text, nullable=False)
    # 提交时的原卷字母（S-5）。
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    # 学生所选原卷字母；NULL = 未作答（S-7）。
    selected_option: Mapped[str | None] = mapped_column(String(1), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 允许空串（G6/BR-25），不做占位（S-6）。
    explanation_text: Mapped[str] = mapped_column(Text, nullable=False)


class AttemptRejection(Base):
    """永久幂等拒绝标记；不是作答记录，不计入 attempt 数。"""

    __tablename__ = "attempt_rejections"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "attempt_key",
            name="uq_attempt_rejections_student_attempt_key",
        ),
        CheckConstraint(
            "rejection_kind IN ('paper_not_accessible',"
            " 'content_version_mismatch')",
            name="rejection_kind_domain",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 仅保存提交目标标识用于追溯；不设外键（试卷不存在时也要能落标记）。
    exam_paper_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # 首次拒绝时的请求指纹；仅作审计/排查，不参与回放判定。
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rejection_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # 内部定位信息（如不一致的题目身份），不返回学生。
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
