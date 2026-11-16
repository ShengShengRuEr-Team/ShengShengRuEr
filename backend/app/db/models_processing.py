"""Durable processing state, immutable drafts and auditable review decisions."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class MaterialSource(Base):
    __tablename__ = "material_sources"
    __table_args__ = (UniqueConstraint("source_kind", "storage_key", "sha256"),)
    id = Column(BigInteger, primary_key=True)
    exam_paper_code = Column(String(64), nullable=False, index=True)
    source_kind = Column(String(32), nullable=False)
    storage_key = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    media_type = Column(String(64), nullable=False)
    source_locator = Column(Text, nullable=False)
    derived_from_material_id = Column(BigInteger, ForeignKey("material_sources.id"))
    generation = Column(JSONB)
    registered_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DictionarySnapshot(Base):
    __tablename__ = "dictionary_snapshots"
    id = Column(BigInteger, primary_key=True)
    schema_sha256 = Column(String(64), nullable=False, unique=True)
    data_sha256 = Column(String(64), nullable=False)
    version = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    id_mapping = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','running','failed',"
            "'awaiting_confirmation','completed')",
            name="state",
        ),
        Index("ix_processing_tasks_poll", "state", "created_at", "id"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    exam_paper_code = Column(String(64), nullable=False, index=True)
    exam_paper_id = Column(BigInteger, ForeignKey("exam_papers.id"))
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("processing_tasks.id"))
    state = Column(String(32), nullable=False, default="pending")
    stage = Column(String(32), nullable=False, default="registered")
    attempt = Column(Integer, nullable=False, default=0)
    lease_token = Column(UUID(as_uuid=True))
    worker_id = Column(String(128))
    heartbeat_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    input_hash = Column(String(64), nullable=False)
    method_hash = Column(String(64), nullable=False)
    result_hash = Column(String(64))
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"))
    reused_task_id = Column(UUID(as_uuid=True), ForeignKey("processing_tasks.id"))
    request = Column(JSONB, nullable=False)
    method = Column(JSONB, nullable=False)
    issues = Column(JSONB, nullable=False, default=list)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TaskMaterial(Base):
    __tablename__ = "task_materials"
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), primary_key=True
    )
    material_id = Column(
        BigInteger, ForeignKey("material_sources.id"), primary_key=True
    )


class ProcessingArtifact(Base):
    __tablename__ = "processing_artifacts"
    __table_args__ = (UniqueConstraint("task_id", "stage", "artifact_hash"),)
    id = Column(BigInteger, primary_key=True)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    stage = Column(String(32), nullable=False)
    input_hash = Column(String(64), nullable=False)
    method_hash = Column(String(64), nullable=False)
    storage_key = Column(Text, nullable=False)
    artifact_hash = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    schema_version = Column(String(32), nullable=False, default="m3.v1")
    source_artifact_id = Column(BigInteger, ForeignKey("processing_artifacts.id"))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingDraft(Base):
    __tablename__ = "processing_drafts"
    __table_args__ = (UniqueConstraint("task_id", "view"),)
    id = Column(BigInteger, primary_key=True)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    view = Column(String(16), nullable=False)
    result_hash = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingReview(Base):
    __tablename__ = "processing_reviews"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    result_hash = Column(String(64), nullable=False)
    scope = Column(String(32), nullable=False)
    decision = Column(String(32), nullable=False)
    items = Column(JSONB, nullable=False)
    evidence_refs = Column(JSONB, nullable=False)
    note = Column(Text, nullable=False)
    operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    operator_label = Column(String(128), nullable=False)
    reviewed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingCorrection(Base):
    __tablename__ = "processing_corrections"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    parent_task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    before_hash = Column(String(64), nullable=False)
    after_hash = Column(String(64), nullable=False)
    before_payload = Column(JSONB, nullable=False)
    after_payload = Column(JSONB, nullable=False)
    changes = Column(JSONB, nullable=False)
    reason = Column(Text, nullable=False)
    source_refs = Column(JSONB, nullable=False)
    operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BatchActivationLog(Base):
    __tablename__ = "batch_activation_logs"
    id = Column(BigInteger, primary_key=True)
    exam_paper_id = Column(BigInteger, ForeignKey("exam_papers.id"), nullable=False)
    old_batch_id = Column(BigInteger, ForeignKey("import_batches.id"))
    new_batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    check_id = Column(BigInteger, ForeignKey("content_checks.id"), nullable=False)
    result_hash = Column(String(64), nullable=False)
    operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BatchPaperMetadata(Base):
    __tablename__ = "batch_paper_metadata"
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), primary_key=True)
    content_group_id = Column(
        BigInteger, ForeignKey("content_groups.id"), nullable=False
    )
    binding_state = Column(String(32))
    question_order_state = Column(String(32))
    option_order_state = Column(String(32))
    equivalence_basis = Column(Text)


class BatchAudioGroup(Base):
    __tablename__ = "batch_audio_groups"
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), primary_key=True)
    audio_id = Column(BigInteger, ForeignKey("audio_files.id"), primary_key=True)
    content_group_id = Column(
        BigInteger, ForeignKey("content_groups.id"), primary_key=True
    )


class BatchSourceRef(Base):
    __tablename__ = "batch_source_refs"
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    material_id = Column(BigInteger, ForeignKey("material_sources.id"), nullable=False)
    entity_type = Column(String(64), nullable=False)
    src_id = Column(String(128), nullable=False)
    locator = Column(JSONB, nullable=False)
    original_text = Column(Text)
    conversion_hash = Column(String(64))


class LlmAttempt(Base):
    """Reservations are persistent across all tasks, including unknown charges."""

    __tablename__ = "processing_llm_attempts"
    id = Column(BigInteger, primary_key=True)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id"), nullable=False
    )
    run_key = Column(String(64), nullable=False)
    phase = Column(String(16), nullable=False)
    request_hash = Column(String(64), nullable=False)
    request_payload = Column(JSONB, nullable=False)
    response_payload = Column(JSONB)
    response_model = Column(String(128))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    reserved_usd = Column(Numeric(14, 8), nullable=False)
    charged_usd = Column(Numeric(14, 8))
    billing_status = Column(String(16), nullable=False, default="unknown")
    status = Column(String(32), nullable=False, default="reserved")
    error_code = Column(String(64))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
