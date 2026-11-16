"""Transactional workflow commands with replay before business preconditions.

PostgreSQL transaction advisory locks serialize the idempotency namespace and
the natural paper identity. They also close the race where two different keys
both try to create the first workflow for a previously unknown paper.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text

from app.core.errors import AppError, not_found
from app.db import models_processing_workflows as m
from app.db.models_listening import ExamPaper
from app.module3.annotation_identity import request_hash, rules_manifest
from app.module3.contracts import fingerprint
from app.repositories import listening

MATERIAL_KINDS = ("paper", "answer", "audio")


def conflict(code, message, **context):
    return AppError(409, message, error_code=code, context=context or None)


def advisory_lock(db, namespace):
    digest = bytes.fromhex(fingerprint(namespace))[:8]
    key = int.from_bytes(digest, "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def command_by_key(db, user_id, action, key):
    return db.scalar(
        select(m.ProcessingWorkflowCommand).where(
            m.ProcessingWorkflowCommand.created_by == user_id,
            m.ProcessingWorkflowCommand.action == action,
            m.ProcessingWorkflowCommand.idempotency_key == key,
        )
    )


def command_data(command):
    return {
        "operation_id": command.id,
        "workflow_id": command.workflow_id,
        "revision_id": command.revision_id,
        "action": command.action,
        "state": command.state,
        "failure_code": command.failure_code,
        "result": command.result,
        "created_at": command.created_at,
    }


def begin_command(db, user_id, action, key, target, payload):
    body = payload.model_dump(mode="json")
    digest = request_hash(action, str(target) if target else None, body)
    advisory_lock(db, ["workflow-command", user_id, action, str(key)])
    command = command_by_key(db, user_id, action, key)
    if command and command.request_hash != digest:
        raise conflict("IDEMPOTENCY_CONFLICT", "该操作键已用于不同请求，请核对原操作")
    return command, digest, body


def get_workflow(db, workflow_id, *, lock=False):
    stmt = select(m.ProcessingWorkflow).where(m.ProcessingWorkflow.id == workflow_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt.execution_options(populate_existing=True))
    if row is None:
        raise not_found("处理工作流不存在")
    return row


def locked_current(db, workflow_id, payload):
    # Reading the pointer before locking is safe: after the paper lock, re-read
    # the workflow under a row lock and validate the original preconditions.
    workflow = get_workflow(db, workflow_id)
    if workflow.exam_paper_id:
        db.execute(
            select(ExamPaper.id)
            .where(ExamPaper.id == workflow.exam_paper_id)
            .with_for_update()
        )
    workflow = get_workflow(db, workflow_id, lock=True)
    if (
        workflow.row_version != payload.expected_workflow_version
        or workflow.current_revision_id != payload.expected_revision_id
    ):
        raise conflict(
            "VERSION_CONFLICT",
            "工作流已更新，请保留输入并刷新核对",
            row_version=workflow.row_version,
            revision_id=str(workflow.current_revision_id),
        )
    revision = db.scalar(
        select(m.ProcessingWorkflowRevision)
        .where(m.ProcessingWorkflowRevision.id == workflow.current_revision_id)
        .with_for_update()
    )
    return workflow, revision


def add_event(db, workflow, revision, command, user_id, event_type, detail):
    db.add(
        m.ProcessingWorkflowEvent(
            workflow_id=workflow.id,
            revision_id=revision.id,
            command_id=command.id,
            operator_user_id=user_id,
            event_type=event_type,
            detail=detail,
        )
    )


def finish_command(
    db,
    workflow,
    revision,
    user_id,
    action,
    key,
    digest,
    body,
    result,
    *,
    state="succeeded",
    retry_of_operation_id=None,
):
    command = m.ProcessingWorkflowCommand(
        id=uuid4(),
        workflow_id=workflow.id,
        revision_id=revision.id,
        action=action,
        idempotency_key=key,
        request_hash=digest,
        request=body,
        expected_workflow_version=body.get("expected_workflow_version"),
        state=state,
        result=result,
        retry_of_operation_id=retry_of_operation_id,
        created_by=user_id,
    )
    db.add(command)
    db.flush()
    add_event(db, workflow, revision, command, user_id, action, result)
    db.commit()
    return command


def create_workflow(db, payload, user_id, key):
    old, digest, body = begin_command(db, user_id, "create", key, None, payload)
    if old:
        return old
    identity = {
        name: body[name]
        for name in ("exam_level", "exam_year", "exam_month", "paper_set")
    }
    identity["content_scope"] = "listening"
    advisory_lock(db, ["paper-identity", identity])
    papers = db.scalars(
        select(ExamPaper).filter_by(**identity).order_by(ExamPaper.id).with_for_update()
    ).all()
    if len(papers) > 1:
        raise AppError(
            422,
            "同一考试身份存在多份试卷，须先核对来源编码",
            error_code="PAPER_IDENTITY_CONFLICT",
            context={"exam_paper_ids": [p.id for p in papers]},
        )
    existing = db.scalar(select(m.ProcessingWorkflow).filter_by(**identity))
    if existing:
        raise conflict(
            "PAPER_IDENTITY_CONFLICT",
            "该考试已有工作流，请继续或创建子修订",
            workflow_id=str(existing.id),
        )
    workflow = m.ProcessingWorkflow(
        id=uuid4(),
        **identity,
        exam_paper_id=papers[0].id if papers else None,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(workflow)
    db.flush()
    revision = m.ProcessingWorkflowRevision(
        id=uuid4(),
        workflow_id=workflow.id,
        revision_no=1,
        reason="创建工作流",
        document_mode=payload.document_mode,
        listening_pages=body["listening_pages"],
        rules_manifest=rules_manifest(),
        created_by=user_id,
    )
    db.add(revision)
    db.flush()
    workflow.current_revision_id = revision.id
    return finish_command(
        db,
        workflow,
        revision,
        user_id,
        "create",
        key,
        digest,
        body,
        {
            "workflow_id": str(workflow.id),
            "revision_id": str(revision.id),
            "row_version": workflow.row_version,
        },
    )


def create_revision(db, workflow_id, payload, user_id, key):
    old, digest, body = begin_command(
        db, user_id, "create_revision", key, workflow_id, payload
    )
    if old:
        return old
    workflow, parent = locked_current(db, workflow_id, payload)
    if workflow.processing_state in {"queued", "running", "stopping"}:
        raise conflict("WORKFLOW_BUSY", "请先停止当前执行，再替换材料")
    if workflow.publication_state in {
        "preparing",
        "pending_batch",
        "validating",
        "activating",
    }:
        raise conflict("WORKFLOW_BUSY", "请先核对当前发布操作")
    revision = copy_revision(
        db,
        workflow,
        parent,
        user_id,
        payload.reason,
        payload.document_mode,
        body["listening_pages"],
    )
    return finish_command(
        db,
        workflow,
        revision,
        user_id,
        "create_revision",
        key,
        digest,
        body,
        {
            "workflow_id": str(workflow.id),
            "revision_id": str(revision.id),
            "row_version": workflow.row_version,
        },
    )


def copy_revision(
    db, workflow, parent, user_id, reason, document_mode, listening_pages
):
    revision = m.ProcessingWorkflowRevision(
        id=uuid4(),
        workflow_id=workflow.id,
        revision_no=parent.revision_no + 1,
        parent_revision_id=parent.id,
        reason=reason,
        document_mode=document_mode,
        listening_pages=listening_pages,
        rules_manifest=rules_manifest(),
        created_by=user_id,
    )
    db.add(revision)
    db.flush()
    # Copy only verified original-material references. Never inherit an upload
    # receiver, immutable final result, review session or previous approvals.
    selected = (
        db.execute(
            select(m.ProcessingWorkflowMaterial)
            .join(
                m.ProcessingMaterialSelection,
                m.ProcessingMaterialSelection.upload_id
                == m.ProcessingWorkflowMaterial.id,
            )
            .where(m.ProcessingMaterialSelection.revision_id == parent.id)
        )
        .scalars()
        .all()
    )
    for source in selected:
        if source.state != "ready":
            continue
        if source.kind == "paper" and parent.document_mode != revision.document_mode:
            continue
        material = m.ProcessingWorkflowMaterial(
            id=uuid4(),
            revision_id=revision.id,
            kind=source.kind,
            upload_version=1,
            state="ready",
            material_id=source.material_id,
            original_filename=source.original_filename,
            declared_size=source.actual_size,
            declared_sha256=source.actual_sha256,
            actual_size=source.actual_size,
            actual_sha256=source.actual_sha256,
        )
        db.add(material)
        db.flush()
        db.add(
            m.ProcessingMaterialSelection(
                revision_id=revision.id,
                kind=source.kind,
                upload_id=material.id,
            )
        )
    workflow.current_revision_id = revision.id
    workflow.current_task_id = None
    workflow.row_version += 1
    workflow.updated_by = user_id
    workflow.updated_at = func.now()
    workflow.processing_state = "awaiting_materials"
    workflow.content_review_state = "not_ready"
    workflow.error_review_state = "not_ready"
    workflow.publication_state = "unpublished"
    db.flush()
    return revision


def workflow_data(db, workflow):
    revision = db.get(m.ProcessingWorkflowRevision, workflow.current_revision_id)
    rows = db.scalars(
        select(m.ProcessingWorkflowMaterial)
        .join(
            m.ProcessingMaterialSelection,
            m.ProcessingMaterialSelection.upload_id == m.ProcessingWorkflowMaterial.id,
        )
        .where(m.ProcessingMaterialSelection.revision_id == revision.id)
    ).all()
    uploads = {r.kind: r for r in rows}
    from decimal import Decimal

    from app.core.config import get_settings
    from app.db.models_processing import LlmAttempt, ProcessingTask
    from app.services.processing.orchestration import environment_ready
    from app.services.processing.progress import workflow_progress

    task = (
        db.get(ProcessingTask, workflow.current_task_id)
        if workflow.current_task_id
        else None
    )
    session = db.scalar(
        select(m.ProcessingReviewSession).where(
            m.ProcessingReviewSession.revision_id == revision.id
        )
    )
    approvals = db.scalars(
        select(m.ProcessingStageApproval)
        .where(m.ProcessingStageApproval.revision_id == revision.id)
        .order_by(
            m.ProcessingStageApproval.created_at.desc(),
            m.ProcessingStageApproval.id.desc(),
        )
    ).all()
    latest_gates = {}
    for approval in approvals:
        latest_gates.setdefault(approval.stage, approval)
    attempts = db.scalars(
        select(LlmAttempt)
        .join(ProcessingTask, ProcessingTask.id == LlmAttempt.task_id)
        .where(ProcessingTask.workflow_id == workflow.id)
    ).all()
    usage = {
        "known_usd": str(
            sum((row.charged_usd or Decimal(0) for row in attempts), Decimal(0))
        ),
        "reserved_usd": str(
            sum(
                (row.reserved_usd for row in attempts if row.charged_usd is None),
                Decimal(0),
            )
        ),
        "has_unknown_charges": any(row.billing_status == "unknown" for row in attempts),
    }
    batch = (
        listening.get_current_batch(db, workflow.exam_paper_id)
        if workflow.exam_paper_id
        else None
    )
    visible = (
        listening.student_access(db, workflow.exam_paper_id)[0] if batch else False
    )
    now = db.scalar(select(func.now()))
    materials = []
    for kind in MATERIAL_KINDS:
        row = uploads.get(kind)
        materials.append(
            {
                "kind": kind,
                "upload_id": row.id if row else None,
                "upload_version": row.upload_version if row else 0,
                "state": row.state if row else "missing",
                "material_id": row.material_id if row else None,
                "lease_expired": bool(
                    row and row.lease_expires_at and row.lease_expires_at <= now
                ),
                "failure_code": row.failure_code if row else None,
                "filename": row.original_filename if row else None,
            }
        )
    return {
        "workflow_id": workflow.id,
        "revision_id": revision.id,
        "row_version": workflow.row_version,
        "task_id": workflow.current_task_id,
        "result_hash": revision.final_result_hash,
        "current_batch_id": batch.id if batch else None,
        "is_student_visible": visible,
        "usage": usage,
        "stages": revision.stage_fingerprints,
        "review_session_id": session.id if session else None,
        "review_session_version": session.row_version if session else None,
        **{
            key: getattr(workflow, key)
            for key in (
                "exam_level",
                "exam_year",
                "exam_month",
                "paper_set",
                "exam_paper_id",
                "processing_state",
                "content_review_state",
                "error_review_state",
                "publication_state",
            )
        },
        "document_mode": revision.document_mode,
        "listening_pages": revision.listening_pages,
        "materials": materials,
        "error_generation_summary": {},
        "progress": workflow_progress(
            db, workflow, task, materials, now, get_settings(), revision
        ),
        "gates": [
            {
                "kind": stage,
                "state": latest_gates[stage].decision
                if stage in latest_gates
                else "pending",
                "dependency_hash": projection["dependency_hash"],
            }
            for stage, projection in revision.stage_fingerprints.items()
            if stage in {"align", "source", "sample"}
        ],
        "issues": [
            {
                "code": issue.get("issue_code", "PROCESSING_FAILED"),
                "message": issue.get("message", "阶段未完成"),
                "retryable": issue.get("retryable", False),
            }
            for issue in task.issues
            if issue.get("issue_code") != "DOWNSTREAM_SCOPE_STOP"
        ]
        if task
        else [],
        "allowed_actions": [
            {
                "action": "reserve_upload",
                "enabled": revision.materials_frozen_at is None,
                "blocked_reason": "材料已冻结，请创建子修订"
                if revision.materials_frozen_at
                else None,
            },
            {
                "action": "start",
                "enabled": (
                    not revision.materials_frozen_at
                    and all(row["state"] == "ready" for row in materials)
                    and environment_ready(get_settings())
                ),
                "blocked_reason": "须备齐三份材料并配置处理环境",
            },
        ],
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }


def decode_cursor(cursor):
    try:
        stamp, identity = cursor.split("|", 1)
        parsed = datetime.fromisoformat(stamp)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC), UUID(identity)
    except (ValueError, AttributeError) as error:
        raise AppError(422, "分页游标无效") from error


def cursor_page(db, stmt, model, limit, cursor=None):
    if cursor:
        stamp, identity = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                model.created_at < stamp,
                and_(
                    model.created_at == stamp,
                    model.id < identity,
                ),
            )
        )
    rows = db.scalars(
        stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    next_cursor = (
        f"{page[-1].created_at.isoformat()}|{page[-1].id}"
        if len(rows) > limit
        else None
    )
    return page, next_cursor
