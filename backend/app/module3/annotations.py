"""Strict candidate schemas and deterministic conversion to evidence relations."""

from typing import Literal

from pydantic import Field

from app.module3.contracts import ProcessingError
from app.schemas_processing import NonEmpty, StrictModel
from app.services.processing.validation import load_dictionary


class EvidenceCandidate(StrictModel):
    evidence_segment_src_ids: list[NonEmpty] = Field(min_length=1)
    quote: NonEmpty
    support_note: NonEmpty | None = None


class SkillCandidate(EvidenceCandidate):
    skill_code: NonEmpty
    role: Literal["PRIMARY", "AUXILIARY"]
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
with a concrete rationale, and evidence for EVERY skill.
Use role PRIMARY or AUXILIARY. ANSWER evidence is separate.
Use only consecutive body segments in the same passage; quotes must be verbatim.
S07/S13 and all skill usage boundaries are binding. Optional candidate errors need
specific support; they are question-level candidates, never student diagnoses.
Return exactly: {question_src_id,skills:[{skill_code,role,rationale,
evidence_segment_src_ids,quote}],answer_evidence:[{evidence_segment_src_ids,quote}],
candidate_errors:[{error_cause_code,rationale,option_letter,
evidence_segment_src_ids,quote}],language_items:[],genre_candidate:null}.
Never provide database IDs, answer overrides, timestamps, other keys or fake evidence.
For each answer_evidence also provide support_note: explain how the quoted facts
support the supplied correct option and the question's target, including any
arithmetic/inference. Select the smallest sufficient evidence span; do not quote
an entire passage when a sentence answers the question. Normally choose ONE PRIMARY
skill, at most two where independently necessary. Directly stated facts are not
implicit inference; a word appearing does not prove a vocabulary/grammar skill.
Only usage_scope=题目标注 is eligible; S07/S13 are diagnostic-only and forbidden.
S11 is local word/phrase equivalence; S23 concerns whole proposition matching;
do not mechanically duplicate them. Candidate errors are OPTIONAL: omit them unless
a particular distractor and its concrete mechanism support the selected definition.
No learner response is supplied: never diagnose an individual or assume unknown words.
Use Chinese for rationale/support_note. Do not echo boilerplate or self-rate accuracy.

PRIMARY selection is an operation decision, not a list of everything a listener does:
identify the decisive NONTRIVIAL operation needed to get from the evidence to the
correct option. If arithmetic, aggregation, magnitude or degree comparison is
necessary, S18 takes PRIMARY over generic S21 fact retrieval. Do not label an
arithmetic answer as simple fact retrieval just because its input numbers are explicit.
Direct extraction of a single stated number remains S21. Combining numbers within
one sentence is not automatically S29 cross-sentence integration.

Default to NO AUXILIARY skills. Add an AUXILIARY only when the rationale identifies
a second, distinct and necessary operation with a concrete difficulty beyond the
PRIMARY. Merely recognizing the same statement in an almost identical option is
not grounds to append S23. Matching "the" to "an", copying the same words,
identifying the question topic, and retrieving inputs for an arithmetic operation
do not justify extra skill labels. This applies to every question, not just examples.
S23 requires a substantive whole-proposition paraphrase/mapping beyond a trivial
local wording change; S11 requires a consequential local equivalence, not any synonym.
For directly stated causes/purposes, S22 alone normally suffices.

Evidence sufficiency comes BEFORE brevity: each answer evidence must establish the
predicate actually asked, not merely mention the same actor or action. If one sentence
states an action and its adjacent sentence establishes the asked outcome, include
BOTH consecutive sentences. Vague statements about change do not by themselves
establish improvement, motive or cause. Never use the question/answer to fill a fact
missing from the quoted evidence. Reference supplied sentence IDs in rationales;
do not invent paragraph numbers or structural locations not present in the input.

Speaker M/W is source data, not something to infer from turn order. Keep speaker,
referent and target attribution correct. Include the antecedent when the selected
sentence says only he/she/his/it and the target entity would otherwise be unknown.
When both speakers' attitude is asked, evidence must include both voices (including
the agreement if one person's evaluation concerns a different target).
Within each evidence_segment_src_ids array, EVERY intervening body ID must be
included: e.g. s032,s033,s035 is INVALID; quote s032,s033,s034,s035 verbatim instead,
or use separate evidence objects for distinct spans. Never splice a skipped span.

Use the most specific decisive operation as PRIMARY. Where understanding a fixed
idiom is necessary to obtain the answer meaning, S10 takes PRIMARY over generic
cause/fact retrieval. Conversely, a question asking WHAT WORD another speaker
explicitly found confusing is normally S21 retrieval of their expressed reaction;
do not add S08 unless resolving that word's contextual meaning is necessary to
distinguish the options. A word merely being the topic does not establish a lexical
meaning test. Rationale facts must be supported by the selected evidence.
"""


def annotation_input(payload, question):
    dictionary = load_dictionary()
    tables = {t["name"]: t for t in dictionary["tables"]}
    return {
        "question": {
            k: question[k]
            for k in (
                "_src_id",
                "passage_src_id",
                "question_text",
                "option_a",
                "option_b",
                "option_c",
                "option_d",
                "correct_option",
                "explanation_text",
            )
        },
        "segments": [
            {
                **{
                    k: s[k]
                    for k in ("_src_id", "text", "segment_type", "segment_index")
                },
                "speaker": s.get("speaker"),
            }
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
            and r["status"] == "启用"
            and r.get("usage_scope") == "题目标注"
        ],
        "candidate_error_dictionary": [
            {
                k: v
                for k, v in r.items()
                if k
                not in {"legacy_payload_json", "reviewer", "reviewed_at", "review_note"}
            }
            for r in tables["error_cause"]["rows"]
            if r["cause_level"] == 3 and r["status"] == "启用"
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
                "start_ms": segments[refs[0]]["start_ms"],
                "end_ms": segments[refs[-1]]["end_ms"],
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
            attributes_json={"support_note": value.support_note or ""},
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
