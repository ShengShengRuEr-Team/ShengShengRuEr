"""Reference text is authoritative; the reference route must never invoke ASR."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest


def source_row(**changes):
    return {
        "segment_id": "body:1",
        "text": "The answer is Alpha.",
        "segment_type": "body",
        "passage_key": "p1",
        "question_no": None,
        "source_storage_key": "answer.pdf",
        "source_sha256": "0" * 64,
        "source_pages": [1],
        "search_start_ms": 0,
        "search_end_ms": 2000,
        **changes,
    }


def test_reference_keeps_source_text_id_and_provenance(monkeypatch, tmp_path):
    from app.module3 import reference

    def aligned(normalized, transcription, settings):
        assert transcription["segments"][0]["text"] == "The answer is Alpha."
        return {
            "segments": [
                {
                    "_src_id": "seg:1",
                    "text": "The answer is Alpha.",
                    "start_ms": 120,
                    "end_ms": 1650,
                    "alignment_status": "aligned",
                }
            ],
            "issues": [],
        }

    monkeypatch.setattr(reference.audio, "align", aligned)
    result = reference.align(tmp_path / "synthetic.npy", [source_row()], object())
    segment = result["segments"][0]
    assert segment["_src_id"] == "body:1"
    assert segment["text_source"] == "reference"
    assert segment["source_pages"] == [1]
    assert segment["start_ms"] == 120  # Search-window start is not a final boundary.


def test_alignment_cannot_rewrite_reference(monkeypatch, tmp_path):
    from app.module3 import reference
    from app.module3.contracts import ProcessingError

    monkeypatch.setattr(
        reference.audio,
        "align",
        lambda *a: {
            "segments": [{"_src_id": "seg:1", "text": "Invented recognition text."}],
            "issues": [],
        },
    )
    with pytest.raises(ProcessingError) as error:
        reference.align(tmp_path / "synthetic.npy", [source_row()], object())
    assert error.value.code == "REFERENCE_TEXT_CHANGED"


@pytest.mark.parametrize("retry_score", [0.98, 0.20])
def test_weak_window_retries_from_neighbours_without_changing_source(
    monkeypatch, tmp_path, retry_score
):
    from app.module3 import reference

    calls = []
    sources = [
        source_row(segment_id="s:1", text="Alpha.", search_end_ms=3000),
        source_row(
            segment_id="s:2",
            text="Beta.",
            search_start_ms=4000,
            search_end_ms=5000,
        ),
        source_row(
            segment_id="s:3",
            text="Gamma.",
            search_start_ms=8000,
            search_end_ms=9000,
        ),
    ]

    def part(text, start, end, score):
        return {
            "_src_id": "seg:" + text,
            "text": text,
            "start_ms": start,
            "end_ms": end,
            "alignment_score": score,
            "alignment_status": "aligned",
            "boundary_method": "m3.reference-ctc.v2",
            "chars": [],
        }

    def align(normalized, request, settings):
        calls.append(request)
        if len(calls) == 1:
            return {
                "segments": [
                    part("Alpha.", 1200, 2800, 0.98),
                    part("Beta.", 4200, 4800, 0.15),
                    part("Gamma.", 8200, 8800, 0.98),
                ],
                "issues": [],
                "duration_ms": 10000,
            }
        self_window = request["segments"][0]
        assert self_window == {"text": "Beta.", "start": 2.55, "end": 8.45}
        return {
            "segments": [part("Beta.", 3300, 7800, retry_score)],
            "issues": [],
        }

    monkeypatch.setattr(reference.audio, "align", align)
    result = reference.align(tmp_path / "synthetic.npy", sources, object())
    row = result["segments"][1]
    assert (row["_src_id"], row["text"]) == ("s:2", "Beta.")
    assert len(calls) == 2 and len(row["search_attempts"]) == 2
    if retry_score == 0.98:
        assert (row["start_ms"], row["end_ms"]) == (3300, 7800)
        assert row["requested_search_start_ms"] == 4000
        assert row["search_start_ms"] == 2550
        assert not result["issues"]
    else:
        assert row["alignment_status"] == "requires_review"
        assert result["issues"][0]["issue_code"] == "ALIGNMENT_LOW_CONFIDENCE"


def test_window_retry_still_rejects_changed_text(monkeypatch, tmp_path):
    from app.module3 import reference
    from app.module3.contracts import ProcessingError

    calls = []

    def align(*args):
        calls.append(True)
        return {
            "segments": [
                {
                    "_src_id": "seg:1",
                    "text": "The answer is Alpha." if len(calls) == 1 else "Invented.",
                    "start_ms": 500,
                    "end_ms": 1500,
                    "alignment_status": "aligned",
                    "alignment_score": 0.1,
                }
            ],
            "issues": [],
            "duration_ms": 10000,
        }

    monkeypatch.setattr(reference.audio, "align", align)
    with pytest.raises(ProcessingError) as caught:
        reference.align(tmp_path / "synthetic.npy", [source_row()], object())
    assert len(calls) == 2 and caught.value.code == "REFERENCE_TEXT_CHANGED"


@pytest.mark.parametrize(
    "retry_score,expected_status", [(0.97, "aligned"), (0.2, "requires_review")]
)
def test_strong_match_at_window_edge_is_retried(
    monkeypatch, tmp_path, retry_score, expected_status
):
    from app.module3 import reference
    from app.module3.ctc_alignment import METHOD_VERSION

    calls = []

    def align(normalized, request, settings):
        calls.append(request)
        return {
            "segments": [
                {
                    "_src_id": "seg:1",
                    "text": "The answer is Alpha.",
                    "start_ms": 120,
                    "end_ms": 1990 if len(calls) == 1 else 1750,
                    "alignment_status": "aligned",
                    "alignment_score": 0.98 if len(calls) == 1 else retry_score,
                    "boundary_method": METHOD_VERSION,
                    "chars": [],
                }
            ],
            "issues": [],
            "duration_ms": 10000,
            "boundary_method": METHOD_VERSION,
        }

    monkeypatch.setattr(reference.audio, "align", align)
    result = reference.align(tmp_path / "synthetic.npy", [source_row()], object())
    assert len(calls) == 2
    assert calls[1]["segments"][0]["end"] == 4.0
    row = result["segments"][0]
    assert row["alignment_status"] == expected_status
    if expected_status == "aligned":
        assert row["search_end_ms"] == 4000
        assert row["requested_search_end_ms"] == 2000
        assert not result["issues"]
    else:
        assert result["issues"][0]["issue_code"] == "ALIGNMENT_SEARCH_EDGE"


def test_neighbour_conflict_is_not_silently_accepted(monkeypatch, tmp_path):
    from app.module3 import reference

    monkeypatch.setattr(
        reference.audio,
        "align",
        lambda *args: {
            "segments": [
                {
                    "_src_id": f"seg:{i}",
                    "text": text,
                    "start_ms": start,
                    "end_ms": end,
                    "alignment_status": "aligned",
                }
                for i, (text, start, end) in enumerate(
                    [("Alpha.", 100, 1800), ("Beta.", 1200, 2000)]
                )
            ],
            "issues": [],
        },
    )
    result = reference.align(
        tmp_path / "synthetic.npy",
        [source_row(text="Alpha."), source_row(segment_id="s:2", text="Beta.")],
        object(),
    )
    assert result["issues"][0]["issue_code"] == "ALIGNMENT_NEIGHBOUR_CONFLICT"
    assert all(r["alignment_status"] == "requires_review" for r in result["segments"])


def test_library_abbreviation_split_keeps_one_source_sentence(monkeypatch, tmp_path):
    from app.module3 import reference

    parts = [
        {
            "_src_id": "seg:1",
            "text": "The U.S.",
            "start_ms": 120,
            "end_ms": 500,
            "alignment_status": "aligned",
        },
        {
            "_src_id": "seg:2",
            "text": "Postal Service.",
            "start_ms": 520,
            "end_ms": 1650,
            "alignment_status": "aligned",
        },
    ]
    monkeypatch.setattr(
        reference.audio, "align", lambda *a: {"segments": parts, "issues": []}
    )
    result = reference.align(
        tmp_path / "synthetic.npy",
        [source_row(text="The U.S. Postal Service.")],
        object(),
    )
    assert len(result["segments"]) == 1
    row = result["segments"][0]
    assert (row["_src_id"], row["text"], row["start_ms"], row["end_ms"]) == (
        "body:1",
        "The U.S. Postal Service.",
        120,
        1650,
    )
    assert len(row["alignment_parts"]) == 2


def test_reference_review_samples_body_sentences(tmp_path):
    import csv

    from app.module3.alignment_review import export_review

    rows = [
        {
            "_src_id": f"s:{i}",
            "text": "Synthetic source sentence.",
            "segment_type": "body" if i < 35 else "question",
            "start_ms": i * 1000,
            "end_ms": i * 1000 + 500,
            "alignment_status": "aligned",
        }
        for i in range(60)
    ]
    export_review(
        tmp_path,
        {"segments": rows, "issues": []},
        {
            "technical_status": "PASS",
            "text_source": "answer_reference",
        },
    )
    with (tmp_path / "boundary-review-template.tsv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        samples = list(csv.DictReader(stream, delimiter="\t"))
    assert len(samples) == 30
    assert all(int(row["segment_id"].split(":")[1]) < 35 for row in samples)
    assert all(
        row["reference_start_ms"] == row["reference_end_ms"] == "" for row in samples
    )


def test_provided_mode_waits_for_reference_without_asr(context, client):
    request = {
        key: value for key, value in context["request"].items() if key != "text_source"
    }
    request["reference_preparation"] = "provided"
    response = client.post(
        "/api/v1/admin/processing-tasks", json=request, headers=context["headers"]
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["state"] == "awaiting_confirmation"
    assert any(
        issue["issue_code"] == "REFERENCE_TEXT_REQUIRED" for issue in data["issues"]
    )


def test_default_source_can_prepare_reference_from_registered_materials(
    context, client
):
    request = {
        key: value
        for key, value in context["request"].items()
        if key
        not in {
            "text_source",
            "expected_question_count",
            "expected_question_count_source",
            "expected_question_ranges",
        }
    }
    response = client.post(
        "/api/v1/admin/processing-tasks", json=request, headers=context["headers"]
    )
    assert response.status_code == 202
    assert response.json()["data"]["state"] == "pending"


@pytest.mark.parametrize("automatic", [False, True])
def test_reference_worker_never_calls_asr_or_downstream(
    context, client, monkeypatch, automatic
):
    from app.db.base import SessionLocal
    from app.module3 import worker
    from app.services.processing import tasks

    source = context["materials"][1]
    common = {
        "source_storage_key": source["storage_key"],
        "source_sha256": source["sha256"],
    }
    request = {
        **context["request"],
        "text_source": "reference",
        "reference_segments": [
            source_row(**common),
            source_row(
                **common,
                segment_id="q:1",
                text="What is the answer?",
                segment_type="question",
                question_no=1,
                search_start_ms=2000,
                search_end_ms=3000,
            ),
        ],
    }
    source_segments = request["reference_segments"]
    calls = []
    if automatic:
        request.update(reference_segments=[], reference_preparation="auto")

    def prepare(*args):
        calls.append(True)
        return {
            "segments": source_segments,
            "trusted_question_structure": {
                "question_count": 1,
                "groups": request["expected_question_ranges"],
            },
        }

    monkeypatch.setattr(worker.auto_reference, "prepare", prepare)
    response = client.post(
        "/api/v1/admin/processing-tasks", json=request, headers=context["headers"]
    )
    assert response.status_code == 202, response.text
    task_id, token = UUID(response.json()["data"]["id"]), uuid4()
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        assert task.state == "pending"
        task.state, task.lease_token = "running", token
        task.expires_at = tasks.utcnow() + timedelta(seconds=120)
        db.commit()

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Reference route must not transcribe or proceed downstream"
        )

    monkeypatch.setattr(
        worker,
        "diagnose",
        lambda profile, *a: (
            {"status": "PASS", "issues": []} if profile == "align" else forbidden()
        ),
    )
    monkeypatch.setattr(worker, "run_ocr", lambda *a: {"pages": []})
    monkeypatch.setattr(
        worker.audio,
        "decode",
        lambda *a: {"normalized_sha256": "0" * 64, "duration_ms": 3000},
    )
    monkeypatch.setattr(worker.audio, "transcribe", forbidden)
    monkeypatch.setattr(worker, "assemble", forbidden)
    from app.module3 import llm

    monkeypatch.setattr(llm, "request_json", forbidden)
    monkeypatch.setattr(worker, "persist_result", forbidden)
    monkeypatch.setattr(
        worker.audio,
        "align",
        lambda normalized, transcription, settings: {
            "segments": [
                {
                    "_src_id": f"seg:{i + 1}",
                    "text": s["text"],
                    "start_ms": round(s["start"] * 1000) + 10,
                    "end_ms": round(s["end"] * 1000) - 10,
                    "alignment_status": "aligned",
                }
                for i, s in enumerate(transcription["segments"])
            ],
            "issues": [],
        },
    )
    assert worker.process(task_id, token, context["settings"]) == 0
    assert len(calls) == int(automatic)
    with SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        assert (task.state, task.stage, task.batch_id) == (
            "awaiting_confirmation",
            "align",
            None,
        )
    base = f"/api/v1/admin/processing-tasks/{task_id}/stages/"
    assert (
        client.get(base + "transcribe", headers=context["headers"]).json()["data"][
            "missing"
        ]
        is True
    )
    aligned = client.get(base + "align", headers=context["headers"]).json()["data"][
        "result"
    ]
    assert aligned["segments"][0]["_src_id"] == "body:1"
    assert aligned["segments"][0]["text"] == "The answer is Alpha."
    assert (
        client.get(base + "reference", headers=context["headers"]).json()["data"][
            "result"
        ]["segments"][0]["text"]
        == "The answer is Alpha."
    )
