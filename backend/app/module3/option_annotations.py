"""Option-scoped V2 candidates. Historical V1 candidates keep their old decoder."""

from copy import deepcopy
from typing import Literal

from pydantic import Field

from app.module3.annotations import (
    SYSTEM_PROMPT,
    AnnotationCandidate,
    EvidenceCandidate,
    SkillCandidate,
    annotation_input,
    merge_candidate,
)
from app.module3.contracts import ProcessingError, fingerprint
from app.schemas_processing import NonEmpty, StrictModel

RULE_VERSION = "m3.option-errors.v1"
PROMPT_VERSION = "m3.annotations.v6"
SYSTEM_PROMPT_V2 = """Annotate the supplied listening question using its SOURCE correct
answer and BASE options. Never modify source text, answers or audio times.
Return exactly {question_src_id,skills:[{skill_code,role,rationale,
evidence_segment_src_ids,quote}],answer_evidence:[{evidence_segment_src_ids,quote,
support_note}],candidate_errors:[{error_cause_code,option_letter,rationale,
evidence:[{evidence_segment_src_ids,quote,support_note}]}],language_items:[],
genre_candidate:null}. Every error MUST identify a BASE wrong option in
allowed_error_options; never annotate the correct option. One wrong option may
have zero or multiple distinct error codes. candidate_errors:[] is fully valid:
do not invent a mechanism or evidence to fill a quota. Each error needs at least
one evidence group, each group consecutive ordered aligned BODY sentence IDs in
the SAME passage, with an exact source quote and Chinese support_note. Separate
nonconsecutive groups. Explain this distractor's mechanism, not a student diagnosis.
Use enabled level-3 dictionary codes, PRIMARY skills and separate answer evidence.
Never return database IDs, new source text, times or extra fields.
""" + SYSTEM_PROMPT[SYSTEM_PROMPT.index("PRIMARY selection") :]


class OptionErrorCandidate(StrictModel):
    error_cause_code: NonEmpty
    option_letter: Literal["A", "B", "C", "D"]
    rationale: NonEmpty
    evidence: list[EvidenceCandidate] = Field(min_length=1)


class OptionAnnotationCandidate(StrictModel):
    question_src_id: NonEmpty
    skills: list[SkillCandidate] = Field(min_length=1)
    answer_evidence: list[EvidenceCandidate] = Field(min_length=1)
    candidate_errors: list[OptionErrorCandidate]
    language_items: list = Field(default_factory=list, max_length=0)
    genre_candidate: None = None


def normalize_candidate(raw):
    candidate = OptionAnnotationCandidate.model_validate(raw)
    merged = {}
    for error in candidate.candidate_errors:
        key = (error.option_letter, error.error_cause_code)
        item = error.model_dump()
        if key in merged and merged[key]["rationale"] != error.rationale:
            raise ProcessingError("ANNOTATION_CONFLICT", "同题同选项同编码的理由冲突")
        target = merged.setdefault(key, {**item, "evidence": []})
        by_identity = {
            fingerprint({k: v for k, v in e.items() if k != "support_note"}): e
            for e in target["evidence"]
        }
        for evidence in item["evidence"]:
            identity = fingerprint(
                {k: v for k, v in evidence.items() if k != "support_note"}
            )
            previous = by_identity.get(identity)
            if previous and previous != evidence:
                raise ProcessingError("ANNOTATION_CONFLICT", "同一证据的支持依据冲突")
            if previous is None:
                target["evidence"].append(evidence)
                by_identity[identity] = evidence
    return {**candidate.model_dump(), "candidate_errors": list(merged.values())}


def option_input(payload, question):
    result = annotation_input(payload, question)
    result["allowed_error_options"] = [
        letter for letter in "ABCD" if letter != question["correct_option"]
    ]
    return result


def check_option_candidate(payload, question, raw):
    from app.module3.annotation_checks import check_candidate

    value = normalize_candidate(raw)
    flattened = []
    for error in value["candidate_errors"]:
        if error["option_letter"] == question["correct_option"]:
            raise ProcessingError("OPTION_ERROR_INVALID", "正确基准选项不能绑定错因")
        for evidence in error["evidence"]:
            if not evidence["support_note"]:
                raise ProcessingError(
                    "ANNOTATION_SUPPORT_MISSING", "每组错因证据须有支持依据"
                )
            flattened.append(
                {**{k: v for k, v in error.items() if k != "evidence"}, **evidence}
            )
    # Reuse dictionary, PRIMARY, same-passage, consecutive, aligned-time and quote
    # checks without ever accepting a V1 candidate as a new-generation receipt.
    check = check_candidate(payload, question, {**value, "candidate_errors": flattened})
    return {
        **check,
        "rule_version": RULE_VERSION,
        "error_count": len(value["candidate_errors"]),
    }


