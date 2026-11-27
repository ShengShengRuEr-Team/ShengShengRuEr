"""Synthetic metric contracts; no external inference or human review claims."""

from copy import deepcopy

import pytest


@pytest.fixture
def sample():
    from app.module3.annotation_identity import question_input_hash, rules_manifest

    source = {
        "audio": {"file_hash": "a" * 64},
        "rules_manifest": rules_manifest(),
        "passages": [{"_src_id": "p1", "topic": "Synthetic source"}],
        "questions": [
            {
                "_src_id": f"q{i}",
                "passage_src_id": "p1",
                "question_index": i,
                "correct_option": "A",
                "question_text": "Synthetic question",
                "options": {"A": "Alpha", "B": "Beta", "C": "Gamma", "D": "Delta"},
            }
            for i in range(1, 26)
        ],
        "presentations": [],
        "transcript_segments": [
            {
                "_src_id": "s1",
                "passage_src_id": "p1",
                "segment_type": "body",
                "segment_index": 1,
                "text": "The answer is Alpha.",
                "alignment_status": "aligned",
                "start_ms": 100,
                "end_ms": 1000,
            }
        ],
    }
    evidence = {
        "evidence_segment_src_ids": ["s1"],
        "quote": "The answer is Alpha.",
        "support_note": "Synthetic evidence",
    }
    records = {provider: {} for provider in ["deepseek", "bailian"]}
    for question in source["questions"]:
        raw = {
            "question_src_id": question["_src_id"],
            "skills": [
                {
                    **evidence,
                    "skill_code": "S08",
                    "role": "PRIMARY",
                    "rationale": "Synthetic skill",
                }
            ],
            "answer_evidence": [deepcopy(evidence)],
            "distractor_assessments": [
                {
                    "option_letter": letter,
                    "status": "NO_SUPPORTED_CANDIDATE",
                    "reason": "Synthetic comparison",
                    "comparison_evidence": [deepcopy(evidence)],
                    "candidates": [],
                    "unresolved_points": [],
                }
                for letter in "BCD"
            ],
            "uncertainties": [],
            "language_items": [],
            "genre_candidate": None,
        }
        for provider in records:
            records[provider][question["_src_id"]] = {
                "origin_type": "AI",
                "execution_state": "executed",
                "complete_record": True,
                "question_input_hash": question_input_hash(source, question),
                "dictionary_sha256": source["rules_manifest"]["dictionary_sha256"],
                "raw": deepcopy(raw),
            }
    return source, records


def report(sample):
    from app.module3.comparison import compare

    return compare(*sample)


def raw(sample, provider="deepseek", qid="q1"):
    return sample[1][provider][qid]["raw"]


def supported(assessment, code="E1.1"):
    assessment.update(
        status="SUPPORTED",
        candidates=[
            {
                "error_cause_code": code,
                "rationale": "Synthetic conditional mechanism",
                "evidence": [
                    {
                        "evidence_segment_src_ids": ["s1"],
                        "quote": "The answer is Alpha.",
                        "support_note": "Synthetic support",
                    }
                ],
                "personal_verification_needed": "Synthetic later verification",
            }
        ],
    )


def test_valid_empty_sets_and_zero_nonempty_denominator(sample):
    result = report(sample)
    assert result["metrics"]["primary"]["numerator"] == 25
    assert result["metrics"]["skills"]["numerator"] == 25
    assert result["metrics"]["errors"]["numerator"] == 75


