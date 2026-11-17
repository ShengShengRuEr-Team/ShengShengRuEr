"""Revalidate saved responses on explicit retries; never replay invalid candidates."""

import json
from uuid import UUID

from sqlalchemy import select

from app.db import models_processing as p
from app.module3.annotation_identity import question_input_hash
from app.module3.contracts import ProcessingError, fingerprint
from app.module3.option_annotations import (
    SYSTEM_PROMPT_V2,
    check_option_candidate,
)
from app.services.processing import orchestration as o


def runtime_compatible(before, after):
    # These runtime fixes do not change the dictionary, prompt, checks, source
    # content or option rules. Every saved response is checked again below.
    if {
        k: v for k, v in before.items() if k not in {"implementation", "manifest_hash"}
    } != {
        k: v for k, v in after.items() if k not in {"implementation", "manifest_hash"}
    }:
        return False
    left, right = before.get("implementation", {}), after.get("implementation", {})
    changed = {
        key for key in left.keys() | right.keys() if left.get(key) != right.get(key)
    }
    return changed <= {
        "app/module3/workflow_worker.py",
        "app/services/processing/reviewing.py",
        "app/services/processing/candidate_recovery.py",
        "app/module3/annotation_identity.py",
    }


def saved_candidate(db, task, revision, payload, question, settings):
    from app.module3.workflow_worker import generation_input
    from app.services.processing.reprocessing import ancestor_revision

    recovery_id = task.request.get("recovery_task_id")
    if not recovery_id:
        return None
    source_task = db.get(p.ProcessingTask, UUID(recovery_id))
    if not source_task or not ancestor_revision(db, revision, source_task):
        raise ProcessingError("ARTIFACT_CHANGED", "恢复任务不属于当前工作流祖先")
    if not runtime_compatible(
        source_task.method["rules_manifest"], revision.rules_manifest
    ):
        return None
    for artifact in db.scalars(
        select(p.ProcessingArtifact)
        .where(
            p.ProcessingArtifact.task_id == source_task.id,
            p.ProcessingArtifact.stage == "workflow_candidate",
        )
        .order_by(p.ProcessingArtifact.id.desc())
    ):
        raw, _ = o.artifact_payload(db, artifact.id, settings)
        if raw.get("question_src_id") != question["_src_id"]:
            continue
        call = db.get(p.LlmAttempt, raw["call"]["attempt_id"])
        if (
            not call
            or call.status != "succeeded"
            or not response_task_matches(db, artifact, call, raw, revision, settings)
        ):
            continue
        if (
            raw.get("question_input_hash") != question_input_hash(payload, question)
            or raw["call"]["request_hash"] != fingerprint(call.request_payload)
            or json.loads(call.request_payload["messages"][1]["content"])
            != generation_input(payload, question, task.request)
            or not call.request_payload["messages"][0]["content"].startswith(
                SYSTEM_PROMPT_V2
            )
            or json.loads(call.response_payload["choices"][0]["message"]["content"])
            != raw["candidate"]
        ):
            continue
        try:
            check_option_candidate(payload, question, raw["candidate"])
        except (ValueError, ProcessingError):
            continue
        return raw["candidate"], {
            **raw["call"],
            "reused_from_artifact_id": artifact.id,
            "response_source_task_id": str(call.task_id),
        }
    return None


def response_task_matches(db, artifact, call, raw, revision, settings, depth=0):
    from app.services.processing.reprocessing import ancestor_revision

    if call.task_id == artifact.task_id:
        return True
    if depth >= 20:
        return False
    source_id = raw["call"].get("reused_from_artifact_id")
    if not source_id:
        return False
    source, source_artifact = o.artifact_payload(db, source_id, settings)
    source_task = db.get(p.ProcessingTask, source_artifact.task_id)
    return bool(
        source_task
        and ancestor_revision(db, revision, source_task)
        and source_artifact.id < artifact.id
        and source_artifact.stage == "workflow_candidate"
        and raw["call"].get("response_source_task_id") == str(call.task_id)
        and source["call"]["attempt_id"] == call.id
        and source["candidate"] == raw["candidate"]
        and source["question_input_hash"] == raw["question_input_hash"]
        and runtime_compatible(source["rules_manifest"], revision.rules_manifest)
        and response_task_matches(
            db, source_artifact, call, source, revision, settings, depth + 1
        )
    )
