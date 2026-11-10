"""Audited alignment revisions, implemented outside the original project."""

from __future__ import annotations

import copy
import json
import os
import shutil
from itertools import pairwise
from pathlib import Path

from sqlalchemy import select

from app.core.errors import AppError
from app.db import models_processing as m
from app.module3.contracts import (
    ProcessingError,
    controlled_path,
    file_hash,
    fingerprint,
)
from app.schemas_processing import ReferenceSegment, TaskRequest
from app.services.processing import tasks

VERSION = "console.alignment-revision.v1"
ROOT = Path(__file__).resolve().parent


def code_hashes():
    return {
        name: file_hash(ROOT / name)
        for name in ("alignment_revision.py", "console_worker.py")
    }


def revision_record(db, task_id):
    row = db.scalar(
        select(m.ProcessingCorrection)
        .where(m.ProcessingCorrection.task_id == task_id)
        .order_by(m.ProcessingCorrection.id.desc())
        .limit(1)
    )
    return row if row and row.after_payload.get("kind") == VERSION else None


def read_artifact(db, task_id, stage, settings, expected=None):
    row = db.scalar(
        select(m.ProcessingArtifact)
        .where(
            m.ProcessingArtifact.task_id == task_id, m.ProcessingArtifact.stage == stage
        )
        .order_by(m.ProcessingArtifact.id.desc())
        .limit(1)
    )
    if row is None or (expected and row.artifact_hash != expected):
        raise AppError(409, "来源阶段不存在或版本已变化，请刷新")
    path = controlled_path(settings.m3_path("m3_artifacts_dir"), row.storage_key)
    if file_hash(path) != row.artifact_hash:
        raise AppError(409, "来源阶段文件校验失败")
    return row, json.loads(path.read_text(encoding="utf-8"))


def merge_allowed(a, b):
    return (
        a["segment_type"] == b["segment_type"] == "body"
        and a["passage_key"] == b["passage_key"]
        and a.get("speaker") in {"M", "W"}
        and a.get("speaker") == b.get("speaker")
        and a["source_storage_key"] == b["source_storage_key"]
        and a["source_sha256"] == b["source_sha256"]
    )


def edit_reference(reference, alignment, values):
    """One explicit edit; source words, question IDs and unaffected rows stay fixed."""
    if values.get("listened") is not True or not str(values.get("reason", "")).strip():
        raise AppError(422, "请先核听上下文，并填写本次校正原因")
    action = values.get("operation")
    if action not in {"window", "merge_next", "merge_previous"}:
        raise AppError(422, "请选择调整搜索范围或合并相邻同说话人正文")
    segments = copy.deepcopy(reference["segments"])
    indexes = [
        i for i, s in enumerate(segments) if s["segment_id"] == values.get("segment_id")
    ]
    if len(indexes) != 1:
        raise AppError(422, "校正片段不存在")
    index = indexes[0]
    start, end = values.get("search_start_ms"), values.get("search_end_ms")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= alignment["duration_ms"]
        or end - start > 30000
    ):
        raise AppError(422, "搜索范围须在音频时长内，起点小于终点，且不超过30秒")
    first, last = index, index
    if action != "window":
        other = index + (1 if action == "merge_next" else -1)
        if not 0 <= other < len(segments):
            raise AppError(422, "没有可合并的相邻片段")
        first, last = sorted((index, other))
        if not merge_allowed(segments[first], segments[last]):
            raise AppError(
                422,
                "仅可合并同一篇章、同一明确说话人、同一来源的相邻正文；不得合并提问",
            )
    old = copy.deepcopy(segments[first : last + 1])
    replacement = copy.deepcopy(old[0])
    replacement["text"] = " ".join(s["text"] for s in old)
    replacement["source_pages"] = sorted({p for s in old for p in s["source_pages"]})
    replacement.update(search_start_ms=start, search_end_ms=end)
    replacement = ReferenceSegment.model_validate(replacement).model_dump(mode="json")
    segments[first : last + 1] = [replacement]
    return segments, {
        "operation": action,
        "original_segment_ids": [s["segment_id"] for s in old],
        "replacement_segment_id": replacement["segment_id"],
        "before": old,
        "after": replacement,
    }


