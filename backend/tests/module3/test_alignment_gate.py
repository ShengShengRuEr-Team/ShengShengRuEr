"""The user checkpoint must prevent assembly, paid calls and business persistence."""

from datetime import timedelta
from uuid import UUID, uuid4


def test_alignment_checkpoint_prevents_all_downstream_calls(
    context, client, monkeypatch
):
    from app.db.base import SessionLocal
    from app.module3 import worker
    from app.services.processing import tasks

    task_id, token = UUID(context["task_id"]), uuid4()
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id, lock=True)
        assert task.request["stop_after"] == "align"
        task.state, task.lease_token = "running", token
        task.expires_at = tasks.utcnow() + timedelta(seconds=120)
        db.commit()
    monkeypatch.setattr(worker, "diagnose", lambda *a: {"status": "PASS", "issues": []})
    monkeypatch.setattr(worker, "run_ocr", lambda *a: {"pages": []})
    monkeypatch.setattr(
        worker.audio,
        "decode",
        lambda *a: {
            "normalized_sha256": "0" * 64,
            "duration_ms": 3000,
        },
    )
    monkeypatch.setattr(
        worker.audio,
        "transcribe",
        lambda *a: {
            "segments": [
                {"text": "The answer is Alpha.", "start": 0.0, "end": 1.8},
            ]
        },
    )
    monkeypatch.setattr(
        worker.audio,
        "align",
        lambda *a: {
            "segments": [
                {
                    "_src_id": "seg:1",
                    "text": "The answer is Alpha.",
                    "start_ms": 0,
                    "end_ms": 1800,
                    "alignment_status": "aligned",
                },
            ],
            "issues": [],
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Downstream processing crossed the user checkpoint")

    monkeypatch.setattr(worker, "assemble", forbidden)
    from app.module3 import llm

    monkeypatch.setattr(llm, "request_json", forbidden)
    monkeypatch.setattr(worker, "persist_result", forbidden)
    assert worker.process(task_id, token, context["settings"]) == 0
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        assert (task.state, task.stage, task.batch_id) == (
            "awaiting_confirmation",
            "align",
            None,
        )
        assert task.issues[0]["issue_code"] == "ALIGNMENT_REVIEW_REQUIRED"
        assert tasks.get_draft(db, task, "auto_draft") is None
    url = f"/api/v1/admin/processing-tasks/{task_id}/stages/align"
    response = client.get(url, headers=context["headers"])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["result"]["segments"][0]["text"] == "The answer is Alpha."
    assert "storage_key" not in data
    assert client.get(url).status_code == 401


def test_missing_stage_is_explicit(context, client):
    url = f"/api/v1/admin/processing-tasks/{context['task_id']}/stages/align"
    response = client.get(url, headers=context["headers"])
    assert response.status_code == 200 and response.json()["data"]["missing"] is True


def test_method_change_blocks_before_environment_or_inference(context, monkeypatch):
    from app.db.base import SessionLocal
    from app.module3 import worker
    from app.module3.contracts import fingerprint
    from app.services.processing import tasks

    task_id, token = UUID(context["task_id"]), uuid4()
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id, lock=True)
        changed = dict(task.method)
        changed["implementation_sha256"] = {"app/module3/audio.py": "0" * 64}
        task.method, task.method_hash = changed, fingerprint(changed)
        task.state, task.lease_token = "running", token
        task.expires_at = tasks.utcnow() + timedelta(seconds=120)
        db.commit()

    def forbidden(*args, **kwargs):
        raise AssertionError("Stale method must be rejected before inference")

    monkeypatch.setattr(worker, "diagnose", forbidden)
    assert worker.process(task_id, token, context["settings"]) == 2
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        assert task.state == "awaiting_confirmation"
        assert task.issues[-1]["issue_code"] == "METHOD_CHANGED"


def test_review_export_preserves_empty_human_reference_fields(tmp_path):
    import csv

    from app.module3.alignment_review import export_review

    rows = [
        {
            "_src_id": f"seg:{i}",
            "start_ms": i * 1000,
            "end_ms": i * 1000 + 500,
            "text": f"Synthetic sentence {i}.",
            "alignment_status": "aligned",
        }
        for i in range(2)
    ]
    export_review(
        tmp_path, {"segments": rows, "issues": []}, {"technical_status": "PASS"}
    )
    with (tmp_path / "boundary-review-template.tsv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        exported = list(csv.DictReader(stream, delimiter="\t"))
    assert len(exported) == 2
    assert {row["segment_id"] for row in exported} == {"seg:0", "seg:1"}
    assert all(
        row["reference_start_ms"]
        == row["reference_end_ms"]
        == row["text_correct"]
        == ""
        for row in exported
    )
