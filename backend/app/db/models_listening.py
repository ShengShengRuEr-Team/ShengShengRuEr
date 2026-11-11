"""模块二业务模型：题库管理与整套试卷展示（最小业务子集）。

范围：试卷、音频、篇章、原文片段、题目、内容组、原卷映射，以及批次、
内容检查、可见性与操作记录四张系统记录表。词典与标注表（06/07A~07D/
08/09/10/11）本期不建，待模块三接入时按 16 表基线补齐。

设计要点：
- 试卷(exam_papers)与音频(audio_files)是跨批次稳定身份；篇章、片段、
  题目、映射、内容组随批次版本化，均挂 ``batch_id``。
- 学生可访问 = 当前批次 ∧ 最低内容检查通过 ∧ 管理员确认可见；三者分别
  持久化于 import_batches / content_checks / paper_visibility，互不合并。
- 继承模块一同一个 ``Base`` 与 ``NAMING_CONVENTION``，不动模块一 4 张表。
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
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AudioFile(Base):
    __tablename__ = "audio_files"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    audio_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    storage_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local", server_default="local"
    )
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # 16 表基线：音频版本与派生关系（原始/剪辑/降噪/转码）。
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    variant_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="原始", server_default="原始"
    )
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExamPaper(Base):
    __tablename__ = "exam_papers"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exam_paper_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    exam_level: Mapped[str] = mapped_column(String(32), nullable=False)
    exam_year: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_month: Mapped[int] = mapped_column(Integer, nullable=False)
    paper_set: Mapped[int] = mapped_column(Integer, nullable=False)
    content_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="listening", server_default="listening"
    )
    playback_audio_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audio_files.id", ondelete="SET NULL"), nullable=True
    )
    # 该套选定原卷的应有题量：首次导入时固定，后续批次的题量与题序都对照它校验，
    # 避免「末尾整题缺失」这类不完整数据被当成整卷（验收报告 F02）。
    expected_question_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_question_count_source: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 16 表基线：来源说明与题号/选项映射来源。
    source: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    mapping_source: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'failed')", name="status"
        ),
        # 每套试卷至多一个当前批次（部分唯一索引）。
        Index(
            "uq_import_batches_one_current",
            "exam_paper_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    audio_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audio_files.id", ondelete="SET NULL"), nullable=True
    )
    batch_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    source_manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContentGroup(Base):
    __tablename__ = "content_groups"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    content_group_code: Mapped[str] = mapped_column(String(64), nullable=False)
    group_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    exam_level_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("batch_id", "passage_index"),
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    audio_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audio_files.id", ondelete="SET NULL"), nullable=True
    )
    passage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    passage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    passage_type: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    topic: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # 16 表基线：场景与口音（口音为标注字段，未判定时记「未判定」）。
    scene: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    accent: Mapped[str] = mapped_column(
        String(32), nullable=False, default="未判定", server_default="未判定"
    )
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    body_end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    speaker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("passage_id", "segment_index"),
        CheckConstraint("segment_type IN ('body', 'question')", name="segment_type"),
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    passage_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_code: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("correct_option IN ('A', 'B', 'C', 'D')", name="correct_option"),
        CheckConstraint(
            "content_state IN ('待补齐', '可用', '停用')", name="content_state"
        ),
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    passage_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )
    question_code: Mapped[str] = mapped_column(String(64), nullable=False)
    question_segment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transcript_segments.id", ondelete="SET NULL"), nullable=True
    )
    # 来源卷全卷题号（16 表基线 question_index）；目标卷题号见 presentations.question_no。
    question_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    option_c: Mapped[str] = mapped_column(Text, nullable=False)
    option_d: Mapped[str] = mapped_column(Text, nullable=False)
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_source: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    content_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待补齐", server_default="待补齐"
    )
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Presentation(Base):
    __tablename__ = "presentations"
    __table_args__ = (
        UniqueConstraint("batch_id", "question_no"),
        CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')", name="review_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    question_no: Mapped[int] = mapped_column(Integer, nullable=False)
    option_mapping_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="未知", server_default="未知"
    )
    mapping_source: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    option_letter_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    collector: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="待审核", server_default="待审核"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContentCheck(Base):
    __tablename__ = "content_checks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    is_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    issues: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaperVisibility(Base):
    __tablename__ = "paper_visibility"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    is_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class VisibilityAuditLog(Base):
    __tablename__ = "visibility_audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exam_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    operator_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
