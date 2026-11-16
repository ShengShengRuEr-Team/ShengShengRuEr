"""Structural checks independent from model inference and human semantic review."""

from __future__ import annotations

import json
from pathlib import Path

from app.module3.contracts import ProcessingError

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config" / "module3"


def load_dictionary() -> dict:
    return json.loads(
        (CONFIG_DIR / "dictionary-schema.json").read_text(encoding="utf-8")
    )


def entity_index(rows: list[dict], entity: str) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        key = str(row.get("_src_id", ""))
        if not key or key in indexed:
            raise ProcessingError("SRC_ID_DUPLICATE", f"{entity}临时ID缺失或重复")
        indexed[key] = row
    return indexed


def evidence_details(evidence: dict, segments: dict, passage: dict) -> dict:
    refs = evidence.get("segment_src_ids", [])
    if not refs or len(refs) != len(set(refs)):
        raise ProcessingError("EVIDENCE_INVALID", "证据必须引用不重复的连续正文句")
    try:
        selected = [segments[str(ref)] for ref in refs]
    except KeyError:
        raise ProcessingError("EVIDENCE_INVALID", "证据引用了不存在的句子") from None
    if any(
        s["segment_type"] != "body"
        or str(s["passage_src_id"]) != str(passage["_src_id"])
        for s in selected
    ):
        raise ProcessingError("EVIDENCE_INVALID", "证据只能引用同篇正文")
    ordered = sorted(
        (
            s
            for s in segments.values()
            if str(s["passage_src_id"]) == str(passage["_src_id"])
        ),
        key=lambda s: s["segment_index"],
    )
    positions = [ordered.index(s) for s in selected]
    if positions != list(range(positions[0], positions[0] + len(positions))):
        raise ProcessingError("EVIDENCE_INVALID", "证据句顺序不连续或夹入提问")
    texts = []
    ranges = evidence.get("char_ranges")
    if ranges is not None and len(ranges) != len(selected):
        raise ProcessingError("EVIDENCE_INVALID", "字符范围与句子数不符")
    for i, segment in enumerate(selected):
        text = segment["text"]
        if ranges:
            start, end = ranges[i]
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(text)
            ):
                raise ProcessingError("EVIDENCE_INVALID", "证据字符范围越界")
            text = text[start:end]
        texts.append(text)
    quote = " ".join(texts)
    if evidence.get("evidence_text") != quote:
        raise ProcessingError("EVIDENCE_QUOTE_INVALID", "证据引文与正文字符范围不符")
    start, end = selected[0]["start_ms"], selected[-1]["end_ms"]
    if evidence.get("start_ms", start) != start or evidence.get("end_ms", end) != end:
        raise ProcessingError("EVIDENCE_TIME_INVALID", "证据时间只能取引用句边界")
    return {"start_ms": start, "end_ms": end, "evidence_text": quote}