def create_revision(db, parent, data, user, settings):
    if (
        parent.state not in {"awaiting_confirmation", "failed"}
        or parent.stage != "align"
    ):
        raise AppError(409, "仅可校正已停止在对齐阶段的任务")
    snapshots = {}
    values = {}
    for stage in ("extract", "normalize", "reference", "align"):
        row, value = read_artifact(
            db,
            parent.id,
            stage,
            settings,
            data.get("artifact_hash") if stage == "align" else None,
        )
        snapshots[stage] = {"id": row.id, "hash": row.artifact_hash}
        values[stage] = value
    if data.get("artifact_hash") != snapshots["align"]["hash"]:
        raise AppError(409, "对齐结果已变化，请刷新后校正")
    references, change = edit_reference(values["reference"], values["align"], data)
    structure = values["reference"].get("trusted_question_structure", {})
    if not structure.get("groups") or not structure.get("question_count"):
        raise AppError(409, "原任务缺少可信原卷题组，不接受丢失来源结构的校正")
    materials = tasks.task_materials(db, parent.id)
    original_paper = next(
        s
        for s in materials
        if s.source_kind == "paper_" + parent.request["document_mode"]
    )
    request = {
        k: v
        for k, v in parent.request.items()
        if k in TaskRequest.model_fields
        and not k.startswith("reuse_")
        and k not in {"sample_review", "annotation_review"}
    }
    request.update(
        reference_preparation="provided",
        reference_segments=references,
        stop_after="align",
        expected_question_count=structure["question_count"],
        expected_question_count_source={
            "document": original_paper.storage_key,
            "sha256": original_paper.sha256,
            "locator": "original_paper_question_headings",
        },
        expected_question_ranges=[
            {k: g[k] for k in ("section", "start", "end")} for g in structure["groups"]
        ],
    )
    task = tasks.create_task(db, TaskRequest.model_validate(request), user.id, settings)
    if task.issues:
        raise AppError(409, "修订任务的来源完整性检查未通过")
    before = {"source_task_id": str(parent.id), "artifacts": snapshots}
    after = {
        "kind": VERSION,
        "source_task_id": str(parent.id),
        "reference_segments": references,
        "change": change,
        "implementation_sha256": code_hashes(),
    }
    method = {
        **task.method,
        "console_alignment_revision": {
            "version": VERSION,
            "implementation_sha256": code_hashes(),
        },
    }
    task.method, task.method_hash = method, fingerprint(method)
    task.input_hash = fingerprint(
        {
            "request": {k: v for k, v in task.request.items() if k != "material_ids"},
            "materials": sorted((r.source_kind, r.sha256) for r in materials),
            "method": method,
        }
    )
    task.parent_task_id = parent.id
    db.add(
        m.ProcessingCorrection(
            task_id=task.id,
            parent_task_id=parent.id,
            before_hash=fingerprint(before),
            after_hash=fingerprint(after),
            before_payload=before,
            after_payload=after,
            changes=[change],
            reason=data["reason"].strip(),
            source_refs=[
                f"task:{parent.id};align:{snapshots['align']['hash']}",
                "audio_context_listened",
            ],
            operator_user_id=user.id,
        )
    )
    db.flush()
    return task


def copy_retry_record(db, parent, child, user_id):
    row = revision_record(db, parent.id)
    if row:
        db.add(
            m.ProcessingCorrection(
                task_id=child.id,
                parent_task_id=row.parent_task_id,
                before_hash=row.before_hash,
                after_hash=row.after_hash,
                before_payload=copy.deepcopy(row.before_payload),
                after_payload=copy.deepcopy(row.after_payload),
                changes=copy.deepcopy(row.changes),
                reason="重试局部校正：" + row.reason,
                source_refs=copy.deepcopy(row.source_refs),
                operator_user_id=user_id,
            )
        )


