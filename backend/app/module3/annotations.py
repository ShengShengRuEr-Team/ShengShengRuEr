"""Strict candidate schemas and deterministic conversion to evidence relations."""

from typing import Literal

from pydantic import Field

from app.module3.contracts import ProcessingError
from app.schemas_processing import NonEmpty, StrictModel
from app.services.processing.validation import load_dictionary


class EvidenceCandidate(StrictModel):
    evidence_segment_src_ids: list[NonEmpty] = Field(min_length=1)
    quote: NonEmpty


class SkillCandidate(EvidenceCandidate):
    skill_code: NonEmpty
    role: Literal["PRIMARY", "SECONDARY"]
    rationale: NonEmpty


class ErrorCandidate(EvidenceCandidate):
    error_cause_code: NonEmpty
    rationale: NonEmpty
    option_letter: Literal["A", "B", "C", "D"] | None = None


class AnnotationCandidate(StrictModel):
    question_src_id: NonEmpty
    skills: list[SkillCandidate] = Field(min_length=1)
    answer_evidence: list[EvidenceCandidate] = Field(min_length=1)
    candidate_errors: list[ErrorCandidate] = Field(default_factory=list)
    language_items: list = Field(default_factory=list, max_length=0)
    genre_candidate: None = None


SYSTEM_PROMPT = """Annotate a listening question from its given answer and passage.
Do not change the correct answer, question, options, transcript or timestamps.
Select enabled level-3 skills from the supplied dictionary. Include PRIMARY skill(s),
with a concrete rationale, and evidence for EVERY skill. ANSWER evidence is separate.
Use only consecutive body segments in the same passage; quotes must be verbatim.
S07/S13 and all skill usage boundaries are binding. Optional candidate errors need
specific support; they are question-level candidates, never student diagnoses.
Return exactly: {question_src_id,skills:[{skill_code,role,rationale,
evidence_segment_src_ids,quote}],answer_evidence:[{evidence_segment_src_ids,quote}],
candidate_errors:[{error_cause_code,rationale,option_letter,
evidence_segment_src_ids,quote}],language_items:[],genre_candidate:null}.
Never provide database IDs, answer overrides, timestamps, other keys or fake evidence.
"""


def annotation_input(payload, question):
    dictionary = load_dictionary()
    tables = {t["name"]: t for t in dictionary["tables"]}
    return {
        "question": question,
        "segments": [
            s
            for s in payload["transcript_segments"]
            if s["passage_src_id"] == question["passage_src_id"]
        ],
        "skills": [
            {
                k: v
                for k, v in r.items()
                if k
                not in {"legacy_payload_json", "reviewer", "reviewed_at", "review_note"}
            }
            for r in tables["skill"]["rows"]
            if r["skill_level"] == 3
        ],
        "candidate_error_dictionary": [
            {
                k: v
                for k, v in r.items()
                if k
                not in {"legacy_payload_json", "reviewer", "reviewed_at", "review_note"}
            }
            for r in tables["error_cause"]["rows"]
            if r["cause_level"] == 3
        ],
    }


def merge_candidate(payload, question, raw):
    candidate = AnnotationCandidate.model_validate(raw)
    if candidate.question_src_id != str(question["_src_id"]):
        raise ProcessingError("LLM_REFERENCE_INVALID", "模型返回错误题目引用")
    qid = candidate.question_src_id
    segments = {str(s["_src_id"]): s for s in payload["transcript_segments"]}
    for key in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        payload.setdefault(key, [])

    def evidence(value, label):
        refs = value.evidence_segment_src_ids
        if any(r not in segments for r in refs):
            raise ProcessingError("LLM_REFERENCE_INVALID", "模型引用不存在的句子")
        if any(
            segments[r]["segment_type"] != "body"
            or segments[r]["passage_src_id"] != question["passage_src_id"]
            for r in refs
        ):
            raise ProcessingError("LLM_REFERENCE_INVALID", "模型证据跨篇或指向提问")
        quote = " ".join(segments[r]["text"] for r in refs)
        ranges = None
        if value.quote != quote:
            if len(refs) != 1 or value.quote not in quote:
                raise ProcessingError(
                    "EVIDENCE_QUOTE_INVALID", "模型引文无法在正文原句中定位"
                )
            start = quote.index(value.quote)
            ranges = [[start, start + len(value.quote)]]
        eid = f"ev:{qid}:{label}"
        payload["evidences"].append(
            {
                "_src_id": eid,
                "passage_src_id": question["passage_src_id"],
                "segment_src_ids": refs,
                "char_ranges": ranges,
                "evidence_text": value.quote,
                "evidence_type": "正文",
                "source": "DeepSeek候选，待人工复核",
                "collector": "module3",
            }
        )
        return eid

    def relation(section, rid, kind, **values):
        payload[section].append(
            {
                "_src_id": rid,
                "relation_code": rid,
                "relation_kind": kind,
                "revision_no": 1,
                "is_current": True,
                "collector": "module3",
                **values,
            }
        )

    for i, skill in enumerate(candidate.skills):
        owner = f"qs:{qid}:{i}"
        eid = evidence(skill, f"s{i}")
        relation(
            "skill_question_relations",
            owner,
            "QUESTION_SKILL",
            question_src_id=qid,
            skill_code=skill.skill_code,
            role=skill.role,
            attributes_json={
                "annotation_reason": skill.rationale,
                "annotation_source": "deepseek-flash",
            },
        )
        relation(
            "skill_question_relations",
            f"se:{qid}:{i}",
            "SKILL_EVIDENCE",
            owner_relation_src_id=owner,
            evidence_src_id=eid,
            sort_order=1,
        )
    for i, value in enumerate(candidate.answer_evidence):
        eid = evidence(value, f"a{i}")
        relation(
            "other_relations",
            f"ae:{qid}:{i}",
            "ANSWER_EVIDENCE",
            question_src_id=qid,
            evidence_src_id=eid,
            sort_order=i + 1,
        )
    for i, value in enumerate(candidate.candidate_errors):
        eid = evidence(value, f"c{i}")
        owner = f"qc:{qid}:{i}"
        relation(
            "error_question_relations",
            owner,
            "QUESTION_ERROR_CANDIDATE",
            question_src_id=qid,
            error_cause_code=value.error_cause_code,
            option_letter=value.option_letter,
            attributes_json={
                "trigger_mechanism": value.rationale,
                "annotation_source": "deepseek-flash",
            },
        )
        relation(
            "error_question_relations",
            f"ce:{qid}:{i}",
            "CANDIDATE_EVIDENCE",
            owner_relation_src_id=owner,
            evidence_src_id=eid,
            sort_order=1,
        )