def merge_option_candidate(payload, question, raw):
    check_option_candidate(payload, question, raw)
    value = normalize_candidate(raw)
    result = deepcopy(payload)
    legacy = AnnotationCandidate.model_validate({**value, "candidate_errors": []})
    merge_candidate(result, question, legacy.model_dump())
    segments = {s["_src_id"]: s for s in result["transcript_segments"]}
    for error in value["candidate_errors"]:
        owner = (
            "qc:"
            + fingerprint(
                [question["_src_id"], error["option_letter"], error["error_cause_code"]]
            )[:48]
        )
        result["error_question_relations"].append(
            {
                "_src_id": owner,
                "relation_code": owner,
                "relation_kind": "QUESTION_ERROR_CANDIDATE",
                "revision_no": 1,
                "is_current": True,
                "collector": "module3",
                "question_src_id": question["_src_id"],
                "option_letter": error["option_letter"],
                "error_cause_code": error["error_cause_code"],
                "rule_version": RULE_VERSION,
                "business_eligible": True,
                "attributes_json": {
                    "trigger_mechanism": error["rationale"],
                    "annotation_source": PROMPT_VERSION,
                },
            }
        )
        for index, evidence in enumerate(error["evidence"], 1):
            refs = evidence["evidence_segment_src_ids"]
            eid = "ev:" + fingerprint([owner, refs, evidence["quote"]])[:48]
            full = " ".join(segments[r]["text"] for r in refs)
            start = full.index(evidence["quote"])
            result["evidences"].append(
                {
                    "_src_id": eid,
                    "passage_src_id": question["passage_src_id"],
                    "segment_src_ids": refs,
                    "char_ranges": None
                    if full == evidence["quote"]
                    else [[start, start + len(evidence["quote"])]],
                    "evidence_text": evidence["quote"],
                    "evidence_type": "正文",
                    "start_ms": segments[refs[0]]["start_ms"],
                    "end_ms": segments[refs[-1]]["end_ms"],
                    "source": PROMPT_VERSION,
                    "collector": "module3",
                }
            )
            child = "ce:" + fingerprint([owner, eid])[:48]
            result["error_question_relations"].append(
                {
                    "_src_id": child,
                    "relation_code": child,
                    "relation_kind": "CANDIDATE_EVIDENCE",
                    "revision_no": 1,
                    "is_current": True,
                    "collector": "module3",
                    "rule_version": RULE_VERSION,
                    "business_eligible": True,
                    "owner_relation_src_id": owner,
                    "evidence_src_id": eid,
                    "sort_order": index,
                    "attributes_json": {"support_note": evidence["support_note"]},
                }
            )
    payload.clear()
    payload.update(result)


def validate_option_relations(payload):
    questions = {q["_src_id"]: q for q in payload["questions"]}
    rows = payload.get("error_question_relations", [])
    owners = {
        r["_src_id"]: r
        for r in rows
        if r["relation_kind"] == "QUESTION_ERROR_CANDIDATE"
    }
    seen = set()
    for owner in owners.values():
        question = questions.get(owner.get("question_src_id"))
        if (
            not question
            or owner.get("option_letter") not in ("A", "B", "C", "D")
            or owner["option_letter"] == question["correct_option"]
            or owner.get("rule_version") != RULE_VERSION
            or not owner.get("business_eligible")
        ):
            raise ProcessingError(
                "OPTION_ERROR_INVALID", "新错因必须绑定当前规则下的错误基准选项"
            )
        identity = (
            question["_src_id"],
            owner["option_letter"],
            owner["error_cause_code"],
        )
        if identity in seen:
            raise ProcessingError("ANNOTATION_CONFLICT", "同题同选项同编码重复")
        seen.add(identity)
        children = [
            r for r in rows if r.get("owner_relation_src_id") == owner["_src_id"]
        ]
        if not children:
            raise ProcessingError("ANNOTATION_EVIDENCE_INVALID", "每条错因必须保留证据")
    for row in rows:
        if (
            row.get("rule_version") != RULE_VERSION
            or not row.get("business_eligible")
            or (
                row["relation_kind"] == "CANDIDATE_EVIDENCE"
                and row.get("owner_relation_src_id") not in owners
            )
        ):
            raise ProcessingError(
                "ANNOTATION_REFERENCE_INVALID", "新旧规则或关系owner不匹配"
            )


def invert_option_mapping(mapping):
    if set(mapping) != set("ABCD") or set(mapping.values()) != set("ABCD"):
        raise ProcessingError("OPTION_MAPPING_INVALID", "展示选项与基准选项须为A—D双射")
    return {base: display for display, base in mapping.items()}
