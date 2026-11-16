"""Persistent business identities; execution state stays in processing_tasks.

Current pointers use composite foreign keys so an ID from another workflow or
revision cannot become current, even through a direct database write.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class AuditTimes:
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingWorkflow(AuditTimes, Base):
    __tablename__ = "processing_workflows"
    __table_args__ = (
        UniqueConstraint(
            "exam_level", "exam_year", "exam_month", "paper_set", "content_scope"
        ),
        CheckConstraint("row_version > 0", name="row_version"),
        CheckConstraint(
            "exam_level IN ('CET4','CET6') AND exam_year BETWEEN 1980 AND 2200 "
            "AND exam_month BETWEEN 1 AND 12 AND paper_set > 0 "
            "AND content_scope = 'listening'",
            name="identity",
        ),
        ForeignKeyConstraint(
            ["current_revision_id", "id"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.workflow_id",
            ],
            use_alter=True,
            name="fk_workflow_current_revision",
        ),
        ForeignKeyConstraint(
            ["current_task_id", "current_revision_id", "id"],
            [
                "processing_tasks.id",
                "processing_tasks.revision_id",
                "processing_tasks.workflow_id",
            ],
            use_alter=True,
            name="fk_workflow_current_task",
        ),
        Index("ix_workflow_cursor", "created_at", "id"),
        Index(
            "ix_workflow_states",
            "processing_state",
            "content_review_state",
            "publication_state",
        ),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    exam_level = Column(String(32), nullable=False)
    exam_year = Column(Integer, nullable=False)
    exam_month = Column(Integer, nullable=False)
    paper_set = Column(Integer, nullable=False)
    content_scope = Column(String(16), nullable=False, default="listening")
    exam_paper_id = Column(BigInteger, ForeignKey("exam_papers.id"))
    current_revision_id = Column(UUID(as_uuid=True))
    current_task_id = Column(UUID(as_uuid=True))
    row_version = Column(Integer, nullable=False, default=1)
    processing_state = Column(String(32), nullable=False, default="awaiting_materials")
    content_review_state = Column(String(32), nullable=False, default="not_ready")
    error_review_state = Column(String(32), nullable=False, default="not_ready")
    publication_state = Column(String(32), nullable=False, default="unpublished")
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    updated_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)


class ProcessingWorkflowRevision(AuditTimes, Base):
    __tablename__ = "processing_workflow_revisions"
    __table_args__ = (
        UniqueConstraint("id", "workflow_id"),
        UniqueConstraint("id", "final_result_hash", name="uq_revision_final_hash"),
        UniqueConstraint("workflow_id", "revision_no"),
        ForeignKeyConstraint(
            ["parent_revision_id", "workflow_id"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.workflow_id",
            ],
            name="fk_revision_parent",
        ),
        ForeignKeyConstraint(
            ["final_task_id", "id", "workflow_id"],
            [
                "processing_tasks.id",
                "processing_tasks.revision_id",
                "processing_tasks.workflow_id",
            ],
            use_alter=True,
            name="fk_revision_final_task_binding",
        ),
        CheckConstraint("revision_no > 0", name="revision_no"),
        CheckConstraint(
            "(final_result_hash IS NULL) = (final_frozen_at IS NULL)",
            name="final_identity",
        ),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    workflow_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_workflows.id"), nullable=False
    )
    revision_no = Column(Integer, nullable=False)
    parent_revision_id = Column(UUID(as_uuid=True))
    reason = Column(Text, nullable=False)
    document_mode = Column(String(16), nullable=False)
    listening_pages = Column(JSONB, nullable=False, default=dict)
    materials_manifest = Column(JSONB, nullable=False, default=dict)
    rules_manifest = Column(JSONB, nullable=False)
    stage_fingerprints = Column(JSONB, nullable=False, default=dict)
    materials_hash = Column(String(64))
    materials_frozen_at = Column(DateTime(timezone=True))
    final_task_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_tasks.id", use_alter=True)
    )
    final_result_hash = Column(String(64))
    final_frozen_at = Column(DateTime(timezone=True))
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"))
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)


class ProcessingWorkflowMaterial(AuditTimes, Base):
    __tablename__ = "processing_workflow_materials"
    __table_args__ = (
        UniqueConstraint("revision_id", "kind", "upload_version"),
        UniqueConstraint("id", "revision_id", "kind"),
        CheckConstraint("kind IN ('paper','answer','audio')", name="kind"),
        CheckConstraint(
            "state IN ('reserved','uploading','validating',"
            "'ready','failed','cancelled','superseded')",
            name="state",
        ),
        CheckConstraint(
            "upload_version > 0 AND declared_size > 0", name="size_version"
        ),
        CheckConstraint(
            "state <> 'ready' OR (material_id IS NOT NULL "
            "AND actual_sha256 IS NOT NULL AND actual_size > 0)",
            name="ready",
        ),
        Index("ix_workflow_upload_recovery", "state", "lease_expires_at"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("processing_workflow_revisions.id"),
        nullable=False,
    )
    kind = Column(String(16), nullable=False)
    upload_version = Column(Integer, nullable=False)
    state = Column(String(16), nullable=False, default="reserved")
    material_id = Column(BigInteger, ForeignKey("material_sources.id"))
    original_filename = Column(String(255), nullable=False)
    declared_size = Column(BigInteger, nullable=False)
    declared_sha256 = Column(String(64))
    actual_size = Column(BigInteger)
    actual_sha256 = Column(String(64))
    failure_code = Column(String(64))
    execution_token = Column(UUID(as_uuid=True))
    lease_expires_at = Column(DateTime(timezone=True))


class ProcessingMaterialSelection(Base):
    __tablename__ = "processing_material_selections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["upload_id", "revision_id", "kind"],
            [
                "processing_workflow_materials.id",
                "processing_workflow_materials.revision_id",
                "processing_workflow_materials.kind",
            ],
            name="fk_material_selection_upload",
        ),
    )
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("processing_workflow_revisions.id"),
        primary_key=True,
    )
    kind = Column(String(16), primary_key=True)
    upload_id = Column(UUID(as_uuid=True), nullable=False)


class ProcessingWorkflowCommand(AuditTimes, Base):
    __tablename__ = "processing_workflow_commands"
    __table_args__ = (
        UniqueConstraint("created_by", "action", "idempotency_key"),
        ForeignKeyConstraint(
            ["revision_id", "workflow_id"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.workflow_id",
            ],
            name="fk_command_revision",
        ),
        CheckConstraint(
            "state IN ('accepted','running','waiting',"
            "'succeeded','failed','conflict','stopped')",
            name="state",
        ),
        Index("ix_workflow_command_poll", "state", "created_at", "id"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    workflow_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_workflows.id"), nullable=False
    )
    revision_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(64), nullable=False)
    idempotency_key = Column(UUID(as_uuid=True), nullable=False)
    request_hash = Column(String(64), nullable=False)
    request = Column(JSONB, nullable=False)
    expected_workflow_version = Column(Integer)
    state = Column(String(16), nullable=False)
    result = Column(JSONB, nullable=False, default=dict)
    failure_code = Column(String(64))
    execution_token = Column(UUID(as_uuid=True))
    lease_expires_at = Column(DateTime(timezone=True))
    retry_of_operation_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_workflow_commands.id")
    )
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)


class ProcessingStageApproval(Base):
    __tablename__ = "processing_stage_approvals"
    id = Column(UUID(as_uuid=True), primary_key=True)
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("processing_workflow_revisions.id"),
        nullable=False,
        index=True,
    )
    stage = Column(String(32), nullable=False)
    artifact_hash = Column(String(64), nullable=False)
    dependency_hash = Column(String(64), nullable=False)
    decision = Column(String(16), nullable=False)
    items = Column(JSONB, nullable=False)
    reused_approval_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_stage_approvals.id")
    )
    operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingReviewSession(AuditTimes, Base):
    __tablename__ = "processing_review_sessions"
    __table_args__ = (
        UniqueConstraint("revision_id", "result_hash"),
        UniqueConstraint("id", "revision_id", "result_hash"),
        ForeignKeyConstraint(
            ["revision_id", "result_hash"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.final_result_hash",
            ],
            name="fk_review_session_final_result",
        ),
        CheckConstraint("state IN ('draft','returned','approved')", name="state"),
        CheckConstraint("row_version > 0", name="row_version"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("processing_workflow_revisions.id"),
        nullable=False,
    )
    result_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False, default="draft")
    row_version = Column(Integer, nullable=False, default=1)
    submitted_by = Column(BigInteger, ForeignKey("users.id"))
    submitted_at = Column(DateTime(timezone=True))


class ProcessingReviewItem(Base):
    __tablename__ = "processing_review_items"
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("processing_review_sessions.id"),
        primary_key=True,
    )
    question_src_id = Column(String(128), primary_key=True)
    decisions = Column(JSONB, nullable=False)
    note = Column(Text, nullable=False)
    issues = Column(JSONB, nullable=False, default=list)
    operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingWorkflowEvent(Base):
    __tablename__ = "processing_workflow_events"
    __table_args__ = (
        Index("ix_workflow_event_cursor", "workflow_id", "created_at", "id"),
    )
    id = Column(BigInteger, primary_key=True)
    workflow_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_workflows.id"), nullable=False
    )
    revision_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_workflow_revisions.id")
    )
    task_id = Column(UUID(as_uuid=True), ForeignKey("processing_tasks.id"))
    command_id = Column(
        UUID(as_uuid=True), ForeignKey("processing_workflow_commands.id")
    )
    event_type = Column(String(64), nullable=False)
    detail = Column(JSONB, nullable=False)
    operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
