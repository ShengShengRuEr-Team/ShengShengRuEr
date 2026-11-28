"""Recoverable pending -> validating -> activating publication, never auto-open."""

from uuid import UUID

from sqlalchemy import select, text, update

from app.db import models_annotations as a
from app.db import models_listening as l
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.db.base import SessionLocal
from app.module3.annotation_identity import CHECK_VERSION, ERROR_RULE_VERSION
from app.module3.contracts import ProcessingError
from app.schemas_processing import ActivationRequest
from app.services.processing import persistence, reviewing, tasks
from app.services.processing import workflows as w
from app.services.processing.validation import entity_index, evidence_details


def begin(db, workflow_id, payload, user_id, key):
    old, digest, body = w.begin_command(
        db, user_id, "publish", key, workflow_id, payload
    )
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if (
        workflow.exam_paper_id
        and db.get(l.ExamPaper, workflow.exam_paper_id).archived_at
    ):
        raise w.conflict("PAPER_ARCHIVED", "归档试卷不能开始发布")
    session = db.get(m.ProcessingReviewSession, payload.review_session_id)
    if (
        not session
        or session.revision_id != revision.id
        or session.state != "approved"
        or payload.expected_result_hash != revision.final_result_hash
        or session.result_hash != revision.final_result_hash
    ):
        raise w.conflict("REVIEW_INCOMPLETE", "须先提交当前最终版本的完整逐题审核")
    active = db.scalar(
        select(m.ProcessingWorkflowCommand.id)
        .where(
            m.ProcessingWorkflowCommand.revision_id == revision.id,
            m.ProcessingWorkflowCommand.state.in_(["accepted", "running"]),
        )
        .limit(1)
    )
    if active:
        raise w.conflict("VERSION_CONFLICT", "当前修订已有执行操作")
    if payload.retry_of_operation_id:
        previous = db.get(m.ProcessingWorkflowCommand, payload.retry_of_operation_id)
        if (
            not previous
            or previous.revision_id != revision.id
            or previous.action != "publish"
            or previous.state not in {"failed", "conflict", "stopped"}
        ):
            raise w.conflict("VERSION_CONFLICT", "发布重试来源不匹配")
    workflow.publication_state = "preparing"
    workflow.processing_state = "queued"
    workflow.row_version += 1
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "publish",
        key,
        digest,
        body,
        {
            "stage": "publish",
            "checkpoint": "preparing",
            "row_version": workflow.row_version,
        },
        state="accepted",
        retry_of_operation_id=payload.retry_of_operation_id,
    )


def insert_annotation_states(db, task, paper, batch, payload, maps):
    workflow = db.get(m.ProcessingWorkflow, task.workflow_id)
    workflow.exam_paper_id = paper.id
    revision = db.get(m.ProcessingWorkflowRevision, task.revision_id)
    session = db.scalar(
        select(m.ProcessingReviewSession).where(
            m.ProcessingReviewSession.revision_id == revision.id,
            m.ProcessingReviewSession.result_hash == revision.final_result_hash,
            m.ProcessingReviewSession.state == "approved",
        )
    )
    if not session:
        raise ProcessingError("REVIEW_REQUIRED", "入库缺少实际整套审核")
    for section, mapping in maps.items():
        for src_id, identity in mapping.items():
            db.execute(
                text("""INSERT INTO processing_batch_identities
                (batch_id,entity_type,src_id,entity_id) VALUES (:b,:s,:src,:id)"""),
                {"b": batch.id, "s": section, "src": src_id, "id": identity},
            )
    if payload.get("library_provenance"):
        from app.services.processing.library_publication import insert_local_states

        insert_local_states(db, task, batch, payload, maps, revision, session)
    for receipt in payload["generation_receipts"]:
        db.execute(
            text("""INSERT INTO question_annotation_states
          (batch_id,question_id,revision_id,result_hash,rule_version,rules_manifest_hash,
           question_input_hash,generation_state,generation_task_id,
           candidate_artifact_id,review_session_id)
          VALUES (:b,:q,:r,:h,:rule,:rules,:input,
                  :state,:task,:artifact,:session)"""),
            {
                "b": batch.id,
                "rule": ERROR_RULE_VERSION,
                "q": maps["questions"][receipt["question_src_id"]],
                "r": revision.id,
                "h": revision.final_result_hash,
                "rules": revision.rules_manifest["manifest_hash"],
                "input": receipt["question_input_hash"],
                "state": receipt["state"],
                "task": UUID(receipt["task_id"]),
                "artifact": receipt["artifact_id"],
                "session": session.id,
            },
        )
    for assessment in payload["distractor_assessments"]:
        qid = maps["questions"][assessment["question_src_id"]]
        db.execute(
            text("""INSERT INTO question_distractor_assessments
          (batch_id,question_id,option_letter,rule_version,status,reason,unresolved_points,source_candidate_hash)
          VALUES(:b,:q,:o,:rule,:s,:reason,CAST(:g AS jsonb),:hash)"""),
            {
                "b": batch.id,
                "q": qid,
                "o": assessment["option_letter"],
                "rule": ERROR_RULE_VERSION,
                "s": assessment["status"],
                "reason": assessment["reason"],
                "g": __import__("json").dumps(assessment["unresolved_points"]),
                "hash": assessment["source_candidate_hash"],
            },
        )
        for order, ref in enumerate(assessment["comparison_evidence_refs"], 1):
            db.execute(
                text("""INSERT INTO question_distractor_comparison_evidences
              (batch_id,question_id,option_letter,sort_order,evidence_id,support_note)
              VALUES(:b,:q,:o,:n,:e,:note)"""),
                {
                    "b": batch.id,
                    "q": qid,
                    "o": assessment["option_letter"],
                    "n": order,
                    "e": maps["evidences"][ref["evidence_src_id"]],
                    "note": ref["support_note"],
                },
            )
    db.flush()