@pytest.mark.parametrize("prior_audit_failure", [False, True])
def test_selected_executor_never_submits_out_of_scope_questions(
    sample, tmp_path, monkeypatch, prior_audit_failure
):
    import json
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace
    from uuid import uuid4

    from scripts import compare_library_models as cli

    source, records = sample
    workflow_id, revision_id = uuid4(), uuid4()
    context = {
        "operator_user_id": 1,
        "workflow_id": str(workflow_id),
        "source_revision_id": str(revision_id),
        "source_dependency_hash": "a" * 64,
        "expected_row_version": 1,
        "expected_content_hash": "b" * 64,
        "rules_manifest": cli.rules_manifest(),
        "edit_head_before": None,
    }
    entity = SimpleNamespace(
        id=uuid4(),
        state="succeeded",
        exam_paper_id=1,
        current_revision_id=revision_id,
        library_row_version=1,
    )
    submitted = []

    def generate(db, workflow, payload, user, key, settings):
        submitted.append((payload.provider, payload.question_src_ids))
        return entity

    monkeypatch.setattr(
        cli,
        "frozen_context",
        lambda *a: (source, {"dependency_hash": "a" * 64}, context),
    )
    monkeypatch.setattr(cli.providers, "freeze", lambda provider, settings: {})
    monkeypatch.setattr(cli, "budget_snapshot", lambda *a: {"limit_reached": False})
    monkeypatch.setattr(
        cli,
        "SessionLocal",
        lambda: nullcontext(
            SimpleNamespace(get=lambda *a: entity, commit=lambda: None)
        ),
    )
    monkeypatch.setattr(cli.generation, "generate", generate)
    monkeypatch.setattr(cli, "head_identity", lambda *a: None)
    if prior_audit_failure:
        (tmp_path / "records.json").write_text("{}", encoding="utf-8")
        recovered = {
            "deepseek": {
                "q1": {
                    **deepcopy(records["deepseek"]["q1"]),
                    "reason": "BUDGET_AUDIT_BLOCKED",
                }
            },
            "bailian": {},
        }
        monkeypatch.setattr(cli, "recover_records", lambda *a: recovered)
    monkeypatch.setattr(
        cli,
        "observations",
        lambda command, src, question, settings: deepcopy(
            records["deepseek"][question["_src_id"]]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare",
            "--workflow",
            str(workflow_id),
            "--admin-username",
            "synthetic",
            "--output",
            str(tmp_path),
            "--listening-waiver-reference",
            "synthetic",
            "--question-indices",
            "1",
            "20",
            "--execute",
            *(
                ["--resume-executor-fix-reference", "Synthetic audit recovery"]
                if prior_audit_failure
                else []
            ),
        ],
    )
    assert cli.main() == 0
    assert submitted == [
        (provider, [qid])
        for provider in ["deepseek", "bailian"]
        for qid in ["q1", "q20"]
        if not (prior_audit_failure and provider == "deepseek" and qid == "q1")
    ]
    result = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    assert result["metadata"]["selected_question_indices"] == [1, 20]
    assert result["metrics"]["errors"]["denominator"] == 75
    assert result["metrics"]["errors"]["numerator"] == 6
    assert result["coverage"]["deepseek"]["errors"]["not_executed"] == 69
    assert result["metrics"]["nonempty_errors"] == {
        "numerator": 0,
        "denominator": 0,
        "ratio": None,
        "display": "不适用",
    }
    assert len(result["questions"]) == 25 and len(result["options"]) == 75


def test_order_independent_full_skill_and_error_sets(sample):
    for provider in ["deepseek", "bailian"]:
        candidate = raw(sample, provider)
        candidate["skills"].append(
            {**candidate["skills"][0], "skill_code": "S09", "role": "AUXILIARY"}
        )
        supported(candidate["distractor_assessments"][0])
        candidate["distractor_assessments"][0]["candidates"].append(
            {
                **deepcopy(candidate["distractor_assessments"][0]["candidates"][0]),
                "error_cause_code": "E1.2",
            }
        )
    raw(sample, "bailian")["skills"].reverse()
    raw(sample, "bailian")["distractor_assessments"][0]["candidates"].reverse()
    result = report(sample)
    assert result["metrics"]["skills"]["numerator"] == 25
    assert result["metrics"]["errors"]["numerator"] == 75
    assert result["metrics"]["nonempty_errors"]["numerator"] == 1


def test_missing_model_question_does_not_shrink_fixed_denominators(sample):
    del sample[1]["bailian"]["q1"]
    result = report(sample)
    assert result["metrics"]["primary"]["numerator"] == 24
    assert result["metrics"]["primary"]["denominator"] == 25
    assert result["metrics"]["errors"]["numerator"] == 72
    assert result["metrics"]["errors"]["denominator"] == 75
    assert result["coverage"]["bailian"]["errors"]["not_executed"] == 3


def test_one_bad_option_keeps_other_units_valid(sample):
    raw(sample)["distractor_assessments"][0]["comparison_evidence"][0]["quote"] = (
        "Not present in source"
    )
    result = report(sample)
    assert result["metrics"]["primary"]["numerator"] == 25
    assert result["metrics"]["skills"]["numerator"] == 25
    assert result["metrics"]["errors"]["numerator"] == 74


