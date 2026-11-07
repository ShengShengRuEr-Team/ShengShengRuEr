"""Stage-7/8 negative gates and the boundary before business persistence."""

import copy
from uuid import UUID

import pytest


def raw_candidate(context):
    from app.services.processing.validation import load_dictionary

    skill = next(
        r["skill_code"]
        for t in load_dictionary()["tables"]
        if t["name"] == "skill"
        for r in t["rows"]
        if r.get("usage_scope") == "题目标注" and r["skill_level"] == 3
    )
    ev = {"evidence_segment_src_ids": ["s:1"], "quote": "The answer is Alpha."}
    return {
        "question_src_id": "q:1",
        "skills": [
            {
                **ev,
                "skill_code": skill,
                "role": "PRIMARY",
                "rationale": "正文直接指出Alpha，与正确选项一致。",
            }
        ],
        "answer_evidence": [{**ev, "support_note": "正文明确指出Alpha，支持答案A。"}],
        "candidate_errors": [],
        "language_items": [],
        "genre_candidate": None,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "dictionary",
        "diagnostic",
        "cross_passage",
        "question_evidence",
        "duplicate",
        "quote",
        "answer_override",
        "time",
        "support",
        "primary",
    ],
)
def test_annotation_rejects_bad_candidate(context, mutation):
    from app.module3.annotation_checks import check_candidate

    raw = raw_candidate(context)
    if mutation == "dictionary":
        raw["skills"][0]["skill_code"] = "S_FAKE"
    if mutation == "diagnostic":
        raw["skills"][0]["skill_code"] = "S07"
    if mutation == "cross_passage":
        context["payload"]["transcript_segments"][0]["passage_src_id"] = "other"
    if mutation == "question_evidence":
        raw["answer_evidence"][0]["evidence_segment_src_ids"] = ["s:2"]
    if mutation == "duplicate":
        raw["skills"][0]["evidence_segment_src_ids"] *= 2
    if mutation == "quote":
        raw["answer_evidence"][0]["quote"] = "Fabricated text"
    if mutation == "answer_override":
        raw["correct_option"] = "B"
    if mutation == "time":
        raw["answer_evidence"][0]["start_ms"] = 2
    if mutation == "support":
        raw["answer_evidence"][0].pop("support_note")
    if mutation == "primary":
        raw["skills"][0]["role"] = "AUXILIARY"
    with pytest.raises(ValueError):
        check_candidate(context["payload"], context["payload"]["questions"][0], raw)


def test_candidate_times_are_computed(context):
    from app.module3.annotation_checks import check_candidate
    from app.module3.annotations import merge_candidate

    raw = raw_candidate(context)
    p = copy.deepcopy(context["payload"])
    for k in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        p[k] = []
    assert check_candidate(p, p["questions"][0], raw)["status"] == "PASS"
    merge_candidate(p, p["questions"][0], raw)
    assert all((e["start_ms"], e["end_ms"]) == (0, 1800) for e in p["evidences"])


@pytest.mark.parametrize("stop", ["assemble", "annotate_sample", "annotate"])
def test_draft_stop_never_creates_batch(context, stop):
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.db.base import SessionLocal
    from app.db.models_listening import ImportBatch
    from app.module3.worker import stop_draft
    from app.services.processing import tasks

    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(context["task_id"]), lock=True)
        task.state, task.lease_token = "running", UUID(int=7)
        task.expires_at = tasks.utcnow() + timedelta(seconds=120)
        count = db.scalar(select(func.count()).select_from(ImportBatch))
        db.commit()
    stage = "assemble" if stop == "assemble" else "annotate"
    assert (
        stop_draft(
            UUID(context["task_id"]),
            UUID(int=7),
            stage,
            context["payload"],
            context["settings"],
        )
        == 0
    )
    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(context["task_id"]))
        assert (task.state, task.stage, task.batch_id) == (
            "awaiting_confirmation",
            stage,
            None,
        )
        assert db.scalar(select(func.count()).select_from(ImportBatch)) == count


def test_conflicting_source_answer_is_blocked():
    from app.module3.source_assembly import finalize_answers

    record = {
        1: {
            "explanation_blocks": [
                {"original_text": "选项A为正确答案；B为正确答案", "confidence": 0.99}
            ]
        }
    }
    with pytest.raises(ValueError):
        finalize_answers(record)


def test_whole_annotation_requires_sample_review(context):
    from app.schemas_processing import TaskRequest

    with pytest.raises(ValueError):
        TaskRequest.model_validate({**context["request"], "stop_after": "annotate"})


def test_answer_exclusion_does_not_override_explicit_answer():
    from app.module3.source_assembly import finalize_answers

    records = {
        1: {
            "explanation_blocks": [
                {
                    "original_text": "由此可知，选项C为正确答案。故排除选项B。",
                    "confidence": 0.99,
                }
            ]
        }
    }
    assert finalize_answers(records)[1]["correct_option"] == "C"


