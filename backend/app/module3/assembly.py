"""Assemble fixed-format CET listening groups without allowing answer fabrication."""

import re

from pydantic import Field

from app.module3.contracts import ProcessingError
from app.module3.llm import request_json
from app.schemas_processing import NonEmpty, StrictModel


class QuestionCandidate(StrictModel):
    question_no: int = Field(gt=0)
    question_segment_src_id: NonEmpty
    question_text: NonEmpty
    option_a: NonEmpty
    option_b: NonEmpty
    option_c: NonEmpty
    option_d: NonEmpty
    correct_option: NonEmpty
    explanation_quote: NonEmpty
    paper_page: int = Field(gt=0)
    answer_page: int = Field(gt=0)


class GroupCandidate(StrictModel):
    body_segment_src_ids: list[NonEmpty] = Field(min_length=1)
    questions: list[QuestionCandidate] = Field(min_length=1)


def compact(text):
    return re.sub(r"\s+", "", text).casefold()


ASSEMBLY_PROMPT = """Extract ONLY the requested CET listening question group.
Input has PDF/OCR pages and actual aligned speech segments. Preserve source options,
answer and explanation; do not infer missing content. Map the complete body and the
spoken question for each number to segment IDs. Exclude instructions/announcements.
Never combine different groups. question_text must quote its spoken question segment.
explanation_quote must be a verbatim nonempty substring from the indicated answer page;
Include the answer letter in that substring as proof. Do not write your own
explanation. Every option must occur verbatim in the indicated original paper page.
Return exactly {body_segment_src_ids:[...],questions:[{question_no,
question_segment_src_id,question_text,option_a,option_b,option_c,option_d,
correct_option,explanation_quote,paper_page,answer_page}]}.
No database IDs or timestamps. Ambiguous content: return {"unresolved":"reason"}.
"""