def link_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if file_hash(target) != file_hash(source):
            raise ProcessingError("REVISION_FILE_CHANGED", "修订任务已有文件不一致")
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def validate_combined(reference, result):
    refs = reference["segments"]
    rows = result["segments"]
    if len(rows) != len(refs) or [s["_src_id"] for s in rows] != [
        s["segment_id"] for s in refs
    ]:
        raise ProcessingError("REFERENCE_TEXT_CHANGED", "修订后句子集合不一致")
    issues = result.setdefault("issues", [])
    for ref, s in zip(refs, rows, strict=True):
        if s["text"] != ref["text"]:
            raise ProcessingError("REFERENCE_TEXT_CHANGED", "修订后正文发生未授权变化")
        if (
            s.get("alignment_status") != "aligned"
            or type(s.get("start_ms")) is not int
            or type(s.get("end_ms")) is not int
            or not 0 <= s["start_ms"] < s["end_ms"] <= result["duration_ms"]
        ):
            if not any(s["_src_id"] in i.get("segment_src_ids", []) for i in issues):
                issues.append(
                    {
                        "issue_code": "ALIGNMENT_UNVERIFIED",
                        "segment_src_ids": [s["_src_id"]],
                        "message": "片段仍需校正",
                    }
                )
    for left, right in pairwise(rows):
        if (
            left.get("end_ms") is not None
            and right.get("start_ms") is not None
            and (
                left["end_ms"] - right["start_ms"] > 300
                or right["start_ms"] < left["start_ms"]
            )
        ):
            left["alignment_status"] = right["alignment_status"] = "requires_review"
            issues.append(
                {
                    "issue_code": "ALIGNMENT_NEIGHBOUR_CONFLICT",
                    "segment_src_ids": [left["_src_id"], right["_src_id"]],
                    "message": "修订与相邻片段边界冲突，仍需校正",
                }
            )


