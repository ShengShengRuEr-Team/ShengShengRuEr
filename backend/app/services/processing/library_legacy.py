"""Register legacy papers without rewriting their formal batch or inventing proof."""

from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.db import models_annotations as a
from app.db import models_listening as b
from app.db import models_processing_workflows as m
from app.module3.annotation_identity import rules_manifest
from app.module3.contracts import fingerprint
from app.services.processing import library_content as c
from app.services.processing import workflows as w


def ensure_workflow(db, paper, user_id):
    identity = {
        k: getattr(paper, k)
        for k in ("exam_level", "exam_year", "exam_month", "paper_set", "content_scope")
    }
    workflow = db.scalar(
        select(m.ProcessingWorkflow).filter_by(**identity).with_for_update()
    )
    if workflow:
        if workflow.exam_paper_id not in {None, paper.id}:
            raise w.conflict("PAPER_IDENTITY_CONFLICT", "自然身份已有不同的稳定试卷")
        workflow.exam_paper_id = paper.id
        return workflow
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
        reason="登记现有试卷管理上下文；不改变正式批次",
        document_mode="text",
        listening_pages={},
        rules_manifest=rules,
        workflow_contract="library.v1",
        origin_manifest={"type": "LEGACY_PAPER", "exam_paper_id": paper.id},
        method_manifest_hash=rules["manifest_hash"],
        created_by=user_id,
    )
    db.add(revision)
    db.flush()
    workflow.current_revision_id = revision.id
    return workflow


def snapshot(db, paper):
    batch = db.scalar(
        select(b.ImportBatch).where(
            b.ImportBatch.exam_paper_id == paper.id, b.ImportBatch.is_current.is_(True)
        )
    )
    if (
        paper.exam_level not in {"CET4", "CET6"}
        or paper.exam_month not in {6, 12}
        or paper.paper_set not in {1, 2, 3}
        or paper.expected_question_count not in {None, 25}
    ):
        raise w.conflict(
            "STANDARD_PAPER_REQUIRED", "本轮编辑仅支持标准完整真题，历史正式批次仍保留"
        )
    result = {name: [] for name in c.SECTIONS}
    result.update(
        schema_version="m3.v3",
        rules_manifest=rules_manifest(),
        source_materials=[],
        audio={},
    )
    if not batch:
        return result, {
            "type": "LEGACY_BATCH",
            "batch_id": None,
            "hash": fingerprint(result),
        }
    models = {
        "content_groups": b.ContentGroup,
        "passages": b.Passage,
        "transcript_segments": b.TranscriptSegment,
        "questions": b.Question,
        "presentations": b.Presentation,
    }
    rows = {
        name: list(db.scalars(select(model).where(model.batch_id == batch.id)).all())
        for name, model in models.items()
    }
    ids = {
        name: {
            row.id: str(uuid5(NAMESPACE_URL, f"ssre:legacy:{batch.id}:{name}:{row.id}"))
            for row in values
        }
        for name, values in rows.items()
    }
    db_ids = {
        "id",
        "batch_id",
        "exam_paper_id",
        "audio_id",
        "basis_paper_id",
        "source_paper_id",
        "genre_id",
        "passage_id",
        "question_id",
        "question_segment_id",
        "created_at",
        "updated_at",
    }
    for name, values in rows.items():
        for row in values:
            value = {
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
                if column.name not in db_ids
            }
            value["_src_id"] = ids[name][row.id]
            for source, target, section in (
                ("passage_id", "passage_src_id", "passages"),
                ("question_id", "question_src_id", "questions"),
                (
                    "question_segment_id",
                    "question_segment_src_id",
                    "transcript_segments",
                ),
            ):
                identity = getattr(row, source, None)
                if identity is not None:
                    value[target] = ids[section].get(identity)
            if name == "transcript_segments":
                value["alignment_status"] = "requires_review"
            if name in {"questions", "passages", "transcript_segments"}:
                value["source_refs"] = []
            result[name].append(value)
    audio = (
        db.get(b.AudioFile, batch.audio_id or paper.playback_audio_id)
        if batch.audio_id or paper.playback_audio_id
        else None
    )
    if audio:
        result["audio"] = {
            k: getattr(audio, k)
            for k in (
                "audio_code",
                "duration_ms",
                "format",
                "mime_type",
                "file_hash",
                "collector",
            )
        }
    # Legacy annotations remain auditable and visible in their formal batch.
    # They are not reclassified as valid empty V7 results in this new edit draft.
    historical = {}
    for name, model in (
        ("skills", a.SkillQuestionRelation),
        ("errors", a.ErrorQuestionRelation),
        ("other_relations", a.OtherRelation),
        ("evidences", a.EvidenceItem),
    ):
        historical[name] = [
            {
                column.name: getattr(row, column.name)
                for column in model.__table__.columns
            }
            for row in db.scalars(select(model).where(model.batch_id == batch.id)).all()
        ]
    result["legacy_annotation_snapshot"] = jsonable_encoder(historical)
    return result, {
        "type": "LEGACY_BATCH",
        "batch_id": batch.id,
        "hash": fingerprint(result),
        "source_review": "required",
        "listening": "not_claimed",
        "annotations": "legacy_requires_revalidation",
    }
