"""Canonical editable projection, field differences and dependency invalidation."""

from copy import deepcopy

from app.core.errors import AppError
from app.module3.contracts import ProcessingError, fingerprint
from app.services.processing.validation import evidence_details, validate_result

SECTIONS = (
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
    "distractor_assessments",
)
SOURCE_SECTIONS = {
    "content_groups",
    "passages",
    "transcript_segments",
    "questions",
    "presentations",
}
HARD_ERRORS = {
    "SRC_ID_DUPLICATE",
    "QUESTION_PASSAGE_INVALID",
    "SEGMENT_PASSAGE_INVALID",
    "RELATION_REFERENCE_INVALID",
    "RELATION_OWNER_INVALID",
    "RELATION_KIND_INVALID",
    "RELATION_FIELDS_INVALID",
    "RELATION_ATTRIBUTES_INVALID",
    "SKILL_INVALID",
    "ERROR_CAUSE_INVALID",
    "EVIDENCE_INVALID",
    "EVIDENCE_QUOTE_INVALID",
    "EVIDENCE_TIME_INVALID",
    "EVIDENCE_OWNERSHIP_INVALID",
    "SOURCE_REFERENCE_INVALID",
    "DISTRACTOR_CORRECT_OPTION",
    "OPTION_ERROR_CORRECT_OPTION",
    "OPTION_ERROR_INVALID",
    "CANDIDATE_EVIDENCE_INVALID",
    "ANNOTATION_CONFLICT",
    "ANNOTATION_REFERENCE_INVALID",
    "ASSESSMENT_STATUS_CONFLICT",
    "DISTRACTOR_OPTION_SET_INVALID",
}


def invalid(message, path=None):
    return AppError(
        422, message, error_code="LIBRARY_CONTENT_INVALID", context={"path": path}
    )


def projection(payload):
    return {name: deepcopy(payload.get(name, [])) for name in SECTIONS}


def question_annotation_hash(snapshot, qid):
    owners = {
        r["_src_id"]
        for name in ("skill_question_relations", "error_question_relations")
        for r in snapshot[name]
        if r.get("question_src_id") == qid
    }
    selected = {
        name: [
            {k: v for k, v in r.items() if k != "source_candidate_hash"}
            for r in snapshot[name]
            if r.get("question_src_id") == qid
            or r.get("owner_relation_src_id") in owners
        ]
        for name in (
            "skill_question_relations",
            "error_question_relations",
            "other_relations",
            "distractor_assessments",
        )
    }
    refs = {
        r["evidence_src_id"]
        for rows in selected.values()
        for r in rows
        if r.get("evidence_src_id")
    }
    refs |= {
        r["evidence_src_id"]
        for a in selected["distractor_assessments"]
        for r in a.get("comparison_evidence_refs", [])
    }
    selected["evidences"] = [r for r in snapshot["evidences"] if r["_src_id"] in refs]
    return fingerprint(selected)


def build_payload(snapshot, baseline, *, save_version_id=None):
    payload = {**deepcopy(baseline), **deepcopy(snapshot)}
    annotation_hashes = {
        q["_src_id"]: question_annotation_hash(snapshot, q["_src_id"])
        for q in snapshot["questions"]
    }
    for assessment in payload["distractor_assessments"]:
        assessment["source_candidate_hash"] = annotation_hashes.get(
            assessment.get("question_src_id")
        )
    payload["library_provenance"] = {
        "contract": "library.v1",
        "save_version_id": str(save_version_id) if save_version_id else None,
        "annotation_hashes": annotation_hashes,
    }
    return payload


def canonical_snapshot(value):
    if not isinstance(value, dict) or set(value) - set(SECTIONS):
        raise invalid("快照只能包含可编辑内容，来源、方法及模型回执由服务器管理")
    snapshot = {}
    for section in SECTIONS:
        rows = value.get(section, [])
        if not isinstance(rows, list) or len(rows) > 5000:
            raise invalid("内容列表无效或过大", section)
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("_src_id"), str):
                raise invalid("对象必须具有稳定源身份", section)
            database_ids = {
                "id",
                "batch_id",
                "exam_paper_id",
                "passage_id",
                "question_id",
                "evidence_id",
                "source_paper_id",
                "audio_id",
                "skill_id",
                "error_cause_id",
            }
            if set(row) & database_ids:
                raise invalid(
                    "编辑对象只能使用卷内源身份，不能写正式数据库外键", section
                )
            if (
                not row["_src_id"]
                or len(row["_src_id"]) > 255
                or row["_src_id"] in seen
            ):
                raise invalid("对象源身份缺失或重复", section)
            seen.add(row["_src_id"])
        snapshot[section] = sorted(deepcopy(rows), key=lambda r: r["_src_id"])
    return snapshot


def differences(before, after):
    changes = []
    for section in SECTIONS:
        old = {r["_src_id"]: r for r in before.get(section, [])}
        new = {r["_src_id"]: r for r in after.get(section, [])}
        for src_id in sorted(set(old) | set(new)):
            if old.get(src_id) == new.get(src_id):
                continue
            changes.append(
                {
                    "section": section,
                    "src_id": src_id,
                    "before": old.get(src_id),
                    "after": new.get(src_id),
                    "fields": sorted(
                        k
                        for k in set(old.get(src_id, {})) | set(new.get(src_id, {}))
                        if old.get(src_id, {}).get(k) != new.get(src_id, {}).get(k)
                    ),
                }
            )
    return changes


