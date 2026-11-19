"""Bounded, version-pinned draft projections; private execution details stay private."""

from functools import cache

from app.module3.contracts import result_hash
from app.module3.option_annotations import invert_option_mapping
from app.services.processing import orchestration as o
from app.services.processing import reviewing
from app.services.processing import workflows as w


@cache
def dictionary_names():
    from app.services.processing.validation import load_dictionary

    return {
        row["error_cause_code"]: row["cause_name"]
        for table in load_dictionary()["tables"]
        if table["name"] == "error_cause"
        for row in table["rows"]
    }


@cache
def skill_names():
    from app.services.processing.validation import load_dictionary

    return {
        row["skill_code"]: row["skill_name"]
        for table in load_dictionary()["tables"]
        if table["name"] == "skill"
        for row in table["rows"]
    }


def public_value(value):
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: public_value(item)
            for key, item in value.items()
            if key
            not in {
                "storage_key",
                "source_storage_key",
                "path",
                "page_image",
                "model_root",
                "nltk_data",
                "execution_token",
                "lease_token",
                "worker_id",
                "call",
                "rules_manifest",
            }
        }
    return value


def coverage_summary(content, decisions=()):
    assessments = content.get("distractor_assessments", [])
    expected = {a["_src_id"] for a in assessments}
    reviewed = {
        r["reference"]
        for item in decisions
        for r in item.get("distractor_assessments", [])
        if r.get("decision") == "approved" and r.get("reference") in expected
    }
    return {
        "assessed": len(assessments),
        "expected": len(content["questions"]) * 3,
        "resolved": sum(a["status"] != "INSUFFICIENT_EVIDENCE" for a in assessments),
        "reviewed": len(reviewed),
        "empty_options": sum(
            a["status"] == "NO_SUPPORTED_CANDIDATE" for a in assessments
        ),
        "unresolved": sum(a["status"] == "INSUFFICIENT_EVIDENCE" for a in assessments),
    }


def question_view(content, question):
    qid = question["_src_id"]
    evidences = {r["_src_id"]: r for r in content.get("evidences", [])}
    error_rows = content.get("error_question_relations", [])
    skill_rows = content.get("skill_question_relations", [])
    presentation = next(
        row for row in content["presentations"] if row["question_src_id"] == qid
    )
    inverse = invert_option_mapping(presentation["option_letter_mapping"])

    def evidence_groups(rows, owner):
        return [
            {
                **evidences[row["evidence_src_id"]],
                "relation_src_id": row["_src_id"],
                "support_note": (row.get("attributes_json") or {}).get(
                    "support_note", ""
                ),
            }
            for row in sorted(rows, key=lambda row: row.get("sort_order") or 0)
            if row.get("owner_relation_src_id") == owner
        ]

    options = []
    assessments = {
        a["option_letter"]: a
        for a in content.get("distractor_assessments", [])
        if a["question_src_id"] == qid
    }
    for display, base in presentation["option_letter_mapping"].items():
        errors = [
            {
                "relation_src_id": row["_src_id"],
                "code": row["error_cause_code"],
                "name": dictionary_names().get(
                    row["error_cause_code"], row["error_cause_code"]
                ),
                "rationale": (row.get("attributes_json") or {}).get(
                    "trigger_mechanism", ""
                ),
                "personal_verification_needed": row.get("personal_verification_needed"),
                "evidence": evidence_groups(error_rows, row["_src_id"]),
            }
            for row in error_rows
            if row.get("question_src_id") == qid and row.get("option_letter") == base
        ]
        options.append(
            {
                "display_letter": display,
                "base_option_letter": base,
                "text": question["option_" + base.lower()],
                "error_causes": errors,
                "assessment": (
                    {
                        **{
                            k: v
                            for k, v in assessments[base].items()
                            if k != "comparison_evidence_refs"
                        },
                        "comparison_evidence": [
                            {
                                **evidences[ref["evidence_src_id"]],
                                "support_note": ref.get("support_note"),
                            }
                            for ref in assessments[base]["comparison_evidence_refs"]
                        ],
                    }
                    if base in assessments
                    else None
                ),
            }
        )
    receipt = next(
        (
            r
            for r in content.get("generation_receipts", [])
            if r["question_src_id"] == qid
        ),
        None,
    )
    return public_value(
        {
            **question,
            "question_src_id": qid,
            "question_no": presentation["question_no"],
            "correct_option_base": question["correct_option"],
            "correct_option_display": inverse[question["correct_option"]],
            "options": sorted(options, key=lambda row: row["display_letter"]),
            "skills": [
                {
                    **row,
                    "skill_name": skill_names().get(row["skill_code"]),
                    "evidence": evidence_groups(skill_rows, row["_src_id"]),
                }
                for row in skill_rows
                if row.get("question_src_id") == qid
            ],
            "answer_evidence": [
                {
                    **evidences[row["evidence_src_id"]],
                    "relation_src_id": row["_src_id"],
                    "support_note": (row.get("attributes_json") or {}).get(
                        "support_note", ""
                    ),
                }
                for row in content.get("other_relations", [])
                if row.get("question_src_id") == qid
                and row["relation_kind"] == "ANSWER_EVIDENCE"
            ],
            "generation_state": receipt["state"] if receipt else "not_generated",
            "assessment_summary": {
                "expected": 3,
                "assessed": len(assessments),
                "resolved": sum(
                    a["status"] != "INSUFFICIENT_EVIDENCE" for a in assessments.values()
                ),
            },
            "candidate_changes": [
                d
                for d in content.get("candidate_changes", [])
                if d["question_src_id"] == qid
            ],
            "annotation_uncertainties": content.get("annotation_uncertainties", {}).get(
                qid, []
            ),
            "rule_version": content.get("rules_manifest", {}).get("error_rule_version"),
            "result_version": content.get("schema_version"),
            "review_requirements": {
                key: sorted(refs)
                for key, refs in reviewing.review_requirements(content, qid).items()
            },
        }
    )


def questions(db, revision, settings, expected_hash=None, cursor=0, limit=25):
    stage = next(
        (
            stage
            for stage in ("final", "sample", "source")
            if stage in revision.stage_fingerprints
        ),
        None,
    )
    if not stage:
        return {"items": [], "next_cursor": None, "result_hash": None, "total": 0}
    content, _ = o.stage_payload(db, revision, stage, settings)
    identity = result_hash(content)
    if (expected_hash and expected_hash != identity) or (cursor and not expected_hash):
        raise w.conflict("VERSION_CONFLICT", "题目分页版本变化，请重新读取")
    selected = content["questions"][cursor : cursor + limit]
    display_content = content
    if stage == "source":
        # Source drafts precede annotation tables. Normalize only this read
        # projection; keep the immutable source payload and its hash unchanged.
        display_content = {
            **content,
            **{
                key: content.get(key, [])
                for key in (
                    "evidences",
                    "skill_question_relations",
                    "error_question_relations",
                    "other_relations",
                )
            },
        }
    return {
        "items": [question_view(display_content, q) for q in selected],
        "assessment_summary": coverage_summary(display_content),
        "result_hash": identity,
        "total": len(content["questions"]),
        "next_cursor": cursor + limit
        if cursor + limit < len(content["questions"])
        else None,
    }
