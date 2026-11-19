"""M3-EC contract/source regressions. Synthetic evidence is not content approval."""

import copy

import pytest
from pydantic import ValidationError

from app.module3.contracts import ProcessingError, fingerprint, result_hash
from app.module3.distractor_annotations import (
    check_option_candidate,
    merge_option_candidate,
    normalize_candidate,
)
from app.module3.distractor_contract import generation_state


@pytest.fixture
def coverage(context):
    payload = context["clone"]()
    q = payload["questions"][0]
    ev = {
        "evidence_segment_src_ids": ["s:1"],
        "quote": "The answer is Alpha.",
        "support_note": "Synthetic exact source",
    }
    raw = {
        "question_src_id": q["_src_id"],
        "skills": [
            {
                **ev,
                "skill_code": "S21",
                "role": "PRIMARY",
                "rationale": "Synthetic explicit fact",
            }
        ],
        "answer_evidence": [ev],
        "uncertainties": [],
        "language_items": [],
        "genre_candidate": None,
        "distractor_assessments": [
            {
                "option_letter": letter,
                "status": "NO_SUPPORTED_CANDIDATE",
                "reason": f"Synthetic source says Alpha; no mechanism for {letter}.",
                "comparison_evidence": [],
                "candidates": [],
                "unresolved_points": [],
            }
            for letter in "ABCD"
            if letter != q["correct_option"]
        ],
    }
    return payload, q, raw, ev


def supported(raw, ev, code="E4.3"):
    assessment = raw["distractor_assessments"][0]
    assessment["status"] = "SUPPORTED"
    assessment["candidates"].append(
        {
            "error_cause_code": code,
            "rationale": "若把Alpha命题换成Beta，则可能误选；合成技术例。",
            "evidence": [copy.deepcopy(ev)],
            "personal_verification_needed": "需学生复述；选择本项不足以诊断。",
        }
    )
    return assessment["candidates"][-1]


def test_schema_file_matches_active_contract():
    import json
    from pathlib import Path

    from app.module3.distractor_contract import AnnotationCandidateV7

    path = (
        Path(__file__).resolve().parents[2]
        / "config/module3/annotation-candidate-v7.schema.json"
    )
    assert (
        json.loads(path.read_text(encoding="utf-8"))
        == AnnotationCandidateV7.model_json_schema()
    )


@pytest.mark.parametrize("kind", ["comparison", "candidate"])
def test_repair_feedback_identifies_original_v7_evidence(coverage, kind):
    payload, q, raw, ev = coverage
    segment = copy.deepcopy(payload["transcript_segments"][0])
    segment.update(_src_id="s:next", segment_index=2, text="Another exact sentence.")
    payload["transcript_segments"].append(segment)
    invalid = {**ev, "evidence_segment_src_ids": ["s:1", "s:next"]}
    if kind == "comparison":
        raw["distractor_assessments"][0]["comparison_evidence"] = [invalid]
        expected_path = "distractor_assessments[0].comparison_evidence[0]"
    else:
        supported(raw, ev)["evidence"] = [invalid]
        expected_path = "distractor_assessments[0].candidates[0].evidence[0]"
    before = copy.deepcopy(raw)
    with pytest.raises(ProcessingError) as error:
        check_option_candidate(payload, q, raw)
    assert error.value.code == "ANNOTATION_QUOTE_INVALID"
    assert str(error.value).startswith(expected_path + ": ")
    assert "The answer is Alpha. Another exact sentence." in str(error.value)
    assert raw == before


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "correct", "foreign_question"]
)
def test_ec01_assessment_identity(coverage, mutation):
    payload, q, raw, _ = coverage
    if mutation == "missing":
        raw["distractor_assessments"].pop()
    elif mutation == "duplicate":
        raw["distractor_assessments"][0]["option_letter"] = raw[
            "distractor_assessments"
        ][1]["option_letter"]
    elif mutation == "correct":
        raw["distractor_assessments"][0]["option_letter"] = q["correct_option"]
    else:
        raw["question_src_id"] = "other-question"
    with pytest.raises((ValidationError, ProcessingError)):
        check_option_candidate(payload, q, raw)


def test_ec02_legacy_empty_is_not_v7(coverage):
    payload, q, raw, _ = coverage
    raw.pop("distractor_assessments")
    raw["candidate_errors"] = []
    with pytest.raises(ValidationError):
        check_option_candidate(payload, q, raw)


def test_ec03_ec04_empty_and_incomplete_are_distinct(coverage):
    payload, q, raw, _ = coverage
    assert check_option_candidate(payload, q, raw)["resolved_count"] == 3
    assert generation_state(raw) == "generated_empty"
    a = raw["distractor_assessments"][0]
    a["status"], a["unresolved_points"] = (
        "INSUFFICIENT_EVIDENCE",
        ["缺少原件先行词，待核"],
    )
    check = check_option_candidate(payload, q, raw)
    assert check["resolved_count"] == 2
    assert generation_state(raw) == "generation_incomplete"


