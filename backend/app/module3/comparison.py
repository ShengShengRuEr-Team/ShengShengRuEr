"""P6 label agreement: fixed denominators and independent metric-unit validity."""

import json
from collections import Counter

from pydantic import ValidationError

from app.module3.annotation_checks import check_evidence
from app.module3.annotation_identity import question_input_hash
from app.module3.contracts import ProcessingError, fingerprint
from app.module3.distractor_contract import DistractorAssessment, SkillV7
from app.services.processing.validation import load_dictionary

VERSION = "m3.comparison.v1"
PROVIDERS = ("deepseek", "bailian")


def unit(state, labels=None, reason=None, **extra):
    return {"state": state, "labels": labels, "reason": reason, **extra}


def checked(operation):
    try:
        return unit("valid", operation())
    except (ProcessingError, ValidationError, ValueError, TypeError, KeyError) as error:
        code = getattr(error, "code", type(error).__name__)
        return unit(
            "invalid",
            reason=f"{code}: {str(error)[:600]}",
        )


def dictionaries():
    tables = {t["name"]: t["rows"] for t in load_dictionary()["tables"]}
    return (
        {
            r["skill_code"]
            for r in tables["skill"]
            if r["skill_level"] == 3
            and r["status"] == "启用"
            and r.get("usage_scope") == "题目标注"
        },
        {
            r["error_cause_code"]
            for r in tables["error_cause"]
            if r["cause_level"] == 3 and r["status"] == "启用"
        },
    )


def evaluate_question(source, question, record, codes):
    wrong = [letter for letter in "ABCD" if letter != question["correct_option"]]

    def unavailable(state, reason):
        return {
            "primary": unit(state, reason=reason),
            "skills": unit(state, reason=reason),
            "errors": {letter: unit(state, reason=reason) for letter in wrong},
        }

    if not record or record.get("execution_state") == "not_executed":
        return unavailable("not_executed", (record or {}).get("reason") or "未执行")
    if record.get("execution_state") != "executed":
        return unavailable("invalid", "缺少可信执行状态")
    if record.get("origin_type") != "AI":
        return unavailable("invalid", "人工或混合结果不能参与模型原始相同率")
    if record.get("complete_record") is not True:
        return unavailable("invalid", record.get("reason") or "缺少完整模型生成记录")
    if record.get("question_input_hash") != question_input_hash(source, question):
        return unavailable("invalid", "冻结题目、正文或基准映射依赖不一致")
    expected_dictionary = source.get("rules_manifest", {}).get("dictionary_sha256")
    if (
        not expected_dictionary
        or record.get("dictionary_sha256") != expected_dictionary
    ):
        return unavailable("invalid", "冻结词典依赖不一致")
    raw = record.get("raw")
    if not isinstance(raw, dict) or raw.get("question_src_id") != question["_src_id"]:
        return unavailable(
            "invalid", record.get("reason") or "JSON或关键题目身份不可信"
        )
    skills = raw.get("skills")

    def identity():
        if (
            not isinstance(skills, list)
            or not skills
            or any(
                not isinstance(s, dict) or s.get("role") not in {"PRIMARY", "AUXILIARY"}
                for s in skills
            )
        ):
            raise ValueError("技能角色或身份不完整")
        primary = [s for s in skills if s["role"] == "PRIMARY"]
        if len(primary) != 1:
            raise ValueError("主要技能必须恰好一个，不能以集合掩盖重复")
        return primary[0]

    def validate_skill(value):
        result = SkillV7.model_validate(value)
        if result.skill_code not in codes[0]:
            raise ValueError("技能编码未启用或不适用")
        check_evidence(source, question, result, "skills")
        return [result.skill_code, result.role]

    def primary():
        return validate_skill(identity())[0]

    def complete_skills():
        identity()
        labels = [validate_skill(s) for s in skills]
        if len({v[0] for v in labels}) != len(labels):
            raise ValueError("技能编码或关系非法重复")
        return sorted(labels)

    result = {
        "primary": checked(primary),
        "skills": checked(complete_skills),
        "errors": {},
    }
    assessments = raw.get("distractor_assessments")
    trusted = isinstance(assessments, list) and all(
        isinstance(a, dict) and a.get("option_letter") in wrong for a in assessments
    )
    for letter in wrong:
        matches = (
            [a for a in assessments if a["option_letter"] == letter] if trusted else []
        )
        if not trusted or len(matches) != 1:
            result["errors"][letter] = unit(
                "invalid", reason="选项身份不可信、缺少评估或同项评估重复"
            )
            continue

        def validate_option(value=matches[0]):
            assessment = DistractorAssessment.model_validate(value)
            labels = [c.error_cause_code for c in assessment.candidates]
            if len(set(labels)) != len(labels) or any(
                code not in codes[1] for code in labels
            ):
                raise ValueError("错因编码非法、停用或同项重复")
            for evidence in assessment.comparison_evidence:
                check_evidence(source, question, evidence, "comparison_evidence")
            for candidate in assessment.candidates:
                for evidence in candidate.evidence:
                    check_evidence(source, question, evidence, "error_evidence")
            return sorted(labels)

        value = checked(validate_option)
        value["assessment_status"] = matches[0].get("status")
        if (
            value["state"] == "valid"
            and value["assessment_status"] == "INSUFFICIENT_EVIDENCE"
        ):
            value.update(
                state="insufficient",
                labels=None,
                reason="；".join(matches[0]["unresolved_points"]),
            )
        result["errors"][letter] = value
    return result