def verify_actual_batch(db, batch, payload):
    from app.module3.contracts import fingerprint

    actual_refs = db.scalars(
        select(p.BatchSourceRef).where(p.BatchSourceRef.batch_id == batch.id)
    ).all()
    expected_refs = []
    for section in ("passages", "transcript_segments", "questions"):
        for row in payload.get(section, []):
            for ref in row.get("source_refs", []):
                expected_refs.append(
                    {
                        "entity_type": section,
                        "src_id": str(row["_src_id"]),
                        "material_id": ref["material_id"],
                        "locator": ref["locator"],
                        "original_text": ref.get("original_text"),
                        "conversion_hash": ref.get("conversion_hash"),
                    }
                )
    fields = (
        "entity_type",
        "src_id",
        "material_id",
        "locator",
        "original_text",
        "conversion_hash",
    )
    if sorted(map(fingerprint, expected_refs)) != sorted(
        fingerprint({key: getattr(row, key) for key in fields}) for row in actual_refs
    ):
        raise ProcessingError("BATCH_INCOMPLETE", "实际原件定位与冻结结果不符")
    rows = db.execute(
        text(
            "SELECT entity_type,src_id,entity_id FROM processing_batch_identities "
            "WHERE batch_id=:b"
        ),
        {"b": batch.id},
    ).all()
    maps = {}
    for section, src_id, identity in rows:
        maps.setdefault(section, {})[src_id] = identity
    actual_assessments = (
        db.execute(
            text("SELECT * FROM question_distractor_assessments WHERE batch_id=:b"),
            {"b": batch.id},
        )
        .mappings()
        .all()
    )
    expected_assessments = payload.get("distractor_assessments", [])
    if len(actual_assessments) != len(expected_assessments):
        raise ProcessingError("BATCH_INCOMPLETE", "评估数量与冻结结果不符")
    for assessment in expected_assessments:
        qid = maps["questions"][assessment["question_src_id"]]
        actual = next(
            (
                a
                for a in actual_assessments
                if a["question_id"] == qid
                and a["option_letter"] == assessment["option_letter"]
            ),
            None,
        )
        if not actual or any(
            actual[k] != assessment[k]
            for k in (
                "rule_version",
                "status",
                "reason",
                "unresolved_points",
                "source_candidate_hash",
            )
        ):
            raise ProcessingError("BATCH_INCOMPLETE", "评估内容与冻结结果不符")
        actual_refs = db.execute(
            text("""SELECT evidence_id,sort_order,support_note
          FROM question_distractor_comparison_evidences
          WHERE batch_id=:b AND question_id=:q
          AND option_letter=:o ORDER BY sort_order"""),
            {"b": batch.id, "q": qid, "o": assessment["option_letter"]},
        ).all()
        expected_refs = [
            (maps["evidences"][r["evidence_src_id"]], n, r["support_note"])
            for n, r in enumerate(assessment["comparison_evidence_refs"], 1)
        ]
        if [tuple(r) for r in actual_refs] != expected_refs:
            raise ProcessingError("BATCH_INCOMPLETE", "比较证据或顺序与冻结结果不符")
    states = (
        db.execute(
            text("SELECT * FROM question_annotation_states WHERE batch_id=:b"),
            {"b": batch.id},
        )
        .mappings()
        .all()
    )
    revision = db.scalar(
        select(m.ProcessingWorkflowRevision).where(
            m.ProcessingWorkflowRevision.batch_id == batch.id
        )
    )
    receipts = payload.get("generation_receipts", [])
    if payload.get("library_provenance"):
        from app.services.processing.library_publication import local_state_receipts

        receipts = local_state_receipts(db, batch, payload)
    expected_states = {
        maps.get("questions", {}).get(r["question_src_id"]): r for r in receipts
    }
    if (
        not revision
        or len(states) != len(receipts)
        or any(
            row["question_id"] not in expected_states
            or row["result_hash"] != revision.final_result_hash
            or row["revision_id"] != revision.id
            or row["generation_state"] != expected_states[row["question_id"]]["state"]
            or row["generation_task_id"]
            != (
                UUID(expected_states[row["question_id"]]["task_id"])
                if expected_states[row["question_id"]].get("task_id")
                else None
            )
            or row["candidate_artifact_id"]
            != expected_states[row["question_id"]]["artifact_id"]
            or row["question_input_hash"]
            != expected_states[row["question_id"]]["question_input_hash"]
            for row in states
        )
    ):
        raise ProcessingError("BATCH_INCOMPLETE", "实际逐题生成身份与冻结结果不符")
    models = {
        "content_groups": l.ContentGroup,
        "passages": l.Passage,
        "transcript_segments": l.TranscriptSegment,
        "questions": l.Question,
        "presentations": l.Presentation,
        "language_items": a.LanguageItem,
        "evidences": a.EvidenceItem,
        "skill_question_relations": a.SkillQuestionRelation,
        "error_question_relations": a.ErrorQuestionRelation,
        "other_relations": a.OtherRelation,
    }
    segments = entity_index(payload["transcript_segments"], "segments")
    passages = entity_index(payload["passages"], "passages")
    for section, model in models.items():
        expected_rows = payload.get(section, [])
        actual_rows = db.scalars(select(model).where(model.batch_id == batch.id)).all()
        if len(actual_rows) != len(expected_rows) or len(maps.get(section, {})) != len(
            expected_rows
        ):
            raise ProcessingError(
                "BATCH_INCOMPLETE", "pending批次内容/关系数量与冻结结果不符"
            )
        actual = {row.id: row for row in actual_rows}
        for expected in expected_rows:
            row = actual.get(maps[section].get(expected["_src_id"]))
            if not row:
                raise ProcessingError("BATCH_INCOMPLETE", "pending批次身份映射不完整")
            values = persistence.column_values(
                model, expected, exclude=("review_status",)
            )
            for src, dst, target in (
                ("passage_src_id", "passage_id", "passages"),
                ("question_src_id", "question_id", "questions"),
                (
                    "question_segment_src_id",
                    "question_segment_id",
                    "transcript_segments",
                ),
                ("evidence_src_id", "evidence_id", "evidences"),
                ("owner_relation_src_id", "owner_relation_id", section),
            ):
                if expected.get(src):
                    values[dst] = maps[target][expected[src]]
            if section == "evidences":
                values.update(
                    evidence_details(
                        expected, segments, passages[expected["passage_src_id"]]
                    )
                )
                from app.db.models_annotations import EvidenceSegment

                actual_segments = db.scalars(
                    select(EvidenceSegment).where(EvidenceSegment.evidence_id == row.id)
                ).all()
                if {(r.segment_id, r.sort_order) for r in actual_segments} != {
                    (maps["transcript_segments"][src], index)
                    for index, src in enumerate(expected["segment_src_ids"], 1)
                }:
                    raise ProcessingError("BATCH_INCOMPLETE", "证据句序与冻结结果不符")
            for code_field, id_field, model_type, column in (
                ("skill_code", "skill_id", a.Skill, a.Skill.skill_code),
                (
                    "error_cause_code",
                    "error_cause_id",
                    a.ErrorCause,
                    a.ErrorCause.error_cause_code,
                ),
            ):
                if expected.get(code_field):
                    values[id_field] = db.scalar(
                        select(model_type.id).where(column == expected[code_field])
                    )
            if any(getattr(row, field) != value for field, value in values.items()):
                raise ProcessingError(
                    "BATCH_INCOMPLETE", "pending批次实际内容与冻结结果不符"
                )