def validate_result(
    payload: dict, request: dict, dictionary: dict | None = None
) -> list[dict]:
    """Collect failures; absence of failures says nothing about semantic correctness."""
    issues = []

    def issue(code: str, message: str, src_id=None):
        issues.append(
            {
                "kind": code.lower(),
                "issue_code": code,
                "message": message,
                "severity": "error",
                "stage": "validate",
                "src_id": src_id,
            }
        )

    dictionary = dictionary or load_dictionary()
    tables = {t["name"]: t for t in dictionary["tables"]}
    try:
        indexes = {
            name: entity_index(payload.get(name, []), name)
            for name in (
                "content_groups",
                "passages",
                "transcript_segments",
                "questions",
                "presentations",
                "evidences",
                "skill_question_relations",
                "error_question_relations",
                "other_relations",
                "language_items",
            )
        }
    except ProcessingError as exc:
        issue(exc.code, str(exc))
        return issues
    passages, segments, questions = (
        indexes[k] for k in ("passages", "transcript_segments", "questions")
    )
    expected = request.get("expected_question_count")
    source = request.get("expected_question_count_source")
    if expected is None or not source:
        issue("EXPECTED_COUNT_MISSING", "缺少可信题量及原件核对来源")
    elif len(questions) != expected:
        issue("QUESTION_COUNT_MISMATCH", "题目数量与可信题量不符")
    presentations = list(indexes["presentations"].values())
    if expected and sorted(p.get("question_no", 0) for p in presentations) != list(
        range(1, expected + 1)
    ):
        issue("QUESTION_RANGE_INVALID", "题号未完整且唯一覆盖原卷")
    mapped = [str(p.get("question_src_id")) for p in presentations]
    if len(mapped) != len(set(mapped)) or set(mapped) != set(questions):
        issue("PRESENTATION_INVALID", "原卷映射与题目不能一一对应")
    for p in presentations:
        mapping = p.get("option_letter_mapping")
        if (
            not isinstance(mapping, dict)
            or set(mapping) != set("ABCD")
            or set(mapping.values()) != set("ABCD")
        ):
            issue("OPTION_MAPPING_INVALID", "选项映射须为A-D完整排列", p["_src_id"])
    duration = payload.get("audio", {}).get("duration_ms", 0)
    for passage in passages.values():
        a, b, c = (passage.get(k) for k in ("start_ms", "body_end_ms", "end_ms"))
        if (
            not all(type(t) is int for t in (a, b, c))
            or not 0 <= a <= b <= c <= duration
        ):
            issue("PASSAGE_TIME_INVALID", "篇章边界无效", passage["_src_id"])
    segment_numbers = set()
    for s in segments.values():
        sid = s["_src_id"]
        p = passages.get(str(s.get("passage_src_id")))
        start, end = s.get("start_ms"), s.get("end_ms")
        if p is None:
            issue("SEGMENT_PASSAGE_INVALID", "句子篇章不存在", sid)
            continue
        pair = (str(s["passage_src_id"]), s.get("segment_index"))
        if pair in segment_numbers:
            issue("SEGMENT_INDEX_DUPLICATE", "同篇句序重复", sid)
        segment_numbers.add(pair)
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= duration
            or start < p.get("start_ms", 0)
            or end > (p.get("end_ms") or duration)
        ):
            issue("SEGMENT_TIME_INVALID", "句级时间无效或超出篇章", sid)
        if (
            s.get("segment_type") not in {"body", "question"}
            or not str(s.get("text", "")).strip()
        ):
            issue("SEGMENT_TEXT_INVALID", "句子文本或正文/提问归属无效", sid)
        if s.get("alignment_status") != "aligned":
            issue(
                "ALIGNMENT_UNVERIFIED",
                "句子未获得可靠对齐，不能将回退或插值当成功",
                sid,
            )
    for q in questions.values():
        qid = q["_src_id"]
        if str(q.get("passage_src_id")) not in passages:
            issue("QUESTION_PASSAGE_INVALID", "题目篇章不存在", qid)
        for field in (
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "explanation_text",
            "explanation_source",
        ):
            if not str(q.get(field, "")).strip():
                issue("QUESTION_FIELD_MISSING", f"题目缺少{field}", qid)
        if (
            q.get("correct_option") not in "ABCD"
            or len(q.get("correct_option", "")) != 1
        ):
            issue("ANSWER_INVALID", "标准答案无效", qid)
        s = segments.get(str(q.get("question_segment_src_id")))
        if (
            s is None
            or s.get("segment_type") != "question"
            or str(s["passage_src_id"]) != str(q.get("passage_src_id"))
        ):
            issue("QUESTION_SEGMENT_INVALID", "题干未关联同篇录音提问", qid)
        refs = q.get("source_refs", [])
        if any(
            ref.get("material_id") not in request.get("material_ids", [])
            for ref in refs
        ):
            issue("SOURCE_REFERENCE_INVALID", "来源引用不属于本任务登记材料", qid)
        if not refs or any(
            not ref.get("material_id") or not ref.get("locator") for ref in refs
        ):
            issue("SOURCE_REFERENCE_MISSING", "题目/解析缺少原件定位", qid)
    for e in indexes["evidences"].values():
        try:
            p = passages[str(e.get("passage_src_id"))]
            evidence_details(e, segments, p)
        except (ProcessingError, KeyError, TypeError) as exc:
            issue(
                getattr(exc, "code", "EVIDENCE_INVALID"),
                str(exc) if isinstance(exc, ProcessingError) else "证据引用无效",
                e["_src_id"],
            )
    skills = {r["skill_code"]: r for r in tables["skill"]["rows"]}
    errors = {r["error_cause_code"]: r for r in tables["error_cause"]["rows"]}
    for section in (
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        for r in indexes[section].values():
            rid, kind = r["_src_id"], r.get("relation_kind")
            allowed = {
                "QUESTION_SKILL": {"question_src_id", "skill_code", "role"},
                "SKILL_EVIDENCE": {
                    "owner_relation_src_id",
                    "evidence_src_id",
                    "sort_order",
                },
                "QUESTION_ERROR_CANDIDATE": {
                    "question_src_id",
                    "error_cause_code",
                    "option_letter",
                },
                "CANDIDATE_EVIDENCE": {
                    "owner_relation_src_id",
                    "evidence_src_id",
                    "sort_order",
                },
                "ANSWER_EVIDENCE": {"question_src_id", "evidence_src_id", "sort_order"},
                "QUESTION_LANGUAGE_ITEM": {
                    "question_src_id",
                    "language_item_src_id",
                    "segment_src_id",
                    "option_letter",
                },
            }
            fields = allowed.get(kind)
            if fields is None:
                issue("RELATION_KIND_INVALID", "卷内关系类型无效", rid)
                continue
            common = {
                "_src_id",
                "relation_code",
                "relation_kind",
                "revision_no",
                "is_current",
                "attributes_json",
                "collector",
                "review_status",
                "notes",
            }
            if any(v is not None and k not in fields | common for k, v in r.items()):
                issue("RELATION_FIELDS_INVALID", "关系存在不允许的对象字段", rid)
            attr = r.get("attributes_json") or {}
            rule = dictionary["rulesByKind"].get(kind, {})
            attr_keys = rule.get("props", [])
            if not isinstance(attr, dict) or set(attr) - set(attr_keys):
                issue("RELATION_ATTRIBUTES_INVALID", "关系属性超出白名单", rid)
            q = questions.get(str(r.get("question_src_id")))
            if (
                kind
                in {
                    "QUESTION_SKILL",
                    "QUESTION_ERROR_CANDIDATE",
                    "ANSWER_EVIDENCE",
                    "QUESTION_LANGUAGE_ITEM",
                }
                and q is None
            ):
                issue("RELATION_REFERENCE_INVALID", "关系题目不存在", rid)
            if kind == "QUESTION_SKILL":
                skill = skills.get(r.get("skill_code"))
                if (
                    skill is None
                    or skill.get("skill_level") != 3
                    or skill.get("status") != "启用"
                    or r.get("role") not in {"PRIMARY", "AUXILIARY"}
                ):
                    issue("SKILL_INVALID", "只能标注启用的三级技能和有效角色", rid)
                if not attr.get("annotation_reason"):
                    issue("SKILL_REASON_MISSING", "技能必须有标注理由", rid)
            if kind == "QUESTION_ERROR_CANDIDATE":
                cause = errors.get(r.get("error_cause_code"))
                if (
                    cause is None
                    or cause.get("cause_level") != 3
                    or cause.get("status") != "启用"
                ):
                    issue("ERROR_CAUSE_INVALID", "候选错因必须为启用三级项", rid)
            if kind in {"SKILL_EVIDENCE", "CANDIDATE_EVIDENCE"}:
                owner = indexes[section].get(str(r.get("owner_relation_src_id")))
                expected_kind = (
                    "QUESTION_SKILL"
                    if kind == "SKILL_EVIDENCE"
                    else "QUESTION_ERROR_CANDIDATE"
                )
                if owner is None or owner.get("relation_kind") != expected_kind:
                    issue("RELATION_OWNER_INVALID", "证据关系owner种类或归属无效", rid)
                else:
                    q = questions.get(str(owner.get("question_src_id")))
            if kind in {"SKILL_EVIDENCE", "CANDIDATE_EVIDENCE", "ANSWER_EVIDENCE"}:
                e = indexes["evidences"].get(str(r.get("evidence_src_id")))
                if (
                    e is None
                    or q is None
                    or str(e.get("passage_src_id")) != str(q.get("passage_src_id"))
                ):
                    issue(
                        "EVIDENCE_OWNERSHIP_INVALID",
                        "证据须属于目标题目的正文篇章",
                        rid,
                    )
    skill_rows = list(indexes["skill_question_relations"].values())
    answer_rows = list(indexes["other_relations"].values())
    for qid in questions:
        primary = [
            r
            for r in skill_rows
            if r.get("relation_kind") == "QUESTION_SKILL"
            and str(r.get("question_src_id")) == qid
            and r.get("role") == "PRIMARY"
        ]
        if not primary:
            issue("PRIMARY_SKILL_MISSING", "每题必须有主要技能", qid)
        for owner in [
            r
            for r in skill_rows
            if r.get("relation_kind") == "QUESTION_SKILL"
            and str(r.get("question_src_id")) == qid
        ]:
            if not any(
                r.get("relation_kind") == "SKILL_EVIDENCE"
                and str(r.get("owner_relation_src_id")) == str(owner["_src_id"])
                for r in skill_rows
            ):
                issue(
                    "SKILL_EVIDENCE_MISSING",
                    "每条技能关联必须有正文证据",
                    owner["_src_id"],
                )
        if not any(
            r.get("relation_kind") == "ANSWER_EVIDENCE"
            and str(r.get("question_src_id")) == qid
            for r in answer_rows
        ):
            issue("ANSWER_EVIDENCE_MISSING", "每题必须有答案证据", qid)
    return issues
