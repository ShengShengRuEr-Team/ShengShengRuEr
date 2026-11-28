"""Shared edit heads, immutable saves and independent model candidates."""

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


class LibrarySaveVersion(Base):
    __tablename__ = "library_save_versions"
    __table_args__ = (
        UniqueConstraint("id", "exam_paper_id", "workflow_id"),
        UniqueConstraint("exam_paper_id", "version_no"),
        ForeignKeyConstraint(
            ["workflow_id", "exam_paper_id"],
            ["processing_workflows.id", "processing_workflows.exam_paper_id"],
            name="fk_library_save_paper_workflow",
        ),
        ForeignKeyConstraint(
            ["revision_id", "workflow_id"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.workflow_id",
            ],
            name="fk_library_save_revision",
        ),
        ForeignKeyConstraint(
            ["parent_version_id", "exam_paper_id", "workflow_id"],
            [
                "library_save_versions.id",
                "library_save_versions.exam_paper_id",
                "library_save_versions.workflow_id",
            ],
            name="fk_library_save_parent",
        ),
        CheckConstraint("version_no > 0", name="version_positive"),
        CheckConstraint("origin_type IN ('AI','MANUAL','MIXED')", name="origin"),
        Index("ix_library_save_retention", "unprotected_at"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    exam_paper_id = Column(BigInteger, ForeignKey("exam_papers.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    revision_id = Column(UUID(as_uuid=True), nullable=False)
    version_no = Column(Integer, nullable=False)
    parent_version_id = Column(UUID(as_uuid=True))
    restored_from_version_id = Column(
        UUID(as_uuid=True), ForeignKey("library_save_versions.id")
    )
    reason = Column(Text, nullable=False)
    actor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    saved_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    origin_type = Column(String(16), nullable=False)
    before_hash = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    snapshot = Column(JSONB(none_as_null=True))
    diff_summary = Column(JSONB, nullable=False)
    dependency_manifest = Column(JSONB, nullable=False)
    source_context = Column(JSONB, nullable=False, default=dict, server_default="{}")
    unprotected_at = Column(DateTime(timezone=True))
    snapshot_pruned_at = Column(DateTime(timezone=True))


class LibraryEditHead(Base):
    __tablename__ = "library_edit_heads"
    __table_args__ = (
        UniqueConstraint("workflow_id"),
        ForeignKeyConstraint(
            ["workflow_id", "exam_paper_id"],
            ["processing_workflows.id", "processing_workflows.exam_paper_id"],
            name="fk_library_head_paper_workflow",
        ),
        ForeignKeyConstraint(
            ["revision_id", "workflow_id"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.workflow_id",
            ],
            name="fk_library_head_revision",
        ),
        ForeignKeyConstraint(
            ["current_save_version_id", "exam_paper_id", "workflow_id"],
            [
                "library_save_versions.id",
                "library_save_versions.exam_paper_id",
                "library_save_versions.workflow_id",
            ],
            name="fk_library_head_save",
        ),
        CheckConstraint("row_version > 0", name="row_version"),
    )
    exam_paper_id = Column(BigInteger, ForeignKey("exam_papers.id"), primary_key=True)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    revision_id = Column(UUID(as_uuid=True), nullable=False)
    current_save_version_id = Column(UUID(as_uuid=True))
    row_version = Column(Integer, nullable=False, default=1)
    # Baseline is retained independently of expiring recovery snapshots.
    baseline = Column(JSONB, nullable=False)
    baseline_manifest = Column(JSONB, nullable=False)


class LibraryEditChange(Base):
    __tablename__ = "library_edit_changes"
    __table_args__ = (UniqueConstraint("save_version_id", "sequence_no"),)
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    save_version_id = Column(
        UUID(as_uuid=True), ForeignKey("library_save_versions.id"), nullable=False
    )
    sequence_no = Column(Integer, nullable=False)
    changes = Column(JSONB, nullable=False)
    provenance = Column(JSONB, nullable=False)
    parent_hash = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    actor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LibraryVersionReference(Base):
    __tablename__ = "library_version_references"
    __table_args__ = (UniqueConstraint("save_version_id", "kind", "reference"),)
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    save_version_id = Column(
        UUID(as_uuid=True), ForeignKey("library_save_versions.id"), nullable=False
    )
    kind = Column(String(32), nullable=False)
    reference = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_at = Column(DateTime(timezone=True))


class LibraryRetentionEvent(Base):
    __tablename__ = "library_retention_events"
    id = Column(UUID(as_uuid=True), primary_key=True)
    save_version_id = Column(
        UUID(as_uuid=True), ForeignKey("library_save_versions.id"), nullable=False
    )
    state = Column(String(32), nullable=False)
    detail = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnnotationCandidate(Base):
    __tablename__ = "processing_annotation_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "workflow_id"],
            [
                "processing_workflow_revisions.id",
                "processing_workflow_revisions.workflow_id",
            ],
            name="fk_library_candidate_revision",
        ),
        UniqueConstraint("revision_id", "question_src_id", "candidate_hash"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    revision_id = Column(UUID(as_uuid=True), nullable=False)
    question_src_id = Column(String(255), nullable=False)
    method_hash = Column(String(64), nullable=False)
    dependency_hash = Column(String(64), nullable=False)
    candidate_hash = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    receipt = Column(JSONB, nullable=False)
    validation = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