def same(left, right):
    return (
        left["state"] == right["state"] == "valid" and left["labels"] == right["labels"]
    )


def metric(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "ratio": numerator / denominator if denominator else None,
        "display": f"{numerator}/{denominator} ({numerator / denominator:.2%})"
        if denominator
        else "不适用",
    }


def compare(source, records, *, metadata=None):
    """Records are AI-only, hash-bound observations, never edited final snapshots."""
    questions = sorted(source["questions"], key=lambda q: q["question_index"])
    if (
        len(questions) != 25
        or [q["question_index"] for q in questions] != list(range(1, 26))
        or len({q["_src_id"] for q in questions}) != 25
        or any(q.get("correct_option") not in set("ABCD") for q in questions)
    ):
        raise ProcessingError(
            "COMPARISON_SAMPLE_INVALID", "P6固定25个唯一题目和75个错误基准选项"
        )
    unknown = set(records) - set(PROVIDERS)
    if unknown:
        raise ProcessingError(
            "COMPARISON_PROVIDER_INVALID", "对比仅支持已确认的两家模型"
        )
    codes = dictionaries()
    rows = []
    options = []
    for question in questions:
        qid = question["_src_id"]
        values = {
            p: evaluate_question(source, question, records.get(p, {}).get(qid), codes)
            for p in PROVIDERS
        }
        row = {
            "question_src_id": qid,
            "question_index": question["question_index"],
            "correct_option": question["correct_option"],
            "models": values,
            "primary_same": same(
                values["deepseek"]["primary"], values["bailian"]["primary"]
            ),
            "skills_same": same(
                values["deepseek"]["skills"], values["bailian"]["skills"]
            ),
        }
        rows.append(row)
        for letter in "ABCD":
            if letter == question["correct_option"]:
                continue
            a, b = (values[p]["errors"][letter] for p in PROVIDERS)
            options.append(
                {
                    "question_src_id": qid,
                    "question_index": question["question_index"],
                    "option_letter": letter,
                    "models": {"deepseek": a, "bailian": b},
                    "same": same(a, b),
                    "nonempty_denominator": any(
                        v["state"] == "valid" and bool(v["labels"]) for v in [a, b]
                    ),
                    "assessment_status_same": a["state"] == b["state"] == "valid"
                    and a.get("assessment_status") == b.get("assessment_status"),
                }
            )
    nonempty = [r for r in options if r["nonempty_denominator"]]
    coverage = {
        p: {
            "primary": dict(Counter(r["models"][p]["primary"]["state"] for r in rows)),
            "skills": dict(Counter(r["models"][p]["skills"]["state"] for r in rows)),
            "errors": dict(Counter(r["models"][p]["state"] for r in options)),
        }
        for p in PROVIDERS
    }
    execution_count = sum(
        record.get("execution_state") == "executed"
        for provider in PROVIDERS
        for record in records.get(provider, {}).values()
    )
    return {
        "schema_version": VERSION,
        "execution_status": "not_executed"
        if not execution_count
        else "complete"
        if execution_count == 50
        else "partial",
        "source_hash": fingerprint(source),
        "metadata": metadata or {},
        "metrics": {
            "primary": metric(sum(r["primary_same"] for r in rows), 25),
            "skills": metric(sum(r["skills_same"] for r in rows), 25),
            "errors": metric(sum(r["same"] for r in options), 75),
            "nonempty_errors": metric(sum(r["same"] for r in nonempty), len(nonempty)),
            "assessment_status": metric(
                sum(r["assessment_status_same"] for r in options), 75
            ),
        },
        "coverage": coverage,
        "questions": rows,
        "options": options,
        "limitations": [
            "相同率不是准确率，也不是学生评分；不据单套试卷推断全面等效。",
            "未执行、失败、依据不足及非法结果不缩小25/75固定分母，不作为合法空集合。",
            "人工语义意见单独记录，报告不使候选自动入库或开放。",
        ],
        "human_disagreement_review": [],
    }


