"""Publication state distinguishes local provenance from actual model generation."""

from uuid import UUID

from sqlalchemy import text

from app.db import models_library as l
from app.db import models_processing_workflows as m
from app.module3.annotation_identity import ERROR_RULE_VERSION, question_input_hash
from app.module3.contracts import ProcessingError


def insert_local_states(db, task, batch, payload, maps, revision, session):
    identity = payload["library_provenance"]
    source_type = "MANUAL" if identity["origin_type"] == "MANUAL" else "MIXED"
    for question in payload["questions"]:
        qid = question["_src_id"]
        nonempty = any(
            a["question_src_id"] == qid and a["status"] == "SUPPORTED"
            for a in payload["distractor_assessments"]
        )
        db.execute(
            text("""INSERT INTO question_annotation_states
          (batch_id,question_id,revision_id,result_hash,rule_version,rules_manifest_hash,
           question_input_hash,generation_state,review_session_id,source_type,library_save_version_id,origin_task_id)
          VALUES(:b,:q,:r,:h,:rule,:rules,:input,:state,:session,:source,:version,:task)"""),
            {
                "b": batch.id,
                "q": maps["questions"][qid],
                "r": revision.id,
                "h": revision.final_result_hash,
                "rule": ERROR_RULE_VERSION,
                "rules": revision.rules_manifest["manifest_hash"],
                "input": question_input_hash(payload, question),
                "state": source_type.lower() + ("_nonempty" if nonempty else "_empty"),
                "session": session.id,
                "source": source_type,
                "version": UUID(identity["save_version_id"]),
                "task": task.id,
            },
        )
    version = db.get(l.LibrarySaveVersion, UUID(identity["save_version_id"]))
    db.add(
        l.LibraryVersionReference(
            save_version_id=version.id, kind="formal_batch", reference=str(batch.id)
        )
    )


def local_state_receipts(db, batch, payload):
    identity = payload["library_provenance"]
    version = db.get(l.LibrarySaveVersion, UUID(identity["save_version_id"]))
    revision = db.get(m.ProcessingWorkflowRevision, version.revision_id)
    states = (
        db.execute(
            text("SELECT * FROM question_annotation_states WHERE batch_id=:b"),
            {"b": batch.id},
        )
        .mappings()
        .all()
    )
    if any(
        r["source_type"] not in {"MANUAL", "MIXED"}
        or r["library_save_version_id"] != version.id
        or r["origin_task_id"] != revision.final_task_id
        for r in states
    ):
        raise ProcessingError(
            "BATCH_INCOMPLETE", "人工/混合来源的保存版本或本地执行身份无效"
        )
    source = "manual" if identity["origin_type"] == "MANUAL" else "mixed"
    return [
        {
            "question_src_id": q["_src_id"],
            "task_id": None,
            "artifact_id": None,
            "question_input_hash": question_input_hash(payload, q),
            "state": source
            + (
                "_nonempty"
                if any(
                    a["question_src_id"] == q["_src_id"] and a["status"] == "SUPPORTED"
                    for a in payload["distractor_assessments"]
                )
                else "_empty"
            ),
        }
        for q in payload["questions"]
    ]
