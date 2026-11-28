"""Local assembly bridges audited saves into the existing review/import path."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.db import models_library as l
from app.db import models_processing_workflows as m
from app.module3.contracts import fingerprint, result_hash
from app.services.processing import library_content as c
from app.services.processing import library_editing as e
from app.services.processing import orchestration as o
from app.services.processing import tasks
from app.services.processing import workflows as w
from app.services.processing.source_review import listening_review_satisfied


def local_task(db, workflow, revision, source, user_id, snapshot):
    parent = tasks.get_task(db, UUID(source["task_id"]))
    task = tasks.child_task(db, parent, user_id, state="completed")
    task.workflow_id, task.revision_id = workflow.id, revision.id
    task.stage = "local_library_assembly"
    task.method = {
        **task.method,
        "local_execution": "library.assembly.v1",
        "rules_manifest": revision.rules_manifest,
    }
    task.method_hash = fingerprint(task.method)
    task.input_hash = fingerprint({"snapshot": snapshot, "method": task.method_hash})
    workflow.current_task_id = task.id
    db.flush()
    return task


def prepare(db, workflow_id, payload, user_id, key, settings, *, final=False):
    action = "library_prepare_review" if final else "library_prepare_source"
    old, digest, body = w.begin_command(db, user_id, action, key, workflow_id, payload)
    if old:
        return old
    paper, workflow, head, current, snapshot = e.context(db, workflow_id, lock=True)
    e.available(db, workflow, paper)
    e.preconditions(head, snapshot, payload)
    if not current:
        raise w.conflict("SAVE_REQUIRED", "请先明确保存当前草稿")
    revision = db.get(m.ProcessingWorkflowRevision, head.revision_id)
    if revision.final_frozen_at:
        raise w.conflict("REVIEW_EXISTS", "当前版本已进入最终审核，请继续现有审核")
    original, source_projection = o.stage_payload(db, revision, "source", settings)
    # Verify original bytes and actual alignment; editing never manufactures times.
    source_task = tasks.get_task(db, UUID(source_projection["task_id"]))
    for material in tasks.task_materials(db, source_task.id):
        tasks.verify_material(material, settings)
    aligned, _ = o.stage_payload(db, revision, "align", settings)
    alignment = {r["_src_id"]: r for r in aligned["segments"]}
    for segment in snapshot["transcript_segments"]:
        proof = alignment.get(segment["_src_id"])
        if not proof or any(
            segment.get(k) != proof.get(k)
            for k in ("text", "start_ms", "end_ms", "segment_type", "speaker_code")
        ):
            raise w.conflict(
                "ALIGNMENT_REQUIRED",
                "正文或分句须先取得同源实际对齐",
                segment_src_id=segment["_src_id"],
            )
    baseline = {
        **head.baseline,
        "audio": original["audio"],
        "source_materials": original.get("source_materials", []),
        "rules_manifest": revision.rules_manifest,
    }
    content = c.build_payload(snapshot, baseline, save_version_id=current.id)
    content["generation_receipts"] = []
    content["library_provenance"].update(
        content_hash=current.content_hash,
        origin_type=current.origin_type,
        baseline_manifest=head.baseline_manifest,
    )
    issues = c.validate_snapshot(snapshot, baseline, source_task.request)
    if not final:
        issues = [
            i
            for i in issues
            if i["issue_code"]
            not in {
                "PRIMARY_SKILL_MISSING",
                "ANSWER_EVIDENCE_MISSING",
                "DISTRACTOR_ASSESSMENT_MISSING",
                "SKILL_EVIDENCE_MISSING",
                "CANDIDATE_UNRESOLVED",
            }
        ]
    if issues:
        raise w.conflict(
            "LIBRARY_INCOMPLETE", "当前内容存在待补齐或复核问题", issues=issues[:30]
        )
    if final:
        source_content, source_projection = o.stage_payload(
            db, revision, "source", settings
        )
        if any(
            c.canonical_snapshot(c.projection(source_content))[k] != content[k]
            for k in c.SOURCE_SECTIONS
        ):
            raise w.conflict(
                "SOURCE_REVIEW_REQUIRED", "内容变化后须重新组装来源并实际核听确认"
            )
        approval = db.scalar(
            select(m.ProcessingStageApproval)
            .where(
                m.ProcessingStageApproval.revision_id == revision.id,
                m.ProcessingStageApproval.stage == "source",
                m.ProcessingStageApproval.dependency_hash
                == source_projection["dependency_hash"],
            )
            .order_by(m.ProcessingStageApproval.created_at.desc())
            .limit(1)
        )
        if not listening_review_satisfied(approval, settings):
            raise w.conflict("SOURCE_REVIEW_REQUIRED", "须先完成来源及实际核听审核")
    task = local_task(db, workflow, revision, source_projection, user_id, snapshot)
    from app.module3.workflow_worker import record_artifact

    stage = "final" if final else "source"
    artifact = record_artifact(db, None, task, stage, content, settings)
    projection = {
        "task_id": str(task.id),
        "artifact_id": artifact.id,
        "artifact_hash": artifact.artifact_hash,
        "dependency_hash": fingerprint(
            {
                "content": artifact.artifact_hash,
                "materials": revision.materials_hash,
                "rules": revision.rules_manifest["manifest_hash"],
            }
        ),
    }
    revision.stage_fingerprints = {**revision.stage_fingerprints, stage: projection}
    if final:
        tasks.store_draft(db, task, content, view="final")
        revision.final_task_id, revision.final_result_hash, revision.final_frozen_at = (
            task.id,
            result_hash(content),
            tasks.utcnow(),
        )
        db.flush()
        session = m.ProcessingReviewSession(
            id=uuid4(),
            revision_id=revision.id,
            result_hash=revision.final_result_hash,
            state="draft",
            row_version=1,
        )
        db.add(session)
        db.add(
            l.LibraryVersionReference(
                save_version_id=current.id, kind="review", reference=str(session.id)
            )
        )
        workflow.processing_state = "awaiting_review"
        workflow.content_review_state = workflow.error_review_state = "pending"
    else:
        workflow.processing_state = "awaiting_source"
    workflow.row_version += 1
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        action,
        key,
        digest,
        body,
        {
            "save_version_id": str(current.id),
            "stage": stage,
            "row_version": workflow.row_version,
        },
    )


def validate_final(db, payload, request, revision, settings, *, allow_incomplete=False):
    identity = payload.get("library_provenance", {})
    if identity.get("contract") != "library.v1":
        raise w.conflict("PROVENANCE_INVALID", "新编辑结果缺少真实保存来源")
    version = db.get(l.LibrarySaveVersion, UUID(identity["save_version_id"]))
    if not version or version.revision_id != revision.id or version.snapshot_pruned_at:
        raise w.conflict("PROVENANCE_INVALID", "保存来源与当前冻结修订不匹配")
    head = db.get(l.LibraryEditHead, version.exam_paper_id)
    rebuilt = e.reconstruct(db, head, version)
    if fingerprint(rebuilt) != identity.get("content_hash"):
        raise w.conflict("PROVENANCE_INVALID", "人工修订链或内容哈希不匹配")
    expected = c.build_payload(
        rebuilt, version.source_context, save_version_id=version.id
    )
    for section in c.SECTIONS:
        if expected[section] != payload[section]:
            raise w.conflict(
                "PROVENANCE_INVALID", "最终内容无法由真实来源重建", section=section
            )
    source, _source_projection = o.stage_payload(db, revision, "source", settings)
    if any(
        c.canonical_snapshot(c.projection(source))[k] != payload[k]
        for k in c.SOURCE_SECTIONS
    ) or any(source[k] != payload[k] for k in ("audio", "source_materials")):
        raise w.conflict("PROVENANCE_INVALID", "最终来源与实际审核来源不匹配")
    if payload.get("generation_receipts"):
        raise w.conflict("PROVENANCE_INVALID", "人工编辑不能伪装模型回执")
    # The original AI baseline is independently revalidated with the legacy strict
    # validator. Subsequent human differences are checked through the audit chain.
    baseline = head.baseline_manifest
    if baseline.get("type") == "AI":
        parent = db.get(
            m.ProcessingWorkflowRevision, UUID(baseline["parent_revision_id"])
        )
        original, _ = o.stage_payload(db, parent, "final", settings)
        parent_task = tasks.get_task(db, parent.final_task_id)
        from app.services.processing.reviewing import validate_final as validate_origin

        validate_origin(db, original, parent_task.request, parent, settings)
    audits = db.scalars(
        select(l.LibraryEditChange)
        .join(
            l.LibrarySaveVersion,
            l.LibrarySaveVersion.id == l.LibraryEditChange.save_version_id,
        )
        .where(
            l.LibrarySaveVersion.exam_paper_id == version.exam_paper_id,
            l.LibrarySaveVersion.version_no <= version.version_no,
        )
        .order_by(l.LibrarySaveVersion.version_no)
    ).all()
    from app.services.processing.library_candidates import verify_receipt

    state = c.canonical_snapshot(c.projection(head.baseline))
    for audit in audits:
        for candidate_id in audit.provenance.get("candidate_ids", []):
            candidate = db.get(l.AnnotationCandidate, UUID(candidate_id))
            question = next(
                q
                for q in state["questions"]
                if q["_src_id"] == candidate.question_src_id
            )
            verify_receipt(
                db, candidate, {**head.baseline, **state}, question, settings
            )
        state = c.apply_changes(state, audit.changes)
    issues = c.validate_snapshot(rebuilt, version.source_context, request)
    if allow_incomplete:
        issues = [i for i in issues if i["issue_code"] != "CANDIDATE_UNRESOLVED"]
    if issues:
        raise w.conflict("LIBRARY_INCOMPLETE", "最终版本存在缺项", issues=issues[:30])