def test_missing_answer_never_uses_an_excluded_letter():
    from app.module3.source_assembly import finalize_answers

    records = {
        1: {
            "explanation_blocks": [
                {"original_text": "选项B与内容不符，故排除选项B。", "confidence": 0.99}
            ]
        }
    }
    with pytest.raises(ValueError):
        finalize_answers(records)


def test_paper_options_stop_before_keys_and_instructions():
    from app.module3.source_assembly import paper_answer_key, paper_options

    pages = [
        {
            "page": 1,
            "material_id": 1,
            "source_kind": "paper_text",
            "text": "Part II Listening Comprehension\n"
            "1. A) Alpha. C) Gamma.\nB) Beta. D) Delta.\n"
            "Section B\nDirections: choose A), B), C), D).\n"
            "Part III Reading Comprehension",
        },
        {
            "page": 2,
            "material_id": 1,
            "source_kind": "paper_text",
            "text": "KEYS\nPart II Listening Comprehension\n1\nA\n"
            "Part III Reading Comprehension",
        },
    ]
    assert len(paper_options(pages)) == 1
    assert paper_answer_key(pages)[1]["correct_option"] == "A"


def test_option_continuation_is_not_silently_dropped():
    from app.module3.source_assembly import paper_options

    pages = [
        {
            "page": 1,
            "material_id": 1,
            "source_kind": "paper_text",
            "text": "Part II Listening Comprehension\n1. A) First line\n"
            "continued on the next line",
        }
    ]
    with pytest.raises(ValueError):
        paper_options(pages)


