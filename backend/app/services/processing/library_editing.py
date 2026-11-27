"""Transactional library writes; no save operation starts inference."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import not_found
from app.db import models_library as l
from app.db import models_processing_workflows as m
from app.db.models_listening import ExamPaper
from app.module3.annotation_identity import rules_manifest
from app.module3.contracts import fingerprint
from app.module3.providers import freeze
from app.services.processing import library_content as c
from app.services.processing import workflows as w


def request_for(paper, baseline):
    return {
        "expected_question_count": paper.expected_question_count,
        "expected_question_count_source": paper.expected_question_count_source,
        "material_ids": [
            r["material_id"] for r in baseline.get("source_materials", [])
        ],
    }


def paper_lock(db, paper_id):
    paper = db.scalar(
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not paper:
        raise not_found("试卷不存在")
    return paper


def available(db, workflow, paper):
    if paper.archived_at:
        raise w.conflict("PAPER_ARCHIVED", "请先在回收站恢复试卷")
    active = db.scalar(
        select(m.ProcessingWorkflowCommand.id)
        .where(
            m.ProcessingWorkflowCommand.workflow_id == workflow.id,
            m.ProcessingWorkflowCommand.state.in_(["accepted", "running"]),
        )
        .limit(1)
    )
    if active or workflow.processing_state in {"queued", "running", "stopping"}:
        raise w.conflict(
            "WORKFLOW_BUSY",
            "请先停止并等待任务结束",
            operation_id=str(active) if active else None,
        )
    if workflow.publication_state in {
        "preparing",
        "pending_batch",
        "validating",
        "activating",
    }:
        raise w.conflict("WORKFLOW_BUSY", "请先核对发布操作")


def context(db, workflow_id, *, lock=False):
    workflow = w.get_workflow(db, workflow_id)
    if not workflow.exam_paper_id:
        raise w.conflict(
            "EDIT_HEAD_REQUIRED", "当前流程尚未登记稳定试卷，请完成来源组装"
        )
    paper = (
        paper_lock(db, workflow.exam_paper_id)
        if lock
        else db.get(ExamPaper, workflow.exam_paper_id)
    )
    if lock:
        workflow = w.get_workflow(db, workflow_id, lock=True)
    stmt = select(l.LibraryEditHead).where(l.LibraryEditHead.workflow_id == workflow_id)
    head = db.scalar(
        (stmt.with_for_update() if lock else stmt).execution_options(
            populate_existing=True
        )
    )
    if not head:
        raise w.conflict("EDIT_HEAD_REQUIRED", "请先打开唯一编辑草稿")
    current = (
        db.get(l.LibrarySaveVersion, head.current_save_version_id)
        if head.current_save_version_id
        else None
    )
    snapshot = deepcopy(
        current.snapshot
        if current
        else c.canonical_snapshot(c.projection(head.baseline))
    )
    if snapshot is None:
        raise w.conflict("SNAPSHOT_UNAVAILABLE", "当前保存快照不可恢复")
    return paper, workflow, head, current, snapshot


def preconditions(head, snapshot, payload):
    digest = fingerprint(snapshot)
    if (
        head.row_version != payload.expected_row_version
        or digest != payload.expected_content_hash
    ):
        raise w.conflict(
            "VERSION_CONFLICT",
            "草稿已更新，请保留本地内容并查看最新差异",
            row_version=head.row_version,
            content_hash=digest,
            save_version_id=str(head.current_save_version_id)
            if head.current_save_version_id
            else None,
        )


def draft_data(db, workflow_id):
    paper, workflow, head, current, snapshot = context(db, workflow_id)
    issues = c.validate_snapshot(
        deepcopy(snapshot), head.baseline, request_for(paper, head.baseline)
    )
    return {
        "exam_paper_id": paper.id,
        "workflow_id": str(workflow.id),
        "revision_id": str(head.revision_id),
        "row_version": head.row_version,
        "paper_row_version": paper.library_row_version,
        "save_version_id": str(current.id) if current else None,
        "version_no": current.version_no if current else 0,
        "content_hash": fingerprint(snapshot),
        "snapshot": snapshot,
        "issues": issues,
        "archived": paper.archived_at is not None,
        "dependency_manifest": c.dependency_manifest(snapshot, head.baseline),
        "workflow_contract": db.get(
            m.ProcessingWorkflowRevision, head.revision_id
        ).workflow_contract,
        "source_materials": head.baseline.get("source_materials", []),
    }


def create(db, payload, user_id, key):
    old, digest, body = w.begin_command(
        db, user_id, "library_create", key, None, payload
    )
    if old:
        return old
    identity = {
        k: body[k] for k in ("exam_level", "exam_year", "exam_month", "paper_set")
    }
    identity["content_scope"] = "listening"
    w.advisory_lock(db, ["paper-identity", identity])
    existing = db.scalars(select(ExamPaper).filter_by(**identity)).all()
    workflow = db.scalar(select(m.ProcessingWorkflow).filter_by(**identity))
    if existing or workflow:
        raise w.conflict(
            "PAPER_IDENTITY_CONFLICT",
            "同卷身份已存在，请继续已有试卷",
            exam_paper_ids=[r.id for r in existing],
            workflow_id=str(workflow.id) if workflow else None,
        )
    paper = ExamPaper(
        **identity,
        exam_paper_code=f"{payload.exam_level}-{payload.exam_year}{payload.exam_month:02d}-{payload.paper_set}",
        expected_question_count=25,
        expected_question_count_source={
            "source": "admin_original_paper",
            "locator": payload.expected_question_count_source,
            "actor_id": user_id,
        },
        source=payload.expected_question_count_source,
    )
    db.add(paper)
    db.flush()
    workflow = m.ProcessingWorkflow(
        id=uuid4(),
        **identity,
        exam_paper_id=paper.id,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(workflow)
    db.flush()
    rules = rules_manifest()
    revision = m.ProcessingWorkflowRevision(
        id=uuid4(),
        workflow_id=workflow.id,
        revision_no=1,
        reason="登记标准完整真题",
        document_mode="text",
        listening_pages={},
        materials_manifest={},
        rules_manifest=rules,
        workflow_contract="library.v1",
        method_manifest_hash=rules["manifest_hash"],
        created_by=user_id,
        origin_manifest={
            "mode": payload.mode,
            "actor_id": user_id,
            "provider_method": freeze(payload.provider, get_settings()),
        },
    )
    db.add(revision)
    db.flush()
    workflow.current_revision_id = revision.id
    baseline = {
        "schema_version": "m3.v3",
        "rules_manifest": rules,
        "source_materials": [],
        "audio": {},
        **{k: [] for k in c.SECTIONS},
    }
    db.add(
        l.LibraryEditHead(
            exam_paper_id=paper.id,
            workflow_id=workflow.id,
            revision_id=revision.id,
            row_version=1,
            baseline=baseline,
            baseline_manifest={
                "type": "MANUAL",
                "actor_id": user_id,
                "hash": fingerprint(baseline),
            },
        )
    )
    db.flush()
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "library_create",
        key,
        digest,
        body,
        {"exam_paper_id": paper.id, "workflow_id": str(workflow.id), "row_version": 1},
    )


def open_draft(db, paper_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "library_open", key, paper_id, payload
    )
    if old:
        return old
    paper = paper_lock(db, paper_id)
    if paper.library_row_version != payload.expected_row_version:
        raise w.conflict(
            "VERSION_CONFLICT", "试卷状态已更新", row_version=paper.library_row_version
        )
    identity = {
        k: getattr(paper, k)
        for k in ("exam_level", "exam_year", "exam_month", "paper_set", "content_scope")
    }
    duplicates = db.scalars(select(ExamPaper.id).filter_by(**identity)).all()
    if len(duplicates) != 1:
        raise w.conflict(
            "PAPER_IDENTITY_CONFLICT",
            "同卷身份冲突，需先核对",
            exam_paper_ids=list(duplicates),
        )
    workflow = db.scalar(
        select(m.ProcessingWorkflow).filter_by(**identity).with_for_update()
    )
    if not workflow:
        from app.services.processing.library_legacy import ensure_workflow

        workflow = ensure_workflow(db, paper, user_id)
    available(db, workflow, paper)
    head = db.get(l.LibraryEditHead, paper.id)
    if head:
        revision = db.get(m.ProcessingWorkflowRevision, head.revision_id)
    else:
        from app.services.processing import orchestration as o

        parent = db.get(m.ProcessingWorkflowRevision, workflow.current_revision_id)
        stage = next(
            (s for s in ("final", "source") if s in parent.stage_fingerprints), None
        )
        if stage:
            baseline, projection = o.stage_payload(db, parent, stage, settings)
            baseline_manifest = {
                "type": "AI" if baseline.get("generation_receipts") else "MANUAL",
                "parent_revision_id": str(parent.id),
                "artifact": projection,
                "hash": fingerprint(baseline),
            }
        else:
            from app.services.processing.library_legacy import (
                snapshot as legacy_snapshot,
            )

            baseline, baseline_manifest = legacy_snapshot(db, paper)
            projection = None
        revision = w.copy_revision(
            db,
            workflow,
            parent,
            user_id,
            payload.reason,
            parent.document_mode,
            parent.listening_pages,
        )
        revision.workflow_contract = "library.v1"
        revision.materials_manifest = deepcopy(parent.materials_manifest)
        revision.materials_hash = parent.materials_hash
        revision.materials_frozen_at = parent.materials_frozen_at
        revision.origin_manifest = {
            **revision.origin_manifest,
            "parent_revision_id": str(parent.id),
            "baseline_artifact": projection,
        }
        revision.method_manifest_hash = revision.rules_manifest["manifest_hash"]
        # Source remains immutable; final annotations are only the edit baseline.
        revision.stage_fingerprints = {
            k: v
            for k, v in parent.stage_fingerprints.items()
            if k in {"source", "align"}
        }
        head = l.LibraryEditHead(
            exam_paper_id=paper.id,
            workflow_id=workflow.id,
            revision_id=revision.id,
            row_version=1,
            baseline=deepcopy(baseline),
            baseline_manifest=baseline_manifest,
        )
        db.add(head)
        workflow.processing_state = "editing"
        paper.library_row_version += 1
        db.flush()
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "library_open",
        key,
        digest,
        body,
        {
            "workflow_id": str(workflow.id),
            "row_version": head.row_version,
            "exam_paper_id": paper.id,
        },
    )


def preview(db, workflow_id, payload):
    paper, _workflow, head, _current, before = context(db, workflow_id)
    preconditions(head, before, payload)
    after = c.canonical_snapshot(payload.snapshot)
    issues = c.validate_snapshot(
        after, head.baseline, request_for(paper, head.baseline)
    )
    changes = c.differences(before, after)
    return {
        "changes": changes,
        "impact": c.impact(changes, before, after),
        "issues": issues,
        "content_hash": fingerprint(after),
        "row_version": head.row_version,
    }


def append_save(
    db,
    paper,
    workflow,
    head,
    current,
    before,
    after,
    user_id,
    reason,
    *,
    provenance=None,
    restored_from=None,
):
    changes = c.differences(before, after)
    dependencies = c.dependency_manifest(after, head.baseline)
    if not changes and (not current or current.dependency_manifest == dependencies):
        return current, [], c.impact([], before, after)
    if not reason.strip():
        raise c.invalid("有效保存必须填写修改原因")
    revision = db.get(m.ProcessingWorkflowRevision, head.revision_id)
    # Frozen results keep their hash and task. A new edit never rewrites them.
    if revision.final_frozen_at:
        parent = revision
        revision = w.copy_revision(
            db,
            workflow,
            parent,
            user_id,
            reason,
            parent.document_mode,
            parent.listening_pages,
        )
        revision.workflow_contract = "library.v1"
        revision.materials_manifest = deepcopy(parent.materials_manifest)
        revision.materials_hash = parent.materials_hash
        revision.materials_frozen_at = parent.materials_frozen_at
        revision.origin_manifest = {
            **revision.origin_manifest,
            "parent_revision_id": str(parent.id),
        }
        revision.stage_fingerprints = {
            k: v
            for k, v in parent.stage_fingerprints.items()
            if k in {"source", "align"}
        }
        head.revision_id = revision.id
    now = datetime.now(UTC)
    origin = (
        "MIXED"
        if head.baseline.get("generation_receipts")
        or (provenance or {}).get("candidate_ids")
        else "MANUAL"
    )
    version = l.LibrarySaveVersion(
        id=uuid4(),
        exam_paper_id=paper.id,
        workflow_id=workflow.id,
        revision_id=revision.id,
        version_no=(current.version_no + 1 if current else 1),
        parent_version_id=current.id if current else None,
        restored_from_version_id=restored_from,
        reason=reason,
        actor_id=user_id,
        saved_at=now,
        origin_type=origin,
        before_hash=fingerprint(before),
        content_hash=fingerprint(after),
        snapshot=after,
        diff_summary={
            "objects": len(changes),
            "sections": sorted({r["section"] for r in changes}),
        },
        dependency_manifest=c.dependency_manifest(after, head.baseline),
        source_context={
            k: deepcopy(v) for k, v in head.baseline.items() if k not in c.SECTIONS
        },
    )
    db.add(version)
    db.flush()
    db.add(
        l.LibraryEditChange(
            save_version_id=version.id,
            sequence_no=1,
            changes=changes,
            provenance=provenance or {"type": "MANUAL"},
            parent_hash=version.before_hash,
            content_hash=version.content_hash,
            actor_id=user_id,
            reason=reason,
        )
    )
    if current and current.parent_version_id:
        previous = db.get(l.LibrarySaveVersion, current.parent_version_id)
        if previous.unprotected_at is None:
            previous.unprotected_at = now
    head.current_save_version_id, head.row_version = version.id, head.row_version + 1
    workflow.processing_state = "editing"
    workflow.content_review_state = workflow.error_review_state = "not_ready"
    workflow.publication_state = "unpublished"
    workflow.row_version += 1
    workflow.updated_by, workflow.updated_at = user_id, now
    paper.library_row_version += 1
    paper.updated_at = now
    effect = c.impact(changes, before, after)
    if effect["source_review_invalidated"]:
        revision.origin_manifest = {
            **revision.origin_manifest,
            "source_review_invalidated": True,
            "alignment_required": effect["alignment_required"]
            or revision.origin_manifest.get("alignment_required", False),
        }
    if restored_from:
        db.add(
            l.LibraryVersionReference(
                save_version_id=restored_from, kind="restore", reference=str(version.id)
            )
        )
    db.flush()
    return version, changes, effect


def save(db, workflow_id, payload, user_id, key):
    old, digest, body = w.begin_command(
        db, user_id, "library_save", key, workflow_id, payload
    )
    if old:
        return old
    paper, workflow, head, current, before = context(db, workflow_id, lock=True)
    available(db, workflow, paper)
    preconditions(head, before, payload)
    after = c.canonical_snapshot(payload.snapshot)
    issues = c.validate_snapshot(
        after, head.baseline, request_for(paper, head.baseline)
    )
    version, changes, effect = append_save(
        db, paper, workflow, head, current, before, after, user_id, payload.reason
    )
    result = {
        "save_version_id": str(version.id) if version else None,
        "version_no": version.version_no if version else 0,
        "row_version": head.row_version,
        "content_hash": fingerprint(after),
        "issues": issues,
        "impact": effect,
        "changed": bool(changes),
    }
    return w.finish_command(
        db,
        workflow,
        db.get(m.ProcessingWorkflowRevision, head.revision_id),
        user_id,
        "library_save",
        key,
        digest,
        body,
        result,
    )


def reconstruct(db, head, version):
    """Rebuild from retained provenance; this is validation, never a restore API."""
    result = c.canonical_snapshot(c.projection(head.baseline))
    rows = db.scalars(
        select(l.LibrarySaveVersion)
        .where(
            l.LibrarySaveVersion.exam_paper_id == head.exam_paper_id,
            l.LibrarySaveVersion.version_no <= version.version_no,
        )
        .order_by(l.LibrarySaveVersion.version_no)
    ).all()
    previous = None
    for row in rows:
        if row.parent_version_id != previous or row.before_hash != fingerprint(result):
            raise w.conflict("PROVENANCE_INVALID", "保存版本父哈希不匹配")
        audits = db.scalars(
            select(l.LibraryEditChange)
            .where(l.LibraryEditChange.save_version_id == row.id)
            .order_by(l.LibraryEditChange.sequence_no)
        ).all()
        for audit in audits:
            if (
                audit.parent_hash != fingerprint(result)
                or audit.actor_id != row.actor_id
                or not audit.reason.strip()
            ):
                raise w.conflict("PROVENANCE_INVALID", "人工修订来源无法重建")
            result = c.apply_changes(result, audit.changes)
            if fingerprint(result) != audit.content_hash:
                raise w.conflict("PROVENANCE_INVALID", "人工修订结果哈希不匹配")
        if fingerprint(result) != row.content_hash:
            raise w.conflict("PROVENANCE_INVALID", "保存版本无法确定性重建")
        previous = row.id
    return result


def attach_source(db, workflow, revision, content, projection, request):
    """Install a first immutable source baseline, without replacing any saved work."""
    paper = db.get(ExamPaper, workflow.exam_paper_id)
    if not paper:
        raise w.conflict("SOURCE_REQUIRED", "来源组装缺少稳定试卷身份")
    if (
        paper.expected_question_count not in {None, 25}
        or request.get("expected_question_count") != 25
    ):
        raise w.conflict("STANDARD_PAPER_REQUIRED", "新流程只支持标准完整25题真题")
    paper.expected_question_count = 25
    head = db.get(l.LibraryEditHead, paper.id)
    content = {
        **content,
        "library_alignment_basis": deepcopy(content.get("transcript_segments", [])),
    }
    if head and head.current_save_version_id:
        # Keep the editor intact. This source stays an independent stage artifact.
        head.baseline = {
            **head.baseline,
            **{k: deepcopy(v) for k, v in content.items() if k not in c.SECTIONS},
        }
        head.baseline_manifest = {
            **head.baseline_manifest,
            "latest_source_attachment": projection,
        }
        head.revision_id, head.row_version = revision.id, head.row_version + 1
        paper.library_row_version += 1
        paper.expected_question_count_source = request["expected_question_count_source"]
        return
    paper.expected_question_count_source = request["expected_question_count_source"]
    baseline = deepcopy(content)
    manifest = {"type": "SOURCE", "artifact": projection, "hash": fingerprint(baseline)}
    if head:
        head.baseline, head.baseline_manifest = baseline, manifest
        head.revision_id = revision.id
        head.row_version += 1
    else:
        db.add(
            l.LibraryEditHead(
                exam_paper_id=paper.id,
                workflow_id=workflow.id,
                revision_id=revision.id,
                row_version=1,
                baseline=baseline,
                baseline_manifest=manifest,
            )
        )
    paper.library_row_version += 1
