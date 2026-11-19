"""V7 model contract. Assessments are the sole source of new error candidates."""

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, model_validator

from app.module3.annotations import EvidenceCandidate, SkillCandidate
from app.schemas_processing import NonEmpty, StrictModel

CANDIDATE_VERSION = "m3.annotation-candidate.v7"


class EvidenceV7(EvidenceCandidate):
    evidence_segment_src_ids: list[NonEmpty] = Field(
        min_length=1, json_schema_extra={"uniqueItems": True}
    )


class AnswerEvidenceV7(EvidenceV7):
    support_note: NonEmpty


class SkillV7(SkillCandidate):
    skill_code: Literal[
        "S08",
        "S09",
        "S10",
        "S11",
        "S15",
        "S16",
        "S17",
        "S18",
        "S25",
        "S26",
        "S27",
        "S28",
        "S29",
        "S31",
        "S32",
        "S33",
        "S35",
        "S19",
        "S21",
        "S22",
        "S23",
        "S24",
    ]
    evidence_segment_src_ids: list[NonEmpty] = Field(
        min_length=1, json_schema_extra={"uniqueItems": True}
    )


class DistractorErrorCandidate(StrictModel):
    error_cause_code: Literal[
        "E1.1",
        "E1.3",
        "E1.2",
        "E2.1",
        "E3.1",
        "E3.2",
        "E3.3",
        "E4.2",
        "E5.1",
        "E5.2",
        "E7.1",
        "E4.3",
    ]
    rationale: NonEmpty
    evidence: list[EvidenceV7] = Field(min_length=1)
    personal_verification_needed: NonEmpty


class DistractorAssessment(StrictModel):
    model_config: ClassVar[ConfigDict] = {
        "json_schema_extra": {
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": status}}},
                    "then": {
                        "properties": {
                            "candidates": {"minItems": 1}
                            if status == "SUPPORTED"
                            else {"maxItems": 0},
                            "unresolved_points": {"minItems": 1}
                            if status == "INSUFFICIENT_EVIDENCE"
                            else {"maxItems": 0},
                        }
                    },
                }
                for status in (
                    "SUPPORTED",
                    "NO_SUPPORTED_CANDIDATE",
                    "INSUFFICIENT_EVIDENCE",
                )
            ]
        }
    }
    option_letter: Literal["A", "B", "C", "D"]
    status: Literal["SUPPORTED", "NO_SUPPORTED_CANDIDATE", "INSUFFICIENT_EVIDENCE"]
    reason: NonEmpty
    comparison_evidence: list[EvidenceV7]
    candidates: list[DistractorErrorCandidate]
    unresolved_points: list[NonEmpty]

    @model_validator(mode="after")
    def status_consistent(self):
        if (
            (
                self.status == "SUPPORTED"
                and (not self.candidates or self.unresolved_points)
            )
            or (
                self.status == "NO_SUPPORTED_CANDIDATE"
                and (self.candidates or self.unresolved_points)
            )
            or (
                self.status == "INSUFFICIENT_EVIDENCE"
                and (self.candidates or not self.unresolved_points)
            )
        ):
            raise ValueError("ASSESSMENT_STATUS_CONFLICT: 候选/未决点与评估状态冲突")
        return self


class AnnotationCandidateV7(StrictModel):
    question_src_id: NonEmpty
    skills: list[SkillV7] = Field(
        min_length=1,
        json_schema_extra={
            "contains": {
                "properties": {"role": {"const": "PRIMARY"}},
                "required": ["role"],
            },
            "minContains": 1,
            "maxContains": 1,
        },
    )
    answer_evidence: list[AnswerEvidenceV7] = Field(min_length=1)
    distractor_assessments: list[DistractorAssessment] = Field(
        min_length=3, max_length=3
    )
    uncertainties: list[NonEmpty]
    language_items: list = Field(max_length=0)
    genre_candidate: None

    @model_validator(mode="after")
    def exactly_one_primary(self):
        if sum(s.role == "PRIMARY" for s in self.skills) != 1:
            raise ValueError("ANNOTATION_PRIMARY_INVALID: 每题恰好一个主要技能")
        return self


def generation_state(raw):
    candidate = AnnotationCandidateV7.model_validate(raw)
    if any(
        a.status == "INSUFFICIENT_EVIDENCE" for a in candidate.distractor_assessments
    ):
        return "generation_incomplete"
    return (
        "generated_nonempty"
        if any(a.candidates for a in candidate.distractor_assessments)
        else "generated_empty"
    )