@pytest.mark.parametrize("fault", ["rejected", "wrong_hash", "missing_item_reason"])
def test_sample_semantic_gate_blocks_before_new_call(context, monkeypatch, fault):
    from types import SimpleNamespace

    from app.db.base import SessionLocal
    from app.module3 import annotation_checks
    from app.module3.contracts import ProcessingError
    from app.services.processing import tasks

    with SessionLocal() as db:
        source = tasks.get_task(db, UUID(context["task_id"]))
        source.state, source.stage = "awaiting_confirmation", "annotate"
        source.request = {**source.request, "stop_after": "annotate_sample"}
        draft = tasks.store_draft(db, source, context["payload"], view="final")
        review = {
            "result_hash": draft.result_hash,
            "decision": "approved",
            "reviewer": "synthetic gate test",
            "reviewed_at": tasks.utcnow().isoformat(),
            "items": [
                {
                    "question_src_id": "q:1",
                    "decision": "approved",
                    "support_reason": "Alpha stated directly",
                    "skill_reason": "synthetic skill applicability check",
                }
            ],
        }
        method, code = source.method, source.exam_paper_code
        db.commit()
    if fault == "rejected":
        review["decision"] = "changes_required"
    elif fault == "wrong_hash":
        review["result_hash"] = "f" * 64
    else:
        review["items"][0].pop("skill_reason")
    task = SimpleNamespace(
        request={
            "reuse_annotation_task_id": context["task_id"],
            "sample_review": review,
        },
        method=method,
        exam_paper_code=code,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unapproved sample must stop before new LLM calls/checkpoints")

    monkeypatch.setattr(annotation_checks, "request_json", forbidden)
    with pytest.raises(ProcessingError) as error:
        annotation_checks.annotate_questions(
            task, None, context["payload"], context["settings"], forbidden
        )
    assert error.value.code == "ANNOTATION_SAMPLE_REVIEW_REQUIRED"


@pytest.mark.parametrize("failure_count", [1, 3])
def test_contract_retry_is_bounded_and_retains_rejected_output(
    context, monkeypatch, failure_count
):
    from types import SimpleNamespace

    from app.module3 import annotation_checks
    from app.module3.contracts import ProcessingError

    payload = copy.deepcopy(context["payload"])
    for key in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        payload[key] = []
    original = copy.deepcopy(payload)
    inputs, artifacts = [], []

    def request(*args):
        inputs.append(copy.deepcopy(args[4]))
        candidate = raw_candidate(context)
        if len(inputs) <= failure_count:
            candidate["answer_evidence"][0]["quote"] = "Fabricated quote"
        return candidate, {"attempt_id": len(inputs), "response_model": "synthetic"}

    def checkpoint(*args):
        artifacts.append((args[2], copy.deepcopy(args[3])))

    monkeypatch.setattr(annotation_checks, "request_json", request)
    task = SimpleNamespace(
        id=UUID(context["task_id"]), request={"stop_after": "annotate_sample"}
    )
    if failure_count == 3:
        with pytest.raises(ProcessingError) as error:
            annotation_checks.annotate_questions(
                task, None, payload, context["settings"], checkpoint
            )
        assert error.value.code == "ANNOTATION_QUOTE_INVALID"
        assert payload == original
    else:
        annotation_checks.annotate_questions(
            task, None, payload, context["settings"], checkpoint
        )
        assert sum(stage == "annotate" for stage, _ in artifacts) == 1
    assert len(inputs) == min(failure_count + 1, 3)
    assert "validation_feedback" not in inputs[0]
    assert inputs[1]["validation_feedback"]["issue_code"] == "ANNOTATION_QUOTE_INVALID"
    feedback = inputs[1]["validation_feedback"]
    assert "answer_evidence[0]" in feedback["message"]
    assert (
        feedback["previous_candidate"]["answer_evidence"][0]["quote"]
        == "Fabricated quote"
    )
    assert "OPTIONAL" in feedback["optional_candidate_policy"]
    assert (
        sum(stage == "annotation_rejected" for stage, _ in artifacts) == failure_count
    )


def test_disconnected_optional_error_is_identified_and_never_auto_repaired(context):
    from app.module3.annotation_checks import check_candidate
    from app.module3.contracts import ProcessingError

    payload = context["clone"]()
    payload["transcript_segments"].extend(
        [
            {
                **payload["transcript_segments"][0],
                "_src_id": "body:2",
                "segment_index": 2,
            },
            {
                **payload["transcript_segments"][0],
                "_src_id": "body:3",
                "segment_index": 3,
            },
        ]
    )
    candidate = raw_candidate(context)
    candidate["candidate_errors"] = [
        {
            "error_cause_code": "E4.3",
            "rationale": "Synthetic disconnected attribution",
            "option_letter": "B",
            "evidence_segment_src_ids": ["s:1", "body:3"],
            "quote": "The answer is Alpha. The answer is Alpha.",
        }
    ]
    before = copy.deepcopy(candidate)
    with pytest.raises(ProcessingError, match=r"candidate_errors\[0\]") as error:
        check_candidate(payload, payload["questions"][0], candidate)
    assert error.value.code == "ANNOTATION_EVIDENCE_INVALID"
    assert candidate == before


@pytest.mark.parametrize(
    "mode",
    [
        "approved",
        "repair",
        "wrong_hash",
        "missing_reason",
        "import_approved",
        "import_repair",
    ],
)
def test_full_review_reuses_only_approved_candidates(context, monkeypatch, mode):
    from datetime import timedelta
    from types import SimpleNamespace

    from app.db.base import SessionLocal
    from app.module3 import annotation_checks
    from app.module3.contracts import ProcessingError
    from app.services.processing import tasks

    payload = copy.deepcopy(context["payload"])
    for key in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        payload[key] = []
    with SessionLocal() as db:
        source = tasks.get_task(db, UUID(context["task_id"]))
        source.state, source.lease_token = "running", UUID(int=91)
        source.expires_at = tasks.utcnow() + timedelta(seconds=120)
        source.request = {**source.request, "stop_after": "annotate"}
        tasks.save_artifact(
            db,
            source.id,
            source.lease_token,
            "annotate",
            {
                "question_src_id": "q:1",
                "candidate": raw_candidate(context),
                "call": {"attempt_id": 1, "response_model": "synthetic"},
            },
            context["settings"],
        )
        draft = tasks.store_draft(db, source, payload, view="final")
        source.state, source.stage = "awaiting_confirmation", "annotate"
        source.lease_token = None
        item = {
            "question_src_id": "q:1",
            "decision": "approved",
            "support_reason": "synthetic source support",
            "skill_reason": "synthetic applicability",
        }
        review = {
            "result_hash": draft.result_hash,
            "decision": "approved",
            "reviewer": "synthetic gate test",
            "reviewed_at": tasks.utcnow().isoformat(),
            "items": [item],
        }
        method, code = source.method, source.exam_paper_code
        db.commit()
    if mode in {"repair", "import_repair"}:
        review["decision"] = item["decision"] = "changes_required"
        item["repair_feedback"] = "Repair the specified evidence context from source."
    elif mode == "wrong_hash":
        review["result_hash"] = "0" * 64
    elif mode == "missing_reason":
        item.pop("support_reason")
    inputs, stages = [], []

    def request(*args):
        inputs.append(copy.deepcopy(args[4]))
        return raw_candidate(context), {"attempt_id": 2, "response_model": "synthetic"}

    monkeypatch.setattr(annotation_checks, "request_json", request)
    monkeypatch.setattr(annotation_checks, "sample_candidates", lambda *args: {})
    task = SimpleNamespace(
        id=UUID(int=92),
        method=method,
        exam_paper_code=code,
        request={
            "stop_after": "completed" if mode.startswith("import_") else "annotate",
            "reuse_full_annotation_task_id": context["task_id"],
            "annotation_review": review,
        },
    )

    def checkpoint(*args):
        stages.append(args[2])

    if mode in {"wrong_hash", "missing_reason", "import_repair"}:
        with pytest.raises(ProcessingError) as error:
            annotation_checks.annotate_questions(
                task, None, payload, context["settings"], checkpoint
            )
        assert error.value.code == (
            "ANNOTATION_IMPORT_REVIEW_REQUIRED"
            if mode == "import_repair"
            else "ANNOTATION_REPAIR_REVIEW_INVALID"
        )
        assert not inputs and not stages
    else:
        annotation_checks.annotate_questions(
            task, None, payload, context["settings"], checkpoint
        )
        assert len(inputs) == (1 if mode == "repair" else 0)
        assert "annotate" in stages
        if inputs:
            assert (
                inputs[0]["validation_feedback"]["issue_code"]
                == "ANNOTATION_SEMANTIC_REVIEW"
            )
