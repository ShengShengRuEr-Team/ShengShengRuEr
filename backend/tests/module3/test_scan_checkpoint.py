"""Image headings and corrected drafts must retain ownership and scope."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest


def test_split_scan_heading_and_compact_question_heading():
    from app.module3.source_assembly import paper_options

    pages = [
        {
            "source_kind": "paper_scan",
            "material_id": 1,
            "page": 1,
            "text": (
                "Part II\nListening Comprehension\nQuestions1 to 2\n"
                "1. A) One.\nB) Two.\nC) Three.\nD) Four.\n"
                "Questions3 to 4\nPart III Reading"
            ),
        }
    ]
    questions = paper_options(pages)
    assert list(questions) == [1]
    assert questions[1]["options"] == dict(
        zip("ABCD", ("One.", "Two.", "Three.", "Four."), strict=True)
    )


@pytest.mark.parametrize(
    "stop,stage",
    [
        ("assemble", "assemble"),
        ("annotate_sample", "annotate"),
        ("annotate", "annotate"),
    ],
)
def test_correction_worker_preserves_auto_and_does_not_import(
    context, monkeypatch, stop, stage
):
    from app.db.base import SessionLocal
    from app.module3 import worker
    from app.services.processing import tasks

    task_id, token = UUID(context["task_id"]), uuid4()
    original = context["clone"]()
    corrected = context["clone"]()
    corrected["questions"][0]["option_a"] = "Alpha."
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id, lock=True)
        task.request = {**task.request, "correction": True, "stop_after": stop}
        task.state, task.lease_token = "running", token
        task.expires_at = tasks.utcnow() + timedelta(seconds=120)
        tasks.store_draft(db, task, original, view="auto_draft")
        tasks.store_draft(db, task, corrected, view="final")
        db.commit()
    monkeypatch.setattr(worker, "diagnose", lambda *a: {"status": "PASS", "issues": []})

    def forbidden(*a, **kw):
        raise AssertionError("Correction crossed the authorized draft checkpoint")

    monkeypatch.setattr(worker, "assemble", forbidden)
    monkeypatch.setattr(worker, "persist_result", forbidden)
    monkeypatch.setattr(worker, "run_ocr", forbidden)
    monkeypatch.setattr(
        worker.llm
        if hasattr(worker, "llm")
        else __import__("app.module3.llm", fromlist=["request_json"]),
        "request_json",
        forbidden,
    )
    assert worker.process(task_id, token, context["settings"]) == 0
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        assert (task.state, task.stage, task.batch_id) == (
            "awaiting_confirmation",
            stage,
            None,
        )
        assert tasks.get_draft(db, task, "auto_draft").payload == original
        assert tasks.get_draft(db, task, "final").payload == corrected
