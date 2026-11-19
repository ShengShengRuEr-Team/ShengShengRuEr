"""Saved-response reuse must preserve source identity and actual call ancestry."""

import copy
from types import SimpleNamespace


def test_runtime_compatibility_rejects_semantic_changes():
    from app.module3.annotation_identity import rules_manifest
    from app.services.processing.candidate_recovery import runtime_compatible

    current = rules_manifest()
    previous = copy.deepcopy(current)
    previous["implementation"]["app/module3/workflow_worker.py"] = "0" * 64
    assert runtime_compatible(previous, current)
    for key in ("prompt_version", "check_version", "dictionary_sha256"):
        altered = copy.deepcopy(previous)
        altered[key] = "different"
        assert not runtime_compatible(altered, current)
    altered = copy.deepcopy(previous)
    altered["implementation"]["app/module3/option_annotations.py"] = "0" * 64
    assert not runtime_compatible(altered, current)


def test_response_provenance_follows_retries_and_rejects_forgery(monkeypatch):
    from app.services.processing import candidate_recovery as recovery

    manifest = {"implementation": {}, "prompt_version": "synthetic-test"}
    revision = SimpleNamespace(
        id="revision", workflow_id="workflow", rules_manifest=manifest
    )
    attempt = SimpleNamespace(id=7, task_id=1)
    artifacts = {
        number: SimpleNamespace(id=number, task_id=number, stage="workflow_candidate")
        for number in (1, 2, 3)
    }
    payloads = {
        number: {
            "call": {
                "attempt_id": 7,
                **(
                    {
                        "reused_from_artifact_id": number - 1,
                        "response_source_task_id": "1",
                    }
                    if number > 1
                    else {}
                ),
            },
            "candidate": {"question_src_id": "q:1"},
            "question_input_hash": "synthetic-hash",
            "rules_manifest": manifest,
        }
        for number in (1, 2, 3)
    }

    class Database:
        def get(self, model, identity):
            return SimpleNamespace(workflow_id="workflow", revision_id="revision")

    monkeypatch.setattr(
        recovery.o,
        "artifact_payload",
        lambda db, identity, settings: (payloads[identity], artifacts[identity]),
    )
    db = Database()
    assert recovery.response_task_matches(
        db, artifacts[3], attempt, payloads[3], revision, None
    )
    forged = copy.deepcopy(payloads[3])
    forged["call"]["response_source_task_id"] = "other"
    assert not recovery.response_task_matches(
        db, artifacts[3], attempt, forged, revision, None
    )
    forged = copy.deepcopy(payloads[3])
    forged["candidate"] = {"question_src_id": "q:2"}
    assert not recovery.response_task_matches(
        db, artifacts[3], attempt, forged, revision, None
    )
    payloads[2]["call"]["reused_from_artifact_id"] = 3
    assert not recovery.response_task_matches(
        db, artifacts[3], attempt, payloads[3], revision, None
    )