def process_revision(task_id, token, settings, original_worker):
    """Reuse immutable upstream; align only the edited text."""
    from app.core.config import BASE_DIR
    from app.db.base import SessionLocal
    from app.module3 import reference as reference_module
    from app.module3.reuse import UPSTREAM_DEPENDENCIES, implementation_hash

    try:
        with original_worker.renewed_lease(task_id, token, settings) as lost:
            with SessionLocal() as db:
                task = tasks.fenced_task(db, task_id, token)
                row = revision_record(db, task_id)
                if (
                    not row
                    or fingerprint(row.before_payload) != row.before_hash
                    or fingerprint(row.after_payload) != row.after_hash
                ):
                    raise ProcessingError("REVISION_CHANGED", "校正记录校验失败")
                correction = copy.deepcopy(row.after_payload)
                before = copy.deepcopy(row.before_payload)
                if (
                    correction["implementation_sha256"] != code_hashes()
                    or task.method_hash != fingerprint(task.method)
                    or task.method.get("console_alignment_revision", {}).get(
                        "implementation_sha256"
                    )
                    != code_hashes()
                ):
                    raise ProcessingError(
                        "METHOD_CHANGED", "局部校正实现已变化，请建立新的修订任务"
                    )
                if correction["reference_segments"] != task.request.get(
                    "reference_segments"
                ):
                    raise ProcessingError(
                        "REVISION_CHANGED", "校正原文与任务请求不一致"
                    )
                source = tasks.get_task(db, before["source_task_id"])
                if source.method_hash != fingerprint(source.method):
                    raise ProcessingError("METHOD_CHANGED", "原任务方法快照损坏")
                if source.method["locks"] != task.method["locks"]:
                    raise ProcessingError("METHOD_CHANGED", "上游依赖锁已变化")
                manifest = "config/module3/model-artifact-manifest.json"
                if implementation_hash(source.method, manifest) != file_hash(
                    controlled_path(BASE_DIR, manifest)
                ):
                    raise ProcessingError("METHOD_CHANGED", "固定模型资源清单已变化")
                for name in UPSTREAM_DEPENDENCIES:
                    key = "app/module3/" + name
                    if implementation_hash(source.method, key) != file_hash(
                        controlled_path(BASE_DIR, key)
                    ):
                        raise ProcessingError("METHOD_CHANGED", "原任务上游算法已变化")
                materials = tasks.task_materials(db, task.id)
                if sorted((s.source_kind, s.sha256) for s in materials) != sorted(
                    (s.source_kind, s.sha256)
                    for s in tasks.task_materials(db, source.id)
                ):
                    raise ProcessingError("SOURCE_CHANGED", "校正与原任务材料不同")
                for material in materials:
                    tasks.verify_material(material, settings)
                expected_input = fingerprint(
                    {
                        "request": {
                            k: v
                            for k, v in task.request.items()
                            if k not in {"material_ids", "retry_reason"}
                        },
                        "materials": sorted(
                            (r.source_kind, r.sha256) for r in materials
                        ),
                        "method": task.method,
                    }
                )
                if task.input_hash != expected_input:
                    raise ProcessingError("REVISION_CHANGED", "修订输入指纹不一致")
                upstream = {
                    stage: read_artifact(db, source.id, stage, settings, meta["hash"])[
                        1
                    ]
                    for stage, meta in before["artifacts"].items()
                }
            root = settings.m3_path("m3_artifacts_dir")
            source_dir = root / before["source_task_id"]
            target_dir = root / str(task_id)
            (target_dir / "documents").mkdir(parents=True, exist_ok=True)
            normalized = source_dir / "normalized.npy"
            if file_hash(normalized) != upstream["normalize"]["normalized_sha256"]:
                raise ProcessingError("SOURCE_CHANGED", "复用音频校验失败")
            for page in upstream["extract"]["pages"]:
                if page.get("page_image"):
                    image = controlled_path(
                        source_dir / "documents", page["page_image"]
                    )
                    if file_hash(image) != page["page_image_sha256"]:
                        raise ProcessingError("SOURCE_CHANGED", "来源页图校验失败")
                    link_file(
                        image,
                        controlled_path(
                            target_dir / "documents",
                            page["page_image"],
                            must_exist=False,
                        ),
                    )
            link_file(normalized, target_dir / "normalized.npy")
            original_worker.checkpoint(
                task_id,
                token,
                "preflight",
                {
                    "status": "PASS",
                    "scope": VERSION,
                    "new_ocr_calls": 0,
                    "new_asr_calls": 0,
                    "new_llm_calls": 0,
                },
                settings,
            )
            for stage in ("extract", "normalize"):
                original_worker.checkpoint(
                    task_id,
                    token,
                    stage,
                    upstream[stage],
                    settings,
                    source_artifact_id=before["artifacts"][stage]["id"],
                )
            revised = copy.deepcopy(upstream["reference"])
            revised["segments"] = correction["reference_segments"]
            revised["preparation"] = "user_reviewed_local_alignment_revision"
            original_worker.checkpoint(task_id, token, "reference", revised, settings)
            change = correction["change"]
            affected = set(change["original_segment_ids"])
            local = reference_module.align(normalized, [change["after"]], settings)
            result = copy.deepcopy(upstream["align"])
            old = {s["_src_id"]: s for s in result["segments"]}
            replacement = local["segments"][0]
            result["segments"] = [
                replacement
                if r["segment_id"] == replacement["_src_id"]
                else old[r["segment_id"]]
                for r in revised["segments"]
            ]
            result["issues"] = [
                i
                for i in result.get("issues", [])
                if not (
                    i.get("segment_src_ids") and set(i["segment_src_ids"]) <= affected
                )
            ] + local.get("issues", [])
            validate_combined(revised, result)
            original_worker.checkpoint(
                task_id,
                token,
                "alignment_revision",
                {
                    "kind": VERSION,
                    "source_task_id": before["source_task_id"],
                    "before_hash": row.before_hash,
                    "after_hash": row.after_hash,
                    "change": change,
                    "locally_aligned_segment_count": 1,
                    "unchanged_segments_reused": len(result["segments"]) - 1,
                    "human_audio_approval": False,
                },
                settings,
            )
            original_worker.checkpoint(task_id, token, "align", result, settings)
            if lost.is_set():
                raise ProcessingError("STALE_LEASE", "处理租约已失效")
            with SessionLocal() as db:
                task = tasks.fenced_task(db, task_id, token)
                task.state = "awaiting_confirmation"
                task.lease_token = None
                task.expires_at = None
                task.issues = [
                    {
                        "issue_code": "ALIGNMENT_UNVERIFIED"
                        if result["issues"]
                        else "ALIGNMENT_REVIEW_REQUIRED",
                        "severity": "error" if result["issues"] else "info",
                        "stage": "align",
                        "message": "局部重对齐仍有异常，请继续校正"
                        if result["issues"]
                        else "局部重对齐已完成，等待用户核听确认",
                        "retryable": False,
                    }
                ]
                task.updated_at = tasks.utcnow()
                db.commit()
            return 0 if not result["issues"] else 2
    except Exception as exc:
        if os.getenv("M3_CONSOLE_REVISION_DEBUG") == "1":
            import traceback

            traceback.print_exc()
        error = (
            exc
            if isinstance(exc, ProcessingError)
            else ProcessingError(
                "ALIGNMENT_REVISION_FAILED",
                f"局部校正失败（{type(exc).__name__}），保留原结果",
                retryable=True,
            )
        )
        with SessionLocal() as db:
            try:
                task = tasks.fenced_task(db, task_id, token)
            except ProcessingError:
                return 2
            task.state = "failed"
            task.issues = [error.issue(task.stage)]
            task.lease_token = None
            task.expires_at = None
            task.updated_at = tasks.utcnow()
            db.commit()
        return 2
