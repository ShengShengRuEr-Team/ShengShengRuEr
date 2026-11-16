"""Explicit downstream reuse of immutable, verified upstream artifacts."""

import json

from sqlalchemy import select

from app.core.config import BASE_DIR
from app.db.models_processing import ProcessingArtifact
from app.module3.contracts import (
    ProcessingError,
    controlled_path,
    file_hash,
    fingerprint,
)
from app.services.processing import tasks

# Orchestration/dispatch changes do not change extracted text or acoustic boundaries.
# These are the actual upstream algorithm and resource dependencies.
UPSTREAM_DEPENDENCIES = (
    "audio.py",
    "auto_reference.py",
    "reference.py",
    "document_reference.py",
    "reference_document_scan.py",
    "ocr_refinement.py",
    "reference_locator.py",
    "acoustic_features.py",
    "ctc_alignment.py",
    "contracts.py",
)


def implementation_hash(method, key):
    return {
        k.replace("\\", "/"): v for k, v in method["implementation_sha256"].items()
    }.get(key)


def load(db, task, settings):
    source = tasks.get_task(db, task.request["reuse_alignment_task_id"])
    if source.state != "awaiting_confirmation" or source.stage != "align":
        raise ProcessingError("REUSE_NOT_APPROVED", "来源不是已完成的对齐停止点")
    if source.method_hash != fingerprint(source.method):
        raise ProcessingError("REUSE_METHOD_CHANGED", "来源方法快照损坏")
    before = tasks.task_materials(db, source.id)
    after = tasks.task_materials(db, task.id)
    if (
        sorted((m.source_kind, m.sha256) for m in before)
        != sorted((m.source_kind, m.sha256) for m in after)
        or source.exam_paper_code != task.exam_paper_code
    ):
        raise ProcessingError("REUSE_SOURCE_CHANGED", "复用任务材料/试卷身份不一致")
    for material in before:
        tasks.verify_material(material, settings)
    if source.method["locks"] != task.method["locks"]:
        raise ProcessingError("REUSE_METHOD_CHANGED", "上游依赖锁已变化")
    keys = ["app/module3/" + name for name in UPSTREAM_DEPENDENCIES]
    keys.append("config/module3/model-artifact-manifest.json")
    for key in keys:
        expected = implementation_hash(source.method, key)
        if expected is None or file_hash(controlled_path(BASE_DIR, key)) != expected:
            raise ProcessingError("REUSE_METHOD_CHANGED", "上游算法/资源已变化：" + key)
    values, provenance = {}, []
    root = settings.m3_path("m3_artifacts_dir")
    for stage in ("extract", "normalize", "reference", "align"):
        row = db.scalar(
            select(ProcessingArtifact)
            .where(
                ProcessingArtifact.task_id == source.id,
                ProcessingArtifact.stage == stage,
            )
            .order_by(ProcessingArtifact.id.desc())
            .limit(1)
        )
        if row is None:
            raise ProcessingError("REUSE_ARTIFACT_MISSING", "来源阶段缺失：" + stage)
        path = controlled_path(root, row.storage_key)
        if file_hash(path) != row.artifact_hash:
            raise ProcessingError(
                "REUSE_ARTIFACT_CHANGED", "来源阶段哈希不符：" + stage
            )
        values[stage] = json.loads(path.read_text(encoding="utf-8"))
        provenance.append(
            {"stage": stage, "artifact_id": row.id, "sha256": row.artifact_hash}
        )
    if values["align"].get("issues"):
        raise ProcessingError("ALIGNMENT_UNVERIFIED", "上游对齐有未决问题")
    aligned = {s["_src_id"]: s for s in values["align"]["segments"]}
    references = values["reference"]["segments"]
    if len(aligned) != len(references) or any(
        r["segment_id"] not in aligned
        or aligned[r["segment_id"]]["text"] != r["text"]
        or aligned[r["segment_id"]]["alignment_status"] != "aligned"
        for r in references
    ):
        raise ProcessingError("REUSE_TEXT_CHANGED", "对齐与原文ID/文字不一致")
    for page in values["extract"]["pages"]:
        if page.get("page_image"):
            image = controlled_path(root, f"{source.id}/documents/{page['page_image']}")
            if file_hash(image) != page["page_image_sha256"]:
                raise ProcessingError("REUSE_ARTIFACT_CHANGED", "上游页图哈希不符")
    return values, {
        "source_task_id": str(source.id),
        "source_method_hash": source.method_hash,
        "artifacts": provenance,
        "upstream_algorithm_unchanged": True,
        "scope": "reuse only; no new OCR/reference/alignment pass claimed",
    }