def render_markdown(report):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    def label(value):
        if value["state"] != "valid":
            return value["state"] + "：" + cell(value.get("reason") or "")
        return cell(value["labels"] if value["labels"] else "合法空集合")

    meta = report["metadata"]
    lines = [
        "# 双模型标签相同率报告",
        "",
        f"报告契约：{VERSION}；固定样本：25题 / 75个错误基准选项。",
        "",
        "执行状态："
        + cell(report["execution_status"])
        + "。未执行时的0/25、0/75只是覆盖计数，不是模型实测相同率。",
        "",
        "核听记录：" + cell(meta.get("listening_review", {})),
        "",
        "| 指标 | 相同分子 / 分母及比例 |",
        "| --- | --- |",
    ]
    names = {
        "primary": "主要技能",
        "skills": "完整技能",
        "errors": "错因",
        "nonempty_errors": "非空错因",
        "assessment_status": "干扰项状态",
    }
    lines += [f"| {names[k]} | {v['display']} |" for k, v in report["metrics"].items()]
    lines += [
        "",
        "## 执行与费用",
        "",
        "```json",
        json.dumps(meta.get("execution", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 逐题技能",
        "",
        "| 题号 | DeepSeek主要技能 | 千问主要技能 | 主要相同 | "
        "DeepSeek完整技能 | 千问完整技能 | 完整相同 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["questions"]:
        a, b = (row["models"][p] for p in PROVIDERS)
        cells = [
            row["question_index"],
            label(a["primary"]),
            label(b["primary"]),
            row["primary_same"],
            label(a["skills"]),
            label(b["skills"]),
            row["skills_same"],
        ]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    lines += [
        "",
        "## 逐错误基准选项",
        "",
        "| 题号 / 基准选项 | DeepSeek错因及状态 | 千问错因及状态 | "
        "标签相同 | 状态相同 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["options"]:
        a, b = (row["models"][p] for p in PROVIDERS)
        cells = [
            f"{row['question_index']} / {row['option_letter']}",
            f"{label(a)} · {a.get('assessment_status', '未生成')}",
            f"{label(b)} · {b.get('assessment_status', '未生成')}",
            row["same"],
            row["assessment_status_same"],
        ]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    lines += [
        "",
        "## 结论限制",
        "",
        *["- " + v for v in report["limitations"]],
        "",
        "人工分歧复核意见："
        + (
            cell(report["human_disagreement_review"])
            if report["human_disagreement_review"]
            else "尚未记录；不修改模型相同率。"
        ),
        "",
    ]
    return "\n".join(lines)
