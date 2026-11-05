"""Short transactions for task state, fenced leases and immutable processing results."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, not_found
from app.db import models_processing as m
from app.db.models_listening import (
    ContentCheck,
    ExamPaper,
    ImportBatch,
    PaperVisibility,
)
from app.module3.contracts import (
    RULE_VERSION,
    ProcessingError,
    atomic_json,
    controlled_path,
    file_hash,
    fingerprint,
    media_type,
)
from app.module3.contracts import (
    result_hash as business_hash,
)
from app.schemas_processing import (
    ActivationRequest,
    CorrectionRequest,
    MaterialRequest,
    RetryRequest,
    ReviewRequest,
    TaskRequest,
)
from app.services.processing.validation import CONFIG_DIR, validate_result


def utcnow():
    return datetime.now(UTC)


def conflict(message: str):
    return AppError(409, message)


def get_task(db: Session, task_id, *, lock: bool = False) -> m.ProcessingTask:
    statement = select(m.ProcessingTask).where(m.ProcessingTask.id == task_id)
    if lock:
        statement = statement.with_for_update()
    task = db.scalar(statement)
    if task is None:
        raise not_found("处理任务不存在")
    return task


def register_material(
    db: Session, data: MaterialRequest, user_id: int, settings: Settings
):
    path = controlled_path(settings.m3_path("m3_materials_dir"), data.storage_key)
    if path.stat().st_size > 2 * 1024**3:
        raise ProcessingError("SOURCE_TOO_LARGE", "单材料超过2GiB限制")
    mime, digest = media_type(path), file_hash(path)
    if digest != data.expected_sha256:
        raise conflict("材料实际哈希与登记值不符")
    if (data.source_kind == "audio") != mime.startswith("audio/"):
        raise AppError(422, "材料类别与真实媒体类型不符")
    if data.source_kind == "paper_text" and mime != "application/pdf":
        raise AppError(422, "文本原卷必须为PDF")
    # Serialize registration by storage key, including different categories.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int(fingerprint(data.storage_key)[:15], 16)},
    )
    prior = db.scalars(
        select(m.MaterialSource).where(m.MaterialSource.storage_key == data.storage_key)
    ).all()
    if any(
        r.sha256 != digest or r.exam_paper_code != data.exam_paper_code for r in prior
    ):
        raise conflict("同路径材料身份已登记，不能替换内容或套别")
    for row in prior:
        if row.source_kind == data.source_kind:
            return row
    if data.derived_from_material_id:
        parent = db.get(m.MaterialSource, data.derived_from_material_id)
        if (
            parent is None
            or parent.exam_paper_code != data.exam_paper_code
            or not data.generation
        ):
            raise AppError(422, "派生材料须有同套父材料和生成条件")
    material = m.MaterialSource(
        **data.model_dump(exclude={"expected_sha256"}),
        sha256=digest,
        size_bytes=path.stat().st_size,
        media_type=mime,
        registered_by=user_id,
    )
    db.add(material)
    db.flush()
    return material


def verify_material(material: m.MaterialSource, settings: Settings):
    path = controlled_path(settings.m3_path("m3_materials_dir"), material.storage_key)
    if path.stat().st_size != material.size_bytes or file_hash(path) != material.sha256:
        raise ProcessingError("SOURCE_CHANGED", "已登记原件发生变化")
    if media_type(path) != material.media_type:
        raise ProcessingError("SOURCE_CHANGED", "已登记媒体类型发生变化")
    return path


def task_materials(db: Session, task_id):
    return db.scalars(
        select(m.MaterialSource)
        .join(m.TaskMaterial, m.TaskMaterial.material_id == m.MaterialSource.id)
        .where(m.TaskMaterial.task_id == task_id)
        .order_by(m.MaterialSource.id)
    ).all()


def create_task(db: Session, data: TaskRequest, user_id: int, settings: Settings):
    request = data.model_dump(mode="json")
    materials = db.scalars(
        select(m.MaterialSource)
        .where(m.MaterialSource.id.in_(data.material_ids))
        .order_by(m.MaterialSource.id)
    ).all()
    if len(materials) != len(data.material_ids):
        raise not_found("部分材料不存在")
    if any(r.exam_paper_code != data.exam_paper.exam_paper_code for r in materials):
        raise conflict("材料不属于同套试卷")
    for material in materials:
        verify_material(material, settings)
    paper = db.scalar(
        select(ExamPaper).where(
            ExamPaper.exam_paper_code == data.exam_paper.exam_paper_code
        )
    )
    if paper:
        for field in ("exam_level", "exam_year", "exam_month", "paper_set"):
            if getattr(paper, field) != getattr(data.exam_paper, field):
                raise conflict("试卷编码对应的身份元数据冲突")
        if (
            paper.expected_question_count
            and data.expected_question_count
            and (
                paper.expected_question_count != data.expected_question_count
                or paper.expected_question_count_source
                != request["expected_question_count_source"]
            )
        ):
            raise conflict("可信题量或来源与已冻结值冲突")
    profile_path = settings.m3_path("m3_profile_path")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if data.profile_version != profile["profile_version"]:
        raise conflict("处理profile与冻结版本不符")
    if (
        file_hash(CONFIG_DIR / "dictionary-schema.json")
        != data.dictionary_snapshot_sha256
    ):
        raise conflict("词典快照与冻结哈希不符")
    source = data.expected_question_count_source
    if source and not any(
        r.storage_key == source.document
        and r.sha256 == source.sha256
        and r.source_kind in {"paper_text", "paper_scan"}
        for r in materials
    ):
        raise conflict("题量来源须指向本任务已登记的原卷")
    kinds = {r.source_kind for r in materials}
    required = {"audio", "answer_explanation", "paper_" + data.document_mode}
    issues = [
        ProcessingError("MATERIAL_MISSING", f"缺少必需材料：{kind}").issue("registered")
        for kind in sorted(required - kinds)
    ]
    if source is None:
        issues.append(
            ProcessingError("EXPECTED_COUNT_MISSING", "尚未冻结可信题量").issue(
                "registered"
            )
        )
    method = {
        "profile": profile,
        "profile_sha256": file_hash(profile_path),
        "dictionary_sha256": data.dictionary_snapshot_sha256,
        "locks": {
            k: file_hash(CONFIG_DIR / f"requirements-{k}.lock.txt")
            for k in ("api", "asr", "ocr")
        },
        "prompt_version": "m3.annotations.v1",
        "implementation_sha256": {
            str(path.relative_to(CONFIG_DIR.parents[1])): file_hash(path)
            for folder in (
                CONFIG_DIR.parents[1] / "app/module3",
                CONFIG_DIR.parents[1] / "app/services/processing",
            )
            for path in sorted(folder.glob("*.py"))
        },
        "rule_version": RULE_VERSION,
        "sentence_tolerance_ms": settings.m3_sentence_tolerance_ms,
        "budgets_usd": {
            "sample": settings.m3_sample_budget_usd,
            "run": settings.m3_run_budget_usd,
            "total": settings.m3_total_budget_usd,
        },
    }
    task = m.ProcessingTask(
        id=uuid.uuid4(),
        exam_paper_code=data.exam_paper.exam_paper_code,
        exam_paper_id=paper.id if paper else None,
        state="awaiting_confirmation" if issues else "pending",
        stage="registered",
        input_hash=fingerprint(
            {
                "request": {k: v for k, v in request.items() if k != "material_ids"},
                "materials": sorted((r.source_kind, r.sha256) for r in materials),
                "method": method,
            }
        ),
        method_hash=fingerprint(method),
        method=method,
        request=request,
        created_by=user_id,
        issues=issues,
    )
    db.add(task)
    db.flush()
    db.add_all(m.TaskMaterial(task_id=task.id, material_id=r.id) for r in materials)
    db.flush()
    return task


def expire_leases(db: Session):
    tasks = db.scalars(
        select(m.ProcessingTask)
        .where(
            m.ProcessingTask.state == "running", m.ProcessingTask.expires_at < utcnow()
        )
        .with_for_update(skip_locked=True)
    ).all()
    for task in tasks:
        task.state = "failed"
        task.issues = [
            *task.issues,
            ProcessingError("WORKER_LOST", "处理进程租约过期", retryable=True).issue(
                task.stage
            ),
        ]
        task.lease_token = None
        task.updated_at = utcnow()
    return len(tasks)


def claim_task(db: Session, worker_id: str, lease_seconds=120):
    task = db.scalar(
        select(m.ProcessingTask)
        .where(m.ProcessingTask.state == "pending")
        .order_by(m.ProcessingTask.created_at, m.ProcessingTask.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if task is None:
        return None
    task.state, task.stage = "running", "preflight"
    task.worker_id, task.lease_token = worker_id, uuid.uuid4()
    task.heartbeat_at = task.updated_at = utcnow()
    task.expires_at = utcnow() + timedelta(seconds=lease_seconds)
    task.attempt += 1
    db.flush()
    return task


def fenced_task(db: Session, task_id, lease_token):
    task = get_task(db, task_id, lock=True)
    if (
        task.state != "running"
        or task.lease_token != lease_token
        or task.expires_at <= utcnow()
    ):
        raise ProcessingError("STALE_LEASE", "过期或失效worker不能回写结果")
    return task


def heartbeat(db: Session, task_id, lease_token, lease_seconds=120):
    task = fenced_task(db, task_id, lease_token)
    task.heartbeat_at = task.updated_at = utcnow()
    task.expires_at = utcnow() + timedelta(seconds=lease_seconds)


def save_artifact(
    db,
    task_id,
    token,
    stage,
    payload,
    settings,
    *,
    stage_input_hash=None,
    source_artifact_id=None,
):
    task = fenced_task(db, task_id, token)
    digest = fingerprint(payload)
    key = f"{task.id}/{stage}/{digest}.json"
    digest, size = atomic_json(settings.m3_path("m3_artifacts_dir"), key, payload)
    artifact = m.ProcessingArtifact(
        task_id=task.id,
        stage=stage,
        input_hash=stage_input_hash or task.input_hash,
        method_hash=task.method_hash,
        storage_key=key,
        artifact_hash=digest,
        size_bytes=size,
        source_artifact_id=source_artifact_id,
    )
    db.add(artifact)
    task.stage, task.updated_at = stage, utcnow()
    db.flush()
    return artifact


def get_draft(db, task, view="final"):
    return db.scalar(
        select(m.ProcessingDraft).where(
            m.ProcessingDraft.task_id == task.id, m.ProcessingDraft.view == view
        )
    )


def store_draft(db, task, payload, *, view):
    digest = business_hash(payload)
    existing = get_draft(db, task, view)
    if existing:
        if existing.result_hash != digest:
            raise conflict("已保存结果不可原地覆盖；修订须创建新任务")
        return existing
    row = m.ProcessingDraft(
        task_id=task.id, view=view, result_hash=digest, payload=payload
    )
    db.add(row)
    if view == "final":
        task.result_hash = digest
    db.flush()
    return row


def check_result(db, task_id, expected_hash, settings):
    task = get_task(db, task_id, lock=True)
    if task.result_hash != expected_hash:
        raise conflict("结果已变更，请刷新后重试")
    draft = get_draft(db, task)
    if draft is None or task.batch_id is None:
        raise conflict("结果尚未完整入库")
    batch, paper = (
        db.get(ImportBatch, task.batch_id),
        db.get(ExamPaper, task.exam_paper_id),
    )
    from app.services.content_check import evaluate

    issues = evaluate(db, paper, batch, settings.audio_storage_path)
    issues += validate_result(draft.payload, task.request)
    for material in task_materials(db, task.id):
        try:
            verify_material(material, settings)
        except (ProcessingError, OSError):
            issues.append(
                {"kind": "source_changed", "message": "原件缺失或身份发生变化"}
            )
    check = ContentCheck(
        exam_paper_id=paper.id,
        batch_id=batch.id,
        is_passed=not issues,
        issues=issues,
        result_hash=expected_hash,
        rule_version=RULE_VERSION,
        check_profile="module3",
    )
    db.add(check)
    db.flush()
    return check


def latest_reviews(db, task):
    rows = db.scalars(
        select(m.ProcessingReview)
        .where(
            m.ProcessingReview.task_id == task.id,
            m.ProcessingReview.result_hash == task.result_hash,
        )
        .order_by(m.ProcessingReview.id)
    ).all()
    return {r.scope: r for r in rows}


def record_review(db, task_id, data: ReviewRequest, user):
    task = get_task(db, task_id, lock=True)
    if task.result_hash != data.result_hash or not get_draft(db, task):
        raise conflict("复核必须绑定当前真实结果")
    if data.decision == "approved":
        payload = get_draft(db, task).payload
        if data.scope == "content":
            expected = {("questions", str(q["_src_id"])) for q in payload["questions"]}
        elif data.scope == "audio":
            expected = {
                ("transcript_segments", str(s["_src_id"]))
                for s in payload["transcript_segments"]
                if s["segment_type"] == "body"
            }
            expected.add(("audio", "original"))
        else:
            expected = {
                (section, str(row["_src_id"]))
                for section in (
                    "skill_question_relations",
                    "error_question_relations",
                    "other_relations",
                )
                for row in payload.get(section, [])
            }
        found = {
            (item.get("entity_type"), str(item.get("src_id"))): item
            for item in data.items
        }
        if (
            set(found) != expected
            or len(found) != len(data.items)
            or any(
                item.get("verdict") != "PASS"
                or not str(item.get("reference", "")).strip()
                for item in found.values()
            )
        ):
            raise AppError(422, "复核明细必须逐项覆盖当前范围并提供实际依据")
        if data.scope == "audio":
            original = found[("audio", "original")]
            if (
                original.get("file_hash") != payload["audio"]["file_hash"]
                or original.get("listened_to_end") is not True
            ):
                raise AppError(422, "整套核听记录须确认原音身份并完成核听")
            for segment in payload["transcript_segments"]:
                if segment["segment_type"] != "body":
                    continue
                item = found[("transcript_segments", str(segment["_src_id"]))]
                for field in ("start_ms", "end_ms"):
                    reference = item.get("reference_" + field)
                    if (
                        type(reference) is not int
                        or abs(reference - segment[field])
                        > task.method["sentence_tolerance_ms"]
                    ):
                        raise AppError(422, "句级边界未达到已冻结的300ms精度口径")
    row = m.ProcessingReview(
        task_id=task.id,
        **data.model_dump(),
        operator_user_id=user.id,
        operator_label=user.username,
    )
    db.add(row)
    db.flush()
    reviews = latest_reviews(db, task)
    checked = db.scalar(
        select(ContentCheck)
        .where(
            ContentCheck.batch_id == task.batch_id,
            ContentCheck.result_hash == task.result_hash,
        )
        .order_by(ContentCheck.id.desc())
        .limit(1)
    )
    task.state = (
        "completed"
        if checked
        and checked.is_passed
        and set(reviews) == {"content", "audio", "annotations"}
        and all(r.decision == "approved" for r in reviews.values())
        else "awaiting_confirmation"
    )
    task.stage = "completed" if task.state == "completed" else "review"
    return row


def child_task(db, parent, user_id, *, state="pending"):
    task = m.ProcessingTask(
        id=uuid.uuid4(),
        parent_task_id=parent.id,
        exam_paper_code=parent.exam_paper_code,
        exam_paper_id=parent.exam_paper_id,
        state=state,
        stage="registered",
        input_hash=parent.input_hash,
        method_hash=parent.method_hash,
        request=copy.deepcopy(parent.request),
        method=copy.deepcopy(parent.method),
        created_by=user_id,
        issues=[],
    )
    db.add(task)
    db.flush()
    db.add_all(
        m.TaskMaterial(task_id=task.id, material_id=r.id)
        for r in task_materials(db, parent.id)
    )
    return task


def retry_task(db, task_id, data: RetryRequest, user_id, settings):
    parent = get_task(db, task_id, lock=True)
    if parent.input_hash != data.expected_input_hash or parent.state not in {
        "failed",
        "awaiting_confirmation",
    }:
        raise conflict("仅可重试匹配输入指纹的失败或待确认任务")
    if data.from_stage != "preflight":
        # Safe until each stage has separately verified upstream compatibility.
        raise conflict("当前重试必须从preflight开始，禁止未经校验复用阶段")
    for material in task_materials(db, parent.id):
        verify_material(material, settings)
    task = child_task(db, parent, user_id)
    task.request = {**task.request, "retry_reason": data.reason}
    return task


CORRECTABLE = {
    "passages": {
        "topic",
        "scene",
        "accent",
        "passage_type",
        "start_ms",
        "body_end_ms",
        "end_ms",
    },
    "transcript_segments": {
        "text",
        "start_ms",
        "end_ms",
        "segment_type",
        "speaker_code",
    },
    "questions": {
        "question_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_option",
        "explanation_text",
        "explanation_source",
        "source_refs",
    },
    "presentations": {"question_no", "option_letter_mapping", "mapping_source"},
    "evidences": {"segment_src_ids", "char_ranges", "evidence_text"},
    "skill_question_relations": {
        "skill_code",
        "role",
        "attributes_json",
        "evidence_src_id",
    },
    "error_question_relations": {
        "error_cause_code",
        "attributes_json",
        "evidence_src_id",
    },
    "other_relations": {"evidence_src_id", "attributes_json"},
}


def correct_task(db, task_id, data: CorrectionRequest, user_id):
    parent = get_task(db, task_id, lock=True)
    if parent.result_hash != data.expected_result_hash:
        raise conflict("结果版本冲突")
    draft = get_draft(db, parent)
    if draft is None:
        raise conflict("尚无可修订草稿")
    result = copy.deepcopy(draft.payload)
    for change in data.changes:
        if change.field not in CORRECTABLE[change.entity]:
            raise AppError(422, "校正字段不在允许范围")
        rows = [
            r
            for r in result.get(change.entity, [])
            if str(r["_src_id"]) == change.src_id
        ]
        if len(rows) != 1:
            raise AppError(422, "校正对象不存在或不唯一")
        rows[0][change.field] = change.value
        if change.entity == "transcript_segments":
            rows[0]["alignment_status"] = "requires_review"
    task = child_task(db, parent, user_id)
    task.input_hash = fingerprint(
        {"parent": parent.input_hash, "correction": data.model_dump()}
    )
    task.request = {**task.request, "correction": True}
    store_draft(db, task, result, view="final")
    auto = get_draft(db, parent, "auto_draft")
    if auto:
        store_draft(db, task, auto.payload, view="auto_draft")
    db.add(
        m.ProcessingCorrection(
            task_id=task.id,
            parent_task_id=parent.id,
            before_hash=parent.result_hash,
            after_hash=task.result_hash,
            before_payload=draft.payload,
            after_payload=result,
            changes=[c.model_dump() for c in data.changes],
            reason=data.reason,
            source_refs=data.source_refs,
            operator_user_id=user_id,
        )
    )
    return task


def activate(db, paper_id, data: ActivationRequest, user_id):
    paper = db.scalar(
        select(ExamPaper).where(ExamPaper.id == paper_id).with_for_update()
    )
    if paper is None:
        raise not_found()
    task = get_task(db, data.task_id, lock=True)
    batch = db.get(ImportBatch, data.batch_id)
    check = db.get(ContentCheck, data.check_id)
    if (
        batch is None
        or batch.exam_paper_id != paper.id
        or task.exam_paper_id != paper.id
        or task.batch_id != batch.id
        or task.result_hash != data.result_hash
        or batch.result_hash != data.result_hash
        or check is None
        or check.batch_id != batch.id
        or check.result_hash != data.result_hash
        or check.check_profile != "module3"
        or not check.is_passed
    ):
        raise conflict("目标任务、批次、检查或结果哈希不匹配")
    reviews = latest_reviews(db, task)
    if set(reviews) != {"content", "audio", "annotations"} or any(
        r.decision != "approved" for r in reviews.values()
    ):
        raise conflict("缺少当前版本完整的内容、核听和标注复核")
    current = db.scalar(
        select(ImportBatch).where(
            ImportBatch.exam_paper_id == paper.id, ImportBatch.is_current.is_(True)
        )
    )
    if current and current.id == batch.id:
        visibility = db.scalar(
            select(PaperVisibility)
            .where(PaperVisibility.batch_id == batch.id)
            .order_by(PaperVisibility.id.desc())
        )
        return {
            "current_batch_id": batch.id,
            "is_visible": bool(visibility and visibility.is_visible),
        }
    if (current.id if current else None) != data.expected_current_batch_id:
        raise conflict("当前批次已被其他管理员更改")
    if current:
        current.is_current = False
        db.flush()
    batch.is_current, batch.status = True, "active"
    paper.playback_audio_id = batch.audio_id
    visibility = db.scalar(
        select(PaperVisibility)
        .where(PaperVisibility.batch_id == batch.id)
        .order_by(PaperVisibility.id.desc())
    )
    if visibility:
        visibility.is_visible = False
    else:
        db.add(
            PaperVisibility(exam_paper_id=paper.id, batch_id=batch.id, is_visible=False)
        )
    db.add(
        m.BatchActivationLog(
            exam_paper_id=paper.id,
            old_batch_id=current.id if current else None,
            new_batch_id=batch.id,
            task_id=task.id,
            check_id=check.id,
            result_hash=data.result_hash,
            operator_user_id=user_id,
        )
    )
    return {"current_batch_id": batch.id, "is_visible": False}