@pytest.mark.parametrize(
    "status", ["SUPPORTED", "NO_SUPPORTED_CANDIDATE", "INSUFFICIENT_EVIDENCE"]
)
def test_ec05_state_conflicts(coverage, status):
    payload, q, raw, ev = coverage
    if status != "SUPPORTED":
        supported(raw, ev)
    raw["distractor_assessments"][0]["status"] = status
    with pytest.raises(ValidationError, match="ASSESSMENT_STATUS_CONFLICT"):
        check_option_candidate(payload, q, raw)


def test_ec06_ec07_ec12_multiple_mechanisms_and_evidence(coverage):
    payload, q, raw, ev = coverage
    for section in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        payload[section] = []
    segment = copy.deepcopy(payload["transcript_segments"][0])
    segment.update(
        _src_id="s:later",
        segment_index=3,
        text="Kim arrived Friday.",
        start_ms=2000,
        end_ms=2500,
    )
    payload["transcript_segments"].append(segment)
    error = supported(raw, ev)
    error["evidence"].append(
        {"evidence_segment_src_ids": ["s:later"], "quote": segment["text"]}
    )
    raw["distractor_assessments"][0]["candidates"].append(copy.deepcopy(error))
    supported(raw, ev, "E4.2")
    assert check_option_candidate(payload, q, raw)["error_count"] == 2
    merge_option_candidate(payload, q, raw)
    parents = [
        r
        for r in payload["error_question_relations"]
        if r["relation_kind"] == "QUESTION_ERROR_CANDIDATE"
    ]
    assert len(parents) == 2
    first = parents[0]["_src_id"]
    children = [
        r
        for r in payload["error_question_relations"]
        if r.get("owner_relation_src_id") == first
    ]
    assert [r["sort_order"] for r in children] == [1, 2]
    times = [
        (e["start_ms"], e["end_ms"])
        for e in payload["evidences"]
        if e["_src_id"] in {r["evidence_src_id"] for r in children}
    ]
    assert (2000, 2500) in times
    assert "candidate_errors" not in normalize_candidate(raw)


@pytest.mark.parametrize(
    "mutation", ["skip", "quote", "cross_passage", "question_segment"]
)
def test_ec08_bad_evidence_cannot_be_hidden(coverage, mutation):
    payload, q, raw, ev = coverage
    error = supported(raw, ev)
    evidence = error["evidence"][0]
    if mutation == "quote":
        evidence["quote"] = "invented words"
    elif mutation == "skip":
        s = copy.deepcopy(payload["transcript_segments"][0])
        s.update(_src_id="s:later", segment_index=10)
        payload["transcript_segments"].append(s)
        evidence["evidence_segment_src_ids"] += ["s:later"]
    elif mutation == "cross_passage":
        payload["transcript_segments"][0]["passage_src_id"] = "other-passage"
    else:
        payload["transcript_segments"][0]["segment_type"] = "question"
    with pytest.raises(ProcessingError):
        check_option_candidate(payload, q, raw)
    assert raw["distractor_assessments"][0]["candidates"] == [error]


def test_ec09_diff_includes_deletion_status_evidence_and_calls(coverage):
    from app.module3.candidate_diff import candidate_diff

    _, _, raw, ev = coverage
    supported(raw, ev)
    after = copy.deepcopy(raw)
    after["distractor_assessments"][0].update(
        status="NO_SUPPORTED_CANDIDATE",
        candidates=[],
        reason="具体材料比较后的删项理由",
    )
    diff = candidate_diff(raw, after, before_call=7, after_call=8)
    assert diff["before_call_id"] == 7 and diff["after_call_id"] == 8
    assert diff["semantic_deletion_review_required"]
    assert {r["kind"] for r in diff["changes"]} == {"deleted", "assessment_changed"}
    assert diff["before_hash"] != diff["after_hash"]


@pytest.mark.parametrize("code", ["E999", "对象混淆", "3.1"])
def test_ec11_only_system_dictionary_codes(coverage, code):
    payload, q, raw, ev = coverage
    supported(raw, ev, code)
    with pytest.raises((ProcessingError, ValidationError)):
        check_option_candidate(payload, q, raw)


def test_ec12_conflicts_are_blocking(coverage):
    _, _, raw, ev = coverage
    supported(raw, ev)
    second = copy.deepcopy(raw["distractor_assessments"][0]["candidates"][0])
    second["rationale"] = "A materially different mechanism"
    raw["distractor_assessments"][0]["candidates"].append(second)
    with pytest.raises(ProcessingError, match="冲突"):
        normalize_candidate(raw)


@pytest.mark.parametrize("field", ["reason", "status", "candidate", "evidence"])
def test_ec16_every_assessment_change_invalidates_hash(coverage, field):
    payload, _q, raw, ev = coverage
    payload.update(
        schema_version="m3.v3",
        rules_manifest={"error_rule_version": "m3.option-errors.v2"},
    )
    payload["distractor_assessments"] = raw["distractor_assessments"]
    identity = result_hash(payload)
    a = raw["distractor_assessments"][0]
    if field == "reason":
        a["reason"] += "changed"
    elif field == "status":
        a.update(status="INSUFFICIENT_EVIDENCE", unresolved_points=["gap"])
    elif field == "candidate":
        supported(raw, ev)
    else:
        a["comparison_evidence"].append(ev)
    assert result_hash(payload) != identity
    assert fingerprint(raw) != fingerprint({})