def test_bad_auxiliary_does_not_poison_valid_primary(sample):
    candidate = raw(sample)
    candidate["skills"].append(
        {
            **candidate["skills"][0],
            "skill_code": "S09",
            "role": "AUXILIARY",
            "quote": "Not in source",
        }
    )
    result = report(sample)
    assert result["metrics"]["primary"]["numerator"] == 25
    assert result["metrics"]["skills"]["numerator"] == 24
    assert result["metrics"]["errors"]["numerator"] == 75


@pytest.mark.parametrize("kind", ["primary", "error", "assessment"])
def test_illegal_duplicates_are_not_hidden_by_set_conversion(sample, kind):
    candidate = raw(sample)
    if kind == "primary":
        candidate["skills"].append(deepcopy(candidate["skills"][0]))
    elif kind == "error":
        assessment = candidate["distractor_assessments"][0]
        supported(assessment)
        assessment["candidates"].append(deepcopy(assessment["candidates"][0]))
    else:
        candidate["distractor_assessments"].append(
            deepcopy(candidate["distractor_assessments"][0])
        )
    result = report(sample)
    assert result["metrics"]["primary" if kind == "primary" else "errors"][
        "numerator"
    ] == (24 if kind == "primary" else 74)


def test_insufficient_evidence_is_not_a_valid_empty(sample):
    raw(sample)["distractor_assessments"][0].update(
        status="INSUFFICIENT_EVIDENCE",
        unresolved_points=["Synthetic evidence boundary"],
    )
    result = report(sample)
    assert result["metrics"]["errors"]["numerator"] == 74
    assert result["options"][0]["models"]["deepseek"]["state"] == "insufficient"


def test_one_valid_nonempty_side_keeps_the_other_failed_side_in_nonempty_denominator(
    sample,
):
    supported(raw(sample)["distractor_assessments"][0])
    sample[1]["bailian"]["q1"]["complete_record"] = False
    result = report(sample)
    assert result["metrics"]["nonempty_errors"]["denominator"] == 1
    assert result["metrics"]["nonempty_errors"]["numerator"] == 0


@pytest.mark.parametrize(
    "fault", ["identity", "json", "manual", "mixed", "input", "dictionary", "record"]
)
def test_untrusted_identity_or_provenance_invalidates_the_question(sample, fault):
    record = sample[1]["deepseek"]["q1"]
    if fault == "identity":
        record["raw"]["question_src_id"] = "other"
    elif fault == "json":
        record["raw"] = None
    elif fault in {"manual", "mixed"}:
        record["origin_type"] = fault.upper()
    elif fault == "input":
        record["question_input_hash"] = "0" * 64
    elif fault == "dictionary":
        record["dictionary_sha256"] = "0" * 64
    else:
        record["complete_record"] = False
    result = report(sample)
    assert result["metrics"]["primary"]["numerator"] == 24
    assert result["metrics"]["skills"]["numerator"] == 24
    assert result["metrics"]["errors"]["numerator"] == 72


def test_answer_evidence_failure_does_not_change_independent_label_units(sample):
    raw(sample)["answer_evidence"] = None
    result = report(sample)
    assert result["metrics"]["primary"]["numerator"] == 25
    assert result["metrics"]["skills"]["numerator"] == 25
    assert result["metrics"]["errors"]["numerator"] == 75


def test_missing_all_results_still_lists_every_unit(sample):
    source, _records = sample
    from app.module3.comparison import compare, render_markdown

    result = compare(
        source,
        {},
        metadata={
            "listening_review": {
                "state": "waived_by_user",
                "actual_listening_performed": False,
            }
        },
    )
    assert result["metrics"]["primary"]["display"].startswith("0/25")
    assert result["metrics"]["errors"]["display"].startswith("0/75")
    assert result["coverage"]["deepseek"]["errors"]["not_executed"] == 75
    markdown = render_markdown(result)
    assert (
        "waived_by_user" in markdown
        and "25 / D" in markdown
        and "相同率不是准确率" in markdown
    )


def test_comparison_does_not_modify_sources_or_raw_candidates(sample):
    before = deepcopy(sample)
    report(sample)
    assert sample == before


def test_wrong_sample_count_is_rejected(sample):
    from app.module3.comparison import compare
    from app.module3.contracts import ProcessingError

    sample[0]["questions"].pop()
    with pytest.raises(ProcessingError, match="25"):
        compare(*sample)