def assemble(task, extracted, aligned, audio_meta, settings):
    segments = {s["_src_id"]: s for s in aligned["segments"]}
    result = {
        "schema_version": "m3.v1",
        "exam_paper": task.request["exam_paper"],
        "audio": audio_meta,
        "content_groups": [
            {
                "_src_id": "group:1",
                "content_group_code": task.exam_paper_code + "_CG",
                "group_name": task.exam_paper_code,
                "exam_level_scope": task.request["exam_paper"]["exam_level"],
                "collector": "module3",
                "status": "启用",
            }
        ],
        "passages": [],
        "transcript_segments": [],
        "questions": [],
        "presentations": [],
        "language_items": [],
    }
    papers = [
        p
        for p in extracted["pages"]
        if p["source_kind"] in {"paper_text", "paper_scan"}
    ]
    answers = [
        p for p in extracted["pages"] if p["source_kind"] == "answer_explanation"
    ]
    # Send text and locators only. Raw audio and images never leave the machine.
    context = {
        "paper_pages": [
            {k: p[k] for k in ("material_id", "page", "text")} for p in papers
        ],
        "answer_pages": [
            {k: p[k] for k in ("material_id", "page", "text")} for p in answers
        ],
        "segments": [{k: s[k] for k in ("_src_id", "text")} for s in segments.values()],
    }
    used = set()
    for i, group in enumerate(task.request["expected_question_ranges"], 1):
        raw, _ = request_json(
            task.id,
            task.input_hash,
            "sample" if i <= 2 else "run",
            ASSEMBLY_PROMPT,
            {**context, "requested_group": group},
            settings,
        )
        if "unresolved" in raw:
            raise ProcessingError(
                "ASSEMBLY_UNRESOLVED",
                "原件组装存在未决内容：" + str(raw["unresolved"])[:300],
            )
        candidate = GroupCandidate.model_validate(raw)
        numbers = [q.question_no for q in candidate.questions]
        if numbers != list(range(group["start"], group["end"] + 1)):
            raise ProcessingError("QUESTION_RANGE_INVALID", "模型组装未覆盖可信题组")
        refs = candidate.body_segment_src_ids + [
            q.question_segment_src_id for q in candidate.questions
        ]
        if (
            len(refs) != len(set(refs))
            or set(refs) & used
            or any(r not in segments for r in refs)
        ):
            raise ProcessingError(
                "ASSEMBLY_REFERENCE_INVALID", "组装引用重复、跨组或不存在"
            )
        body = [segments[r] for r in candidate.body_segment_src_ids]
        if any(
            s["start_ms"] is None or s["end_ms"] is None
            for s in (segments[r] for r in refs)
        ):
            raise ProcessingError("ALIGNMENT_UNVERIFIED", "组装引用尚无有效句级边界")
        if [s["start_ms"] for s in body] != sorted(s["start_ms"] for s in body):
            raise ProcessingError("ASSEMBLY_REFERENCE_INVALID", "正文句顺序无效")
        passage_id = f"passage:{i}"
        result["passages"].append(
            {
                "_src_id": passage_id,
                "passage_code": f"P{i:02}",
                "passage_index": i,
                "passage_type": group["section"],
                "start_ms": body[0]["start_ms"],
                "body_end_ms": body[-1]["end_ms"],
                "end_ms": max(segments[r]["end_ms"] for r in refs),
                "collector": "module3",
            }
        )
        for n, sid in enumerate(refs, 1):
            s = segments[sid]
            result["transcript_segments"].append(
                {
                    **{
                        k: s[k]
                        for k in (
                            "_src_id",
                            "text",
                            "start_ms",
                            "end_ms",
                            "alignment_status",
                        )
                    },
                    "passage_src_id": passage_id,
                    "segment_index": n,
                    "segment_type": "body"
                    if sid in candidate.body_segment_src_ids
                    else "question",
                    "collector": "module3",
                }
            )
        for q in candidate.questions:
            paper = next((p for p in papers if p["page"] == q.paper_page), None)
            answer = next((p for p in answers if p["page"] == q.answer_page), None)
            if paper is None or answer is None:
                raise ProcessingError("SOURCE_REFERENCE_INVALID", "组装原件页码不存在")
            if any(
                compact(getattr(q, "option_" + letter)) not in compact(paper["text"])
                for letter in "abcd"
            ):
                raise ProcessingError(
                    "OPTION_SOURCE_INVALID", "组装选项无法在原卷页定位"
                )
            if compact(q.explanation_quote) not in compact(answer["text"]):
                raise ProcessingError(
                    "EXPLANATION_SOURCE_INVALID", "解析引文无法在来源页定位"
                )
            if q.correct_option not in {"A", "B", "C", "D"} or not re.search(
                r"(?<![A-Za-z])" + re.escape(q.correct_option) + r"(?![A-Za-z])",
                q.explanation_quote,
            ):
                raise ProcessingError(
                    "ANSWER_SOURCE_INVALID", "标准答案未保留明确来源字母"
                )
            if compact(q.question_text) not in compact(
                segments[q.question_segment_src_id]["text"]
            ):
                raise ProcessingError("QUESTION_SOURCE_INVALID", "题干与录音提问不符")
            qid = f"q:{q.question_no}"
            result["questions"].append(
                {
                    "_src_id": qid,
                    "question_code": f"Q{q.question_no:02}",
                    "question_index": q.question_no,
                    "passage_src_id": passage_id,
                    "question_segment_src_id": q.question_segment_src_id,
                    **q.model_dump(
                        include={
                            "question_text",
                            "option_a",
                            "option_b",
                            "option_c",
                            "option_d",
                            "correct_option",
                        }
                    ),
                    "explanation_text": q.explanation_quote,
                    "explanation_source": (
                        f"material:{answer['material_id']} page:{answer['page']}"
                    ),
                    "source_refs": [
                        {
                            "material_id": p["material_id"],
                            "locator": {"page": p["page"]},
                            "original_text": p["text"],
                        }
                        for p in (paper, answer)
                    ],
                    "collector": "module3",
                }
            )
            result["presentations"].append(
                {
                    "_src_id": f"pr:{q.question_no}",
                    "question_src_id": qid,
                    "question_no": q.question_no,
                    "option_mapping_state": "已知",
                    "mapping_source": "同一原卷选项逐字定位",
                    "option_letter_mapping": dict(zip("ABCD", "ABCD", strict=True)),
                    "collector": "module3",
                }
            )
        used.update(refs)
    return result