def assembly(db, task, settings):
    source = tasks.get_task(db, task.request["reuse_assembly_task_id"])
    if (
        source.state != "awaiting_confirmation"
        or source.stage not in {"assemble", "annotate"}
        or source.exam_paper_code != task.exam_paper_code
        or source.request.get("reuse_alignment_task_id")
        != task.request.get("reuse_alignment_task_id")
    ):
        raise ProcessingError("REUSE_ASSEMBLY_INVALID", "组装复用任务/上游不匹配")
    for key in ("app/module3/source_assembly.py", "app/module3/assembly_scan.py"):
        if implementation_hash(source.method, key) != file_hash(
            controlled_path(BASE_DIR, key)
        ):
            raise ProcessingError("REUSE_ASSEMBLY_CHANGED", "组装算法已变化")
    for material in tasks.task_materials(db, source.id):
        tasks.verify_material(material, settings)
    if sorted(
        (m.source_kind, m.sha256) for m in tasks.task_materials(db, source.id)
    ) != sorted((m.source_kind, m.sha256) for m in tasks.task_materials(db, task.id)):
        raise ProcessingError("REUSE_ASSEMBLY_CHANGED", "组装来源材料不同")
    row = db.scalar(
        select(ProcessingArtifact)
        .where(
            ProcessingArtifact.task_id == source.id,
            ProcessingArtifact.stage == "assemble",
        )
        .order_by(ProcessingArtifact.id.desc())
        .limit(1)
    )
    if row is None:
        raise ProcessingError("REUSE_ASSEMBLY_INVALID", "来源没有组装产物")
    path = controlled_path(settings.m3_path("m3_artifacts_dir"), row.storage_key)
    if file_hash(path) != row.artifact_hash:
        raise ProcessingError("REUSE_ASSEMBLY_CHANGED", "组装产物哈希不符")
    return json.loads(path.read_text(encoding="utf-8")), row.id


def assembly_scan(db, task, settings):
    source = tasks.get_task(db, task.request["reuse_assembly_scan_task_id"])
    if source.exam_paper_code != task.exam_paper_code or sorted(
        (m.source_kind, m.sha256) for m in tasks.task_materials(db, source.id)
    ) != sorted((m.source_kind, m.sha256) for m in tasks.task_materials(db, task.id)):
        raise ProcessingError("REUSE_SOURCE_CHANGED", "解析OCR来源材料不一致")
    key = "app/module3/assembly_scan.py"
    if implementation_hash(source.method, key) != file_hash(
        controlled_path(BASE_DIR, key)
    ):
        raise ProcessingError("REUSE_METHOD_CHANGED", "解析OCR实现已变化")
    if source.method["locks"] != task.method["locks"] or implementation_hash(
        source.method, "config/module3/model-artifact-manifest.json"
    ) != file_hash(BASE_DIR / "config/module3/model-artifact-manifest.json"):
        raise ProcessingError("REUSE_METHOD_CHANGED", "解析OCR依赖/模型已变化")
    row = db.scalar(
        select(ProcessingArtifact)
        .where(
            ProcessingArtifact.task_id == source.id,
            ProcessingArtifact.stage == "assembly_extract",
        )
        .order_by(ProcessingArtifact.id.desc())
        .limit(1)
    )
    if row is None:
        raise ProcessingError("REUSE_ARTIFACT_MISSING", "来源无完整解析OCR阶段")
    root = settings.m3_path("m3_artifacts_dir")
    path = controlled_path(root, row.storage_key)
    if file_hash(path) != row.artifact_hash:
        raise ProcessingError("REUSE_ARTIFACT_CHANGED", "解析OCR哈希不符")
    data = json.loads(path.read_text(encoding="utf-8"))
    for page in data["pages"]:
        image = controlled_path(
            root, f"{source.id}/assembly-documents/{page['page_image']}"
        )
        if file_hash(image) != page["page_image_sha256"]:
            raise ProcessingError("REUSE_ARTIFACT_CHANGED", "解析OCR页图哈希不符")
    return data, row.id