def execute_publication(command_id, token, settings):
    from app.module3.workflow_worker import fence

    with SessionLocal() as db:
        workflow, revision, command = fence(db, command_id, token)
        task = tasks.get_task(db, revision.final_task_id)
        draft = tasks.get_draft(db, task)
        reviewing.validate_final(db, draft.payload, task.request, revision, settings)
        current = db.scalar(
            select(l.ImportBatch).where(
                l.ImportBatch.exam_paper_id == workflow.exam_paper_id,
                l.ImportBatch.is_current.is_(True),
            )
        )
        if (current.id if current else None) != command.request[
            "expected_current_batch_id"
        ] and (not current or current.id != revision.batch_id):
            raise w.conflict("CURRENT_BATCH_CHANGED", "正式当前批次已变化，须刷新核对")
        audio = next(
            material
            for material in tasks.task_materials(db, task.id)
            if material.source_kind == "audio"
        )
        batch = persistence.persist_result(
            db,
            task.id,
            None,
            draft.payload,
            tasks.verify_material(audio, settings),
            settings,
            execution_guard=lambda connection: fence(connection, command_id, token),
        )
        if not batch:
            raise ProcessingError("BATCH_INCOMPLETE", "pending入库校验失败")
        revision.batch_id = batch.id
        workflow.publication_state = "pending_batch"
        command.result = {
            **command.result,
            "checkpoint": "pending_batch",
            "batch_id": batch.id,
            "exam_paper_id": batch.exam_paper_id,
        }
        db.commit()
    with SessionLocal() as db:
        workflow, revision, command = fence(db, command_id, token)
        task = tasks.get_task(db, revision.final_task_id)
        draft = tasks.get_draft(db, task)
        batch = db.get(l.ImportBatch, revision.batch_id)
        if (
            batch.result_hash != revision.final_result_hash
            or batch.exam_paper_id != workflow.exam_paper_id
        ):
            raise ProcessingError("BATCH_INCOMPLETE", "既有pending批次来源或结果不匹配")
        verify_actual_batch(db, batch, draft.payload)
        reviews = tasks.latest_reviews(db, task)
        if set(reviews) != {"content", "audio", "annotations"} or any(
            r.decision != "approved" for r in reviews.values()
        ):
            raise ProcessingError(
                "REVIEW_REQUIRED", "实际批次缺少同最终哈希的完整审核记录"
            )
        # Project already submitted human decisions onto the pending business
        # rows. Do not invent a reviewer or alter the immutable automatic draft.
        for model in (
            l.ContentGroup,
            l.Passage,
            l.Question,
            l.Presentation,
            l.TranscriptSegment,
            a.EvidenceItem,
            a.SkillQuestionRelation,
            a.ErrorQuestionRelation,
            a.OtherRelation,
            a.LanguageItem,
        ):
            db.execute(
                update(model)
                .where(model.batch_id == batch.id)
                .values(review_status="已通过")
            )
        check = tasks.check_result(db, task.id, revision.final_result_hash, settings)
        check.rule_version = CHECK_VERSION
        if not check.is_passed:
            db.commit()
            raise ProcessingError("BATCH_INCOMPLETE", "实际pending批次检查未通过")
        db.info["workflow_publication"] = command.id
        result = tasks.activate(
            db,
            workflow.exam_paper_id,
            ActivationRequest(
                task_id=task.id,
                batch_id=batch.id,
                check_id=check.id,
                result_hash=revision.final_result_hash,
                expected_current_batch_id=command.request["expected_current_batch_id"],
            ),
            command.created_by,
        )
        paper = db.get(l.ExamPaper, workflow.exam_paper_id)
        paper.expected_question_count_source = task.request[
            "expected_question_count_source"
        ]
        workflow.processing_state, workflow.publication_state = "completed", "published"
        workflow.row_version += 1
        command.state, command.execution_token, command.lease_expires_at = (
            "succeeded",
            None,
            None,
        )
        command.result = {**command.result, **result, "checkpoint": "published"}
        db.commit()
    return 0
