"""Pending-only business import; explicit identities and no current-version mutation."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select, text

from app.db import models_annotations as a
from app.db import models_listening as m
from app.db import models_processing as p
from app.db.base import SessionLocal
from app.module3.contracts import (
    ProcessingError,
    controlled_path,
    file_hash,
    fingerprint,
    result_identity,
)
from app.module3.contracts import (
    result_hash as business_hash,
)
from app.services.processing.tasks import fenced_task, store_draft, utcnow
from app.services.processing.validation import (
    CONFIG_DIR,
    entity_index,
    evidence_details,
    load_dictionary,
    validate_result,
)


def json_object(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def column_values(model, data, *, exclude=()):
    columns = {c.name for c in model.__table__.columns} - {"id", *exclude}
    result = {key: value for key, value in data.items() if key in columns}
    if "attributes_json" in result:
        result["attributes_json"] = json_object(result["attributes_json"])
    return result


def ensure_dictionary(db):
    digest = file_hash(CONFIG_DIR / "dictionary-schema.json")
    # Serialize first import even when two different papers start together.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(digest[:15], 16)}
    )
    snapshot = db.scalar(
        select(p.DictionarySnapshot).where(p.DictionarySnapshot.schema_sha256 == digest)
    )
    if snapshot:
        return snapshot
    source = load_dictionary()
    snapshot = p.DictionarySnapshot(
        schema_sha256=digest,
        data_sha256=fingerprint(source),
        version="2026-10-24",
        payload=source,
        id_mapping={},
    )
    db.add(snapshot)
    db.flush()
    mapping = {}
    tables = {t["name"]: t for t in source["tables"]}
    for name, model, old_id, code in (
        ("skill", a.Skill, "skill_id", "skill_code"),
        ("error_cause", a.ErrorCause, "error_cause_id", "error_cause_code"),
        (
            "classification_dict",
            a.ClassificationDict,
            "classification_id",
            "classification_code",
        ),
    ):
        codes, old = {}, {}
        mapping[name] = {"codes": codes, "old_ids": old}
        deferred = []
        for row in tables[name]["rows"]:
            values = column_values(model, row, exclude=("parent_error_cause_id",))
            entity = model(snapshot_id=snapshot.id, **values)
            db.add(entity)
            db.flush()
            codes[row[code]], old[str(row[old_id])] = entity.id, entity.id
            if row.get("parent_error_cause_id"):
                deferred.append((entity, row["parent_error_cause_id"]))
        for entity, parent in deferred:
            entity.parent_error_cause_id = old[str(parent)]
    for row in tables["skill_error_relation"]["rows"]:
        values = column_values(
            a.SkillErrorRelation, row, exclude=("skill_id", "error_cause_id")
        )
        db.add(
            a.SkillErrorRelation(
                snapshot_id=snapshot.id,
                skill_id=mapping["skill"]["old_ids"][str(row["skill_id"])],
                error_cause_id=mapping["error_cause"]["old_ids"][
                    str(row["error_cause_id"])
                ],
                **values,
            )
        )
    for row in tables["other_relation"]["rows"]:
        if row["relation_kind"] not in {
            "SKILL_TAXONOMY",
            "SKILL_PREREQUISITE",
            "SKILL_CO_USE",
            "SKILL_SUPPORT",
        }:
            continue
        values = column_values(
            a.OtherRelation, row, exclude=("from_skill_id", "to_skill_id")
        )
        db.add(
            a.OtherRelation(
                snapshot_id=snapshot.id,
                scope="snapshot",
                scope_key=f"snapshot:{snapshot.id}",
                from_skill_id=mapping["skill"]["old_ids"][str(row["from_skill_id"])],
                to_skill_id=mapping["skill"]["old_ids"][str(row["to_skill_id"])],
                **values,
            )
        )
    snapshot.id_mapping = mapping
    db.flush()
    return snapshot


def publish_audio(source: Path, audio_dir: Path, audio: dict):
    audio_dir.mkdir(parents=True, exist_ok=True)
    key = (
        f"{fingerprint(audio['audio_code'])[:16]}-{audio['file_hash']}"
        f".{source.suffix.lower().lstrip('.')}"
    )
    target = controlled_path(audio_dir, key, must_exist=False)
    if target.exists():
        if file_hash(target) != audio["file_hash"]:
            raise ProcessingError("AUDIO_IDENTITY_CONFLICT", "已存在音频版本哈希冲突")
        return target, False
    staged = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    created = False
    try:
        with source.open("rb") as src, staged.open("xb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        if file_hash(staged) != audio["file_hash"]:
            raise ProcessingError("SOURCE_CHANGED", "音频复制期间源文件发生变化")
        try:
            os.link(staged, target)
            created = True
        except FileExistsError:
            if file_hash(target) != audio["file_hash"]:
                raise ProcessingError(
                    "AUDIO_IDENTITY_CONFLICT", "音频文件发布冲突"
                ) from None
    finally:
        staged.unlink(missing_ok=True)
    return target, created


def persist_result(db, task_id, token, payload, audio_source, settings):
    """Caller commits; retain immutable content when commit status is uncertain.

    Unreferenced content-addressed files are safe and can be reconciled separately.
    Existing files are never removed by a failed task.
    """
    task = fenced_task(db, task_id, token)
    issues = validate_result(payload, task.request)
    if issues:
        task.issues = issues
        task.state, task.stage, task.lease_token = (
            "awaiting_confirmation",
            "validate",
            None,
        )
        return None
    snapshot = ensure_dictionary(db)
    # Paper-level lock also protects first-create and result-fingerprint races.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int(fingerprint(task.exam_paper_code)[:15], 16)},
    )
    paper = db.scalar(
        select(m.ExamPaper)
        .where(m.ExamPaper.exam_paper_code == task.exam_paper_code)
        .with_for_update()
    )
    if paper is None:
        values = column_values(m.ExamPaper, task.request["exam_paper"])
        paper = m.ExamPaper(**values)
        db.add(paper)
        db.flush()
    count, source = (
        task.request[k]
        for k in ("expected_question_count", "expected_question_count_source")
    )
    if paper.expected_question_count is not None and (
        paper.expected_question_count != count
        or paper.expected_question_count_source != source
    ):
        raise ProcessingError("PAPER_IDENTITY_CONFLICT", "可信题量或来源冲突")
    paper.expected_question_count, paper.expected_question_count_source = count, source
    result_hash = business_hash(payload)
    result_fp = fingerprint(
        {
            "input": task.input_hash,
            "method": task.method_hash,
            "result": result_identity(payload),
        }
    )
    prior = db.scalar(
        select(m.ImportBatch).where(
            m.ImportBatch.exam_paper_id == paper.id,
            m.ImportBatch.result_fingerprint == result_fp,
        )
    )
    if prior:
        check = db.scalar(
            select(m.ContentCheck)
            .where(
                m.ContentCheck.batch_id == prior.id,
                m.ContentCheck.result_hash == result_hash,
            )
            .order_by(m.ContentCheck.id.desc())
        )
        if not check or not check.is_passed:
            raise ProcessingError(
                "RESULT_NOT_VALIDATED", "同指纹已有待检批次，请先完成原任务检查"
            )
        task.batch_id, task.exam_paper_id, task.result_hash = (
            prior.id,
            paper.id,
            result_hash,
        )
        task.reused_task_id = db.scalar(
            select(p.ProcessingTask.id)
            .where(p.ProcessingTask.batch_id == prior.id)
            .order_by(p.ProcessingTask.created_at)
        )
        task.state, task.stage, task.lease_token = (
            "awaiting_confirmation",
            "review",
            None,
        )
        return prior
    audio = payload["audio"]
    if file_hash(audio_source) != audio["file_hash"]:
        raise ProcessingError("SOURCE_CHANGED", "音频哈希与产物不一致")
    audio_dir = settings.audio_storage_path.resolve()
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int(audio["file_hash"][:15], 16)},
    )
    target, created = publish_audio(audio_source, audio_dir, audio)
    if created:
        db.info.setdefault("m3_created_files", []).append((target, audio["file_hash"]))
    row = db.scalar(
        select(m.AudioFile).where(m.AudioFile.audio_code == audio["audio_code"])
    )
    if row is not None and (
        row.file_hash != audio["file_hash"]
        or row.storage_key != target.name
        or row.duration_ms != audio["duration_ms"]
    ):
        if created:
            target.unlink(missing_ok=True)
        raise ProcessingError("AUDIO_IDENTITY_CONFLICT", "音频编码已绑定不同版本")
    if row is None:
        row = m.AudioFile(
            **column_values(m.AudioFile, audio, exclude=("storage_key",)),
            storage_key=target.name,
        )
        db.add(row)
        db.flush()
    batch = m.ImportBatch(
        exam_paper_id=paper.id,
        audio_id=row.id,
        batch_code="M3_" + uuid.uuid4().hex,
        status="pending",
        is_current=False,
        result_fingerprint=result_fp,
        result_hash=result_hash,
        profile_version=task.request["profile_version"],
        check_profile="module3",
        source_manifest_hash=task.input_hash,
        source_manifest={"request": task.request, "method": task.method},
        imported_at=utcnow(),
    )
    db.add(batch)
    db.flush()
    maps = {}

    def insert(section, model, values_for):
        maps[section] = {}
        for data in payload.get(section, []):
            src_id = str(data["_src_id"])
            entity = model(batch_id=batch.id, **values_for(data))
            db.add(entity)
            db.flush()
            maps[section][src_id] = entity.id

    def ref(section, value):
        if value is None:
            return None
        try:
            return maps[section][str(value)]
        except KeyError:
            raise ProcessingError(
                "SRC_REFERENCE_INVALID", "临时引用悬空或未按依赖顺序入库"
            ) from None

    insert("content_groups", m.ContentGroup, lambda d: column_values(m.ContentGroup, d))
    for group_id in maps["content_groups"].values():
        db.add(
            p.BatchAudioGroup(
                batch_id=batch.id, audio_id=row.id, content_group_id=group_id
            )
        )
    if maps["content_groups"]:
        db.add(
            p.BatchPaperMetadata(
                batch_id=batch.id,
                content_group_id=next(iter(maps["content_groups"].values())),
            )
        )
    insert(
        "passages",
        m.Passage,
        lambda d: {
            **column_values(m.Passage, d, exclude=("audio_id", "exam_paper_id")),
            "audio_id": row.id,
            "exam_paper_id": paper.id,
        },
    )
    insert(
        "transcript_segments",
        m.TranscriptSegment,
        lambda d: {
            **column_values(m.TranscriptSegment, d, exclude=("passage_id",)),
            "passage_id": ref("passages", d["passage_src_id"]),
        },
    )
    insert(
        "questions",
        m.Question,
        lambda d: {
            **column_values(
                m.Question,
                d,
                exclude=("passage_id", "question_segment_id", "content_state"),
            ),
            "passage_id": ref("passages", d["passage_src_id"]),
            "question_segment_id": ref(
                "transcript_segments", d.get("question_segment_src_id")
            ),
            "content_state": "可用",
        },
    )
    insert(
        "presentations",
        m.Presentation,
        lambda d: {
            **column_values(
                m.Presentation, d, exclude=("exam_paper_id", "question_id")
            ),
            "exam_paper_id": paper.id,
            "question_id": ref("questions", d["question_src_id"]),
        },
    )
    insert(
        "language_items",
        a.LanguageItem,
        lambda d: {
            **column_values(a.LanguageItem, d),
            "normalized_text": d["item_text"].strip().casefold(),
        },
    )
    segments = entity_index(payload["transcript_segments"], "segments")
    passages = entity_index(payload["passages"], "passages")
    insert(
        "evidences",
        a.EvidenceItem,
        lambda d: {
            **column_values(
                a.EvidenceItem,
                d,
                exclude=("passage_id", "segment_id", "start_ms", "end_ms"),
            ),
            **evidence_details(d, segments, passages[str(d["passage_src_id"])]),
            "passage_id": ref("passages", d["passage_src_id"]),
            "segment_id": ref("transcript_segments", d["segment_src_ids"][0]),
        },
    )
    for evidence in payload.get("evidences", []):
        ranges = evidence.get("char_ranges")
        for i, segment_id in enumerate(evidence["segment_src_ids"]):
            db.add(
                a.EvidenceSegment(
                    evidence_id=ref("evidences", evidence["_src_id"]),
                    batch_id=batch.id,
                    passage_id=ref("passages", evidence["passage_src_id"]),
                    segment_id=ref("transcript_segments", segment_id),
                    sort_order=i + 1,
                    start_char=ranges[i][0] if ranges else None,
                    end_char=ranges[i][1] if ranges else None,
                )
            )
    for section, model in (
        ("skill_question_relations", a.SkillQuestionRelation),
        ("error_question_relations", a.ErrorQuestionRelation),
        ("other_relations", a.OtherRelation),
    ):
        maps[section] = {}
        ordered = sorted(
            payload.get(section, []), key=lambda d: bool(d.get("owner_relation_src_id"))
        )
        for data in ordered:
            values = column_values(model, data)
            for source_field, target_field, target_section in (
                ("question_src_id", "question_id", "questions"),
                ("evidence_src_id", "evidence_id", "evidences"),
                ("owner_relation_src_id", "owner_relation_id", section),
                ("language_item_src_id", "language_item_id", "language_items"),
                ("segment_src_id", "segment_id", "transcript_segments"),
            ):
                if source_field in data:
                    values[target_field] = ref(target_section, data[source_field])
            for code_field, id_field, category in (
                ("skill_code", "skill_id", "skill"),
                ("error_cause_code", "error_cause_id", "error_cause"),
            ):
                if code_field in data:
                    values[id_field] = snapshot.id_mapping[category]["codes"][
                        data[code_field]
                    ]
            if section == "other_relations":
                values.update(scope="batch", scope_key=f"batch:{batch.id}")
            entity = model(batch_id=batch.id, **values)
            db.add(entity)
            db.flush()
            maps[section][str(data["_src_id"])] = entity.id
    for section in ("passages", "transcript_segments", "questions"):
        for data in payload.get(section, []):
            for source_ref in data.get("source_refs", []):
                db.add(
                    p.BatchSourceRef(
                        batch_id=batch.id,
                        task_id=task.id,
                        entity_type=section,
                        src_id=str(data["_src_id"]),
                        material_id=source_ref["material_id"],
                        locator=source_ref["locator"],
                        original_text=source_ref.get("original_text"),
                        conversion_hash=source_ref.get("conversion_hash"),
                    )
                )
    store_draft(db, task, payload, view="final")
    task.batch_id, task.exam_paper_id, task.result_hash = (
        batch.id,
        paper.id,
        result_hash,
    )
    task.state, task.stage, task.lease_token = "awaiting_confirmation", "review", None
    task.updated_at = utcnow()
    db.flush()
    return batch


def cleanup_failed_files(created_files):
    """Reconcile only files this attempt created, under the same identity lock.

    A commit whose response was lost is detected by its persisted audio reference.
    If the database cannot answer, preserve the file until reconciliation is possible.
    """
    for path, digest in created_files:
        with SessionLocal() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int(digest[:15], 16)},
            )
            referenced = db.scalar(
                select(m.AudioFile.id).where(m.AudioFile.storage_key == path.name)
            )
            if not referenced and path.is_file() and file_hash(path) == digest:
                path.unlink()
            db.commit()