def apply_changes(snapshot, changes):
    result = deepcopy(snapshot)
    for change in changes:
        section, src_id = change["section"], change["src_id"]
        rows = {r["_src_id"]: r for r in result[section]}
        if rows.get(src_id) != change["before"]:
            raise invalid("来源修订链前值不匹配", f"{section}/{src_id}")
        if change["after"] is None:
            rows.pop(src_id, None)
        else:
            rows[src_id] = deepcopy(change["after"])
        result[section] = sorted(rows.values(), key=lambda r: r["_src_id"])
    return result


def dependency_manifest(snapshot, baseline):
    return {
        "materials": fingerprint(baseline.get("source_materials", [])),
        "audio": fingerprint(baseline.get("audio", {})),
        "source": fingerprint({k: snapshot[k] for k in SOURCE_SECTIONS}),
        "alignment": fingerprint(snapshot["transcript_segments"]),
        "mapping": fingerprint(snapshot["presentations"]),
        "method": fingerprint(baseline.get("rules_manifest", {})),
    }


def impact(changes, before, after):
    sources = [r for r in changes if r["section"] in SOURCE_SECTIONS]
    passages = {
        v.get("passage_src_id", v.get("_src_id"))
        for r in sources
        for v in (r["before"], r["after"])
        if v
    }
    alignment = any(
        r["section"] in {"passages", "transcript_segments"} for r in sources
    )
    affected = {r["src_id"] for r in changes if r["section"] == "questions"}
    affected |= {
        q["_src_id"] for q in after["questions"] if q.get("passage_src_id") in passages
    }
    return {
        "final_review_invalidated": bool(changes),
        "source_review_invalidated": bool(sources),
        "alignment_required": alignment,
        "listening_required": alignment,
        "affected_question_src_ids": sorted(affected),
        "changed_objects": len(changes),
        "model_calls_started": False,
    }


def validate_snapshot(snapshot, baseline, request):
    """Draft incompleteness is allowed; invalid identities/relations are rejected."""
    payload = build_payload(snapshot, baseline)
    qids = {q["_src_id"]: q for q in snapshot["questions"]}
    additional_issues = []
    alignment_basis = {
        r["_src_id"]: r
        for r in baseline.get(
            "library_alignment_basis", baseline.get("transcript_segments", [])
        )
    }
    for segment in snapshot["transcript_segments"]:
        proof = alignment_basis.get(segment["_src_id"])
        if not proof or any(
            proof.get(k) != segment.get(k)
            for k in ("text", "speaker_code", "segment_type", "start_ms", "end_ms")
        ):
            additional_issues.append(
                {
                    "issue_code": "ALIGNMENT_UNVERIFIED",
                    "message": "句子依赖已变化，须重新取得实际对齐并核听",
                    "src_id": segment["_src_id"],
                }
            )
    for qid in qids:
        primary = [
            r
            for r in snapshot["skill_question_relations"]
            if r.get("question_src_id") == qid
            and r.get("relation_kind") == "QUESTION_SKILL"
            and r.get("role") == "PRIMARY"
        ]
        if len(primary) > 1:
            additional_issues.append(
                {
                    "issue_code": "PRIMARY_SKILL_INVALID",
                    "message": "每题须恰好一个主要技能",
                    "src_id": qid,
                }
            )
    for section in SECTIONS:
        for row in snapshot[section]:
            if (
                section == "error_question_relations"
                and row.get("relation_kind") == "QUESTION_ERROR_CANDIDATE"
            ):
                q = qids.get(row.get("question_src_id"))
                if q and row.get("option_letter") == q.get("correct_option"):
                    raise invalid("不能向正确基准选项挂错因", row["_src_id"])
            if section == "distractor_assessments":
                q = qids.get(row.get("question_src_id"))
                if not q or row.get("option_letter") not in set("ABCD") - {
                    q.get("correct_option")
                }:
                    raise invalid(
                        "三项评估只能关联本卷题目的错误基准选项", row["_src_id"]
                    )
    for section, code in (
        ("skill_question_relations", "skill_code"),
        ("error_question_relations", "error_cause_code"),
    ):
        keys = set()
        for row in snapshot[section]:
            if code not in row:
                continue
            key = (row.get("question_src_id"), row.get("option_letter"), row[code])
            if key in keys:
                raise invalid(
                    "同题同基准选项的标签重复；多份证据应关联同一关系", row["_src_id"]
                )
            keys.add(key)
    segments = {r["_src_id"]: r for r in snapshot["transcript_segments"]}
    passages = {r["_src_id"]: r for r in snapshot["passages"]}
    for evidence in snapshot["evidences"]:
        ranges = evidence.get("char_ranges")
        if ranges and len(ranges) > 1:
            for ref, span in zip(
                evidence.get("segment_src_ids", []), ranges, strict=False
            ):
                segment = segments.get(ref)
                if not segment or span != [0, len(segment.get("text", ""))]:
                    raise invalid("多句证据必须连续引用正文全文", evidence["_src_id"])
        try:
            details = evidence_details(
                evidence, segments, passages[evidence.get("passage_src_id")]
            )
            evidence.update(details)
        except (ProcessingError, KeyError, TypeError, ValueError, IndexError):
            raise invalid(
                "证据须为本篇连续 BODY 句，引文及时间须匹配有效对齐",
                evidence["_src_id"],
            ) from None
    try:
        issues = validate_result(payload, request)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise invalid(
            "内容结构无效，请检查字段类型及引用", type(error).__name__
        ) from None
    fatal = [r for r in issues if r["issue_code"] in HARD_ERRORS]
    if fatal:
        raise AppError(
            422,
            "内容含非法编码或引用",
            error_code="LIBRARY_CONTENT_INVALID",
            context={"issues": fatal[:30]},
        )
    return issues + additional_issues
