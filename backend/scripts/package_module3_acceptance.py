"""Build a portable, hash-checked handoff after both real routes pass."""

import csv
import hashlib
import json
import re
import shutil
import sys
import unicodedata
import zipfile
from datetime import datetime
from itertools import chain
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parents[1]
ROOT = WORKSPACE / "outputs/module3-independent-acceptance-20261107"
OLD = WORKSPACE / "outputs/module3-assembly-annotation-20261106"
DEST = ROOT / "声声入耳_模块三_独立验收包_20261107"
sys.path.insert(0, str(BACKEND))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def copy(source, relative):
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def norm(text):
    table = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
    return re.sub(
        r"\s+", " ", unicodedata.normalize("NFC", str(text)).translate(table)
    ).strip()


def field_metrics(payload, baseline, paper, keys):
    by_index = {q["question_index"]: q for q in payload["questions"]}
    baseline_q = {q["question_index"]: q for q in baseline["questions"]}
    presentations = {p["question_src_id"]: p for p in payload["presentations"]}
    source_qa = {
        q["question_index"]: q
        for q in load(ROOT / "source-content-review.json")["items"]
    }
    fields = load(ROOT / "quality-protocol.json")["question_fields"]
    rows = []
    for number in range(1, 26):
        q, base = by_index.get(number, {}), baseline_q[number]
        for field in fields:
            if field == "presentation_mapping":
                actual = presentations.get(q.get("_src_id"), {}).get(
                    "option_letter_mapping"
                )
                expected = dict(zip("ABCD", "ABCD", strict=True))
            elif field.startswith("option_"):
                actual = q.get(field)
                expected = paper[number]["options"][field[-1].upper()]
            elif field == "correct_option":
                actual, expected = q.get(field), keys[number]["correct_option"]
                assert expected == source_qa[number]["correct_option"]
            else:
                actual, expected = q.get(field), base[field]
            correct = actual is not None and (
                actual == expected
                if isinstance(expected, dict)
                else norm(actual) == norm(expected)
            )
            rows.append(
                {
                    "question_index": number,
                    "field": field,
                    "correct": correct,
                    "actual": actual,
                    "expected": expected,
                    "basis": "original-page content review; normalized text agreement"
                    if field in {"question_text", "explanation_text"}
                    else "independent original paper/key or source-linked ownership",
                }
            )
    return {
        "correct": sum(r["correct"] for r in rows),
        "expected": 275,
        "rate": sum(r["correct"] for r in rows) / 275,
        "options_correct": sum(
            r["correct"] for r in rows if r["field"].startswith("option_")
        ),
        "options_expected": 100,
        "rows": rows,
        "literal_chinese_character_accuracy": (
            "NOT_CLAIMED; content reviewed; "
            "printed side-labels and ellipsis formatting disclosed"
        ),
    }


def relation_metrics(payload):
    skills = payload.get("skill_question_relations", [])
    others = payload.get("other_relations", [])
    evidences = {e["_src_id"]: e for e in payload.get("evidences", [])}
    segments = {s["_src_id"]: s for s in payload["transcript_segments"]}
    satisfied = 0
    for q in payload["questions"]:
        primary = [
            r
            for r in skills
            if r.get("relation_kind") == "QUESTION_SKILL"
            and r.get("question_src_id") == q["_src_id"]
            and r.get("role") == "PRIMARY"
        ]
        owned = [
            r
            for r in skills
            if r.get("relation_kind") == "QUESTION_SKILL"
            and r.get("question_src_id") == q["_src_id"]
        ]
        supported = bool(owned) and all(
            any(
                r.get("relation_kind") == "SKILL_EVIDENCE"
                and r.get("owner_relation_src_id") == s["_src_id"]
                and r.get("evidence_src_id") in evidences
                for r in skills
            )
            for s in owned
        )
        answers = [
            r
            for r in others
            if r.get("relation_kind") == "ANSWER_EVIDENCE"
            and r.get("question_src_id") == q["_src_id"]
            and r.get("evidence_src_id") in evidences
        ]
        satisfied += int(bool(primary)) + int(supported) + int(bool(answers))
    body_grounded = all(
        e.get("segment_src_ids")
        and all(
            s in segments
            and segments[s]["segment_type"] == "body"
            and segments[s]["passage_src_id"] == e["passage_src_id"]
            for s in e["segment_src_ids"]
        )
        for e in evidences.values()
    )
    return {
        "satisfied": satisfied,
        "expected": 75,
        "rate": satisfied / 75,
        "body_evidence_ownership": (
            "NOT_GENERATED" if not evidences else "PASS" if body_grounded else "FAIL"
        ),
        "evidence_objects": len(evidences),
        "semantic_correctness": "separate review; coverage is not accuracy",
    }


def export_readable(payload, target):
    passages = {p["_src_id"]: p for p in payload["passages"]}
    segments = {s["_src_id"]: s for s in payload["transcript_segments"]}
    evidence = {e["_src_id"]: e for e in payload["evidences"]}
    skills = payload["skill_question_relations"]
    lines = [
        "# 2025年6月四级第1套：25题核对表",
        "",
        "错因是有证据的候选标注，不要求每题都有，不代表学生个人诊断。",
        "",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_suffix(".tsv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(
            [
                "题号",
                "篇章",
                "提问",
                "A",
                "B",
                "C",
                "D",
                "答案",
                "解析",
                "主技能",
                "答案证据",
                "独立验收人",
                "验收结论",
                "复核分钟",
                "备注",
            ]
        )
        for q in payload["questions"]:
            primary = [
                r
                for r in skills
                if r.get("question_src_id") == q["_src_id"]
                and r.get("role") == "PRIMARY"
            ]
            answers = [
                evidence[r["evidence_src_id"]]
                for r in payload["other_relations"]
                if r.get("relation_kind") == "ANSWER_EVIDENCE"
                and r.get("question_src_id") == q["_src_id"]
            ]
            quotes = " | ".join(e["evidence_text"] for e in answers)
            writer.writerow(
                [
                    q["question_index"],
                    passages[q["passage_src_id"]]["passage_index"],
                    q["question_text"],
                    *[q["option_" + k] for k in "abcd"],
                    q["correct_option"],
                    q["explanation_text"],
                    ",".join(s["skill_code"] for s in primary),
                    quotes,
                    "",
                    "",
                    "",
                    "",
                ]
            )
            lines += [
                f"## 第{q['question_index']}题",
                "",
                q["question_text"],
                "",
                *[f"- {k.upper()}. {q['option_' + k]}" for k in "abcd"],
                "",
                f"答案：{q['correct_option']}；主技能："
                + ",".join(s["skill_code"] for s in primary),
                "",
                "解析：" + q["explanation_text"],
                "",
                "答案证据：" + quotes,
                "",
            ]
            for skill in skills:
                if (
                    skill.get("relation_kind") == "QUESTION_SKILL"
                    and skill.get("question_src_id") == q["_src_id"]
                ):
                    lines += [
                        "技能依据："
                        + skill["skill_code"]
                        + " / "
                        + skill["role"]
                        + "；"
                        + skill.get("attributes_json", {}).get("annotation_reason", ""),
                        "",
                    ]
                    for relation in skills:
                        if relation.get("owner_relation_src_id") == skill["_src_id"]:
                            lines += [
                                "技能证据："
                                + evidence[relation["evidence_src_id"]][
                                    "evidence_text"
                                ],
                                "",
                            ]
            errors = payload.get("error_question_relations", [])
            for error in errors:
                if (
                    error.get("relation_kind") == "QUESTION_ERROR_CANDIDATE"
                    and error.get("question_src_id") == q["_src_id"]
                ):
                    lines += [
                        "可选错因候选："
                        + error["error_cause_code"]
                        + "；选项"
                        + str(error.get("option_letter", ""))
                        + "；"
                        + error.get("attributes_json", {}).get("trigger_mechanism", ""),
                        "",
                    ]
                    for relation in errors:
                        if relation.get("owner_relation_src_id") == error["_src_id"]:
                            lines += [
                                "错因证据："
                                + evidence[relation["evidence_src_id"]][
                                    "evidence_text"
                                ],
                                "",
                            ]
            for e in answers:
                for sid in e["segment_src_ids"]:
                    s = segments[sid]
                    lines += [
                        f"- `{sid}`，{s['start_ms']}—{s['end_ms']}ms：{s['text']}"
                    ]
            lines += [""]
    target.write_text("\n".join(lines), encoding="utf-8")
    subtitles = []

    def stamp(ms):
        seconds, millis = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

    with (target.parent / "核听验收空表.tsv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(
            [
                "segment_id",
                "segment_type",
                "text",
                "start_ms",
                "end_ms",
                "reference_start_ms",
                "reference_end_ms",
                "text_correct",
                "reviewer",
                "review_minutes",
                "note",
            ]
        )
        for index, s in enumerate(payload["transcript_segments"], 1):
            writer.writerow(
                [
                    s["_src_id"],
                    s["segment_type"],
                    s["text"],
                    s["start_ms"],
                    s["end_ms"],
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            subtitles += [
                str(index),
                stamp(s["start_ms"]) + " --> " + stamp(s["end_ms"]),
                s["text"],
                "",
            ]
    (target.parent / "aligned.srt").write_text("\n".join(subtitles), encoding="utf-8")


def main():
    from app.module3.contracts import result_hash
    from app.module3.source_assembly import paper_answer_key, paper_options

    state = load(ROOT / "scan-state.json")
    scan = load(ROOT / "r15-full-pipeline/latest.json")
    text_run = load(ROOT / "text-recheck/latest.json")
    assert scan["status"] == text_run["status"] == "PASS"
    baseline = load(OLD / "questions-and-annotations.json")
    extracted = load(
        WORKSPACE
        / "outputs/module3-auto-reference-20261106"
        / "real-api-run-6-paddle-native/extract-api.json"
    )["result"]["pages"]
    paper, keys = paper_options(extracted), paper_answer_key(extracted)
    assert len(paper) == len(keys) == 25
    scan_raw_dir = ROOT / ("assemble-" + state["raw_assemble"])
    raw = load(scan_raw_dir / "draft.json")
    final = load(Path(scan["directory"]) / "draft.json")
    text_final = load(Path(text_run["directory"]) / "draft.json")
    initial_text = load(OLD / "full-9f1fc805-c93f-4f9a-bd51-685a20da48c2/draft.json")
    metrics = {
        "text_initial": field_metrics(initial_text, baseline, paper, keys),
        "text_final": field_metrics(text_final, baseline, paper, keys),
        "scan_initial": field_metrics(raw, baseline, paper, keys),
        "scan_final": field_metrics(final, baseline, paper, keys),
    }
    assert metrics["text_final"]["correct"] == metrics["scan_final"]["correct"] == 275
    semantic_scan_dir = ROOT / (
        state.get("final_phase", "full")
        + "-"
        + state.get("final_annotation", state["full"])
    )
    semantic = load(semantic_scan_dir / "semantic-review.json")
    scan_initial_semantic = load(
        ROOT / ("full-" + state["full"]) / "semantic-review.json"
    )
    assert (
        semantic["result_hash"] == result_hash(final)
        and semantic["decision"] == "approved"
    )
    quality = {
        "protocol": load(ROOT / "quality-protocol.json"),
        "field_metrics": metrics,
        "required_relations": {
            "text_initial": relation_metrics(initial_text),
            "text_final": relation_metrics(text_final),
            "scan_assembly_initial": relation_metrics(raw),
            "scan_first_complete_annotation": relation_metrics(
                load(ROOT / ("full-" + state["full"]) / "draft.json")
            ),
            "scan_final": relation_metrics(final),
        },
        "text_semantic_review": {
            "first_complete_v5": {"approved": 20, "expected": 25},
            "final": {"approved": 25, "expected": 25},
            "model_regenerated_questions": [12, 14, 16, 20, 23],
            "direct_manual_annotation_field_edits": 0,
            "early_samples": [
                {
                    "task_id": p.parent.name.removeprefix("sample-"),
                    "approved": sum(
                        i["decision"] == "approved" for i in load(p)["items"]
                    ),
                    "expected": len(load(p)["items"]),
                    "decision": load(p)["decision"],
                }
                for p in sorted(OLD.glob("sample-*/semantic-review.json"))
            ],
        },
        "scan_semantic_review": semantic,
        "scan_first_complete_semantic_review": scan_initial_semantic,
        "scan_annotation_repair_questions": [
            i["question_src_id"]
            for i in scan_initial_semantic["items"]
            if i["decision"] != "approved"
        ],
        "scan_direct_manual_annotation_edits": 0,
        "scan_failed_full_attempt": {
            "task_id": state.get("failed_full"),
            "reason": (
                "Q25 optional error used disconnected body IDs; "
                "rejected after 3 bounded attempts"
            ),
            "accepted_candidate_checkpoints": 24,
            "business_import_started": False,
        },
        "source_corrections": {
            "text_direct_manual_questions": 0,
            "scan_direct_manual_questions": 4,
            "scan_direct_manual_question_rate": 4 / 25,
            "scan_direct_manual_fields": 5,
            "changes": load(
                ROOT / ("correct-assembly-" + state["assemble"]) / "request.json"
            )["changes"],
            "initial_auto_draft_preserved": True,
        },
        "automatic_stage_timings": [
            {"phase": p.parent.name, **load(p)} for p in ROOT.glob("*-*/timing.json")
        ],
        "historical_text_alignment_seconds": load(
            WORKSPACE
            / "outputs/module3-auto-reference-20261106"
            / "real-api-run-6-paddle-native/acceptance.json"
        )["seconds"],
        "review_timings": [load(p) for p in ROOT.glob("*review-session*.json")],
        "historical_human_review_minutes": (
            "NOT_RECORDED; user approval retained; no fabricated duration"
        ),
        "scope": (
            "one fixed-layout real paper; "
            "Codex review is not blind independent human benchmarking"
        ),
    }
    quality["pending_import_worker_timing"] = load(
        Path(scan["directory"]) / "worker-timing.json"
    )
    quality[
        "scan_automatic_worker_seconds_including_retries_excluding_duplicate_test"
    ] = (
        sum(t["elapsed_seconds"] for t in quality["automatic_stage_timings"])
        + quality["pending_import_worker_timing"]["elapsed_seconds"]
    )
    start = min(
        datetime.fromisoformat(t["start"]) for t in quality["automatic_stage_timings"]
    )
    end = datetime.fromisoformat(
        load(Path(scan["directory"]) / "report.json")["ended_at"]
    )
    quality["scan_total_elapsed_seconds_including_review_and_gaps"] = (
        end - start
    ).total_seconds()
    dump(ROOT / "quality-report.json", quality)
    rows = [
        "# 模块三质量报告（2026-11-07）",
        "",
        "材料：2025年6月大学英语四级第1套听力，8篇、25题。统计协议在本轮扫描端到端前冻结，关键字段11项×25题=275项，缺失计错。",
        "",
        "| 路径与阶段 | 正确字段/应核对 | 字段正确率 | 选项准确项/100 |",
        "|---|---:|---:|---:|",
    ]
    for label, name in [
        ("文本首次完整初稿", "text_initial"),
        ("文本最终", "text_final"),
        ("扫描组装自动初稿", "scan_initial"),
        ("扫描最终", "scan_final"),
    ]:
        m = metrics[name]
        rows.append(
            f"| {label} | {m['correct']}/275 | {m['rate']:.2%} | "
            f"{m['options_correct']}/100 |"
        )
    rows += [
        "",
        "扫描首套完整25题的标注内容复核："
        + str(sum(i["decision"] == "approved" for i in scan_initial_semantic["items"]))
        + "/25通过；最终25/25通过。"
        "首套完整结果复用了已审查的前5题样本，剩余题新请求生成；不作为盲审准确率基准。",
        "",
        "早期5题开发样本分别有3/5、4/5及后续5/5通过；v4整套在第15题的连续证据契约失败后停止。各运行的原始返回与复核均在text-history保留，这些开发修订不混入冻结v5首套25题的分母。",
        "",
        "本轮扫描首次整套尝试在第25题失败：可选错因的两个句子不连续，3次返回均被拦下，保存24题检查点及失败输出，未进入入库。新增具体对象和上一版候选的重试反馈并通过回归验证，随后新的整套请求通过25题结构检查；该新整套未再次触发结构重试，不把其通过归因于未实际触发的反馈。失败/重试耗时及费用全部计入，未手改模型输出。",
        "",
        "字段正确率是原件内容核对口径：仅统一引号与空白，不忽略句号。中文解析逐题核对内容含义，不宣称逐字符OCR准确率；个别‘解→’侧栏字样、Q14省略号格式差异已披露。独立逐字符复核可填写随包表格。",
        "",
        "文本首次完整v5标注经内容复核20/25通过，Q12、14、16、20、23通过真实模型重生成后25/25通过；早期不完整/失败试跑另列历史，未把修正成品当初稿。扫描首次组装尚未标注，关系为0/75；扫描首次完整标注和最终结果的必交关系均为75/75，语义结论另报。完整标注前已通过接口修正5处源文句号，不能把其字段分数称为未经修正的原始OCR分数。正文证据归属、逐字引用及时间由结构检查与内容复核分别验证。",
        "",
        "扫描直接纠错为5个选项末尾句号，涉及Q4、5、13、17，共4/25=16%；通过纠错接口留痕，自动初稿不变。文本源字段直接手工修改0题；文本标注5/25=20%为内容复核触发的模型重生成，非逐题重录。候选错因属于可选扩展，无依据时为空。",
        "",
        "## 实测时间",
        "",
        "| 阶段 | 秒 |",
        "|---|---:|",
    ]
    for t in quality["automatic_stage_timings"]:
        rows.append(f"| {t['phase']} | {t['elapsed_seconds']:.3f} |")
    rows.append(
        "| 待审入库worker | "
        f"{quality['pending_import_worker_timing']['elapsed_seconds']:.3f} |"
    )
    scan_worker_total = quality[
        "scan_automatic_worker_seconds_including_retries_excluding_duplicate_test"
    ]
    rows.append(
        f"| 扫描自动worker合计（含修订重试；不含幂等测试） | {scan_worker_total:.3f} |"
    )
    rows.append(
        "| 历史文本原件提取至align（当时实测） | "
        f"{quality['historical_text_alignment_seconds']:.3f} |"
    )
    rows += [
        "",
        "以上为实际独立worker墙钟耗时（含启动/诊断），阶段复用在对应请求和产物链中明确记录，不能将阶段简单相加当作无复用连续性能基准。历史文本全链路当时未记录完整精确墙钟，标为NOT_RECORDED；本轮文本复验复用了已有对齐和已审标注，不声称重新OCR/对齐。",
        "",
    ]
    for t in quality["review_timings"]:
        rows.append("- 本轮Codex复核实测记录：" + json.dumps(t, ensure_ascii=False))
    rows += [
        "",
        "历史真人核听/复核耗时未记录（NOT_RECORDED）；保留用户原有音频审批为PASS_BY_USER_CONFIRMATION，不编造≤300ms逐句人工测量。随包空白核听表供独立验收人记录，不冒充已完成记录。",
        "",
        "详细逐字段差异、标注语义判定、计时和来源见quality-report.json及evidence目录。",
    ]
    (ROOT / "质量统计报告.md").write_text("\n".join(rows), encoding="utf-8")
    DEST.mkdir(exist_ok=True)
    dictionary = load(BACKEND / "config/module3/dictionary-schema.json")
    legend = [
        "# 当前任务冻结词典速查",
        "",
        "S07/S13为诊断用途，不能据题目内容直接作为主要技能。"
        "错因为有依据的题目级候选，不等同个人诊断。",
        "",
    ]
    for table in dictionary["tables"]:
        if table["name"] not in {"skill", "error_cause"}:
            continue
        is_skill = table["name"] == "skill"
        legend += ["## " + ("技能" if is_skill else "错因"), ""]
        for row in table["rows"]:
            if row.get("skill_level" if is_skill else "cause_level") != 3:
                continue
            code = row["skill_code" if is_skill else "error_cause_code"]
            name = row["skill_name" if is_skill else "cause_name"]
            legend += [
                f"- **{code} {name}**：{row.get('definition', '')} "
                + "范围："
                + row.get("usage_scope", "题目级候选")
                + "；状态："
                + row.get("status", ""),
                "",
            ]
    (DEST / "词典速查.md").write_text("\n".join(legend), encoding="utf-8")
    for p in (ROOT / "materials").iterdir():
        copy(p, Path("materials") / p.name)
    copy(
        WORKSPACE / "outputs/module3-alignment-review-20261105/scan-generation.json",
        "materials/scan-generation.json",
    )
    for name in (
        "quality-protocol.json",
        "quality-report.json",
        "质量统计报告.md",
        "source-content-review.json",
        "source-review-session.json",
        "scan-reference-comparison.json",
        "scan-boundary-comparison.json",
        "source-correction-audit.json",
        "annotation-final-checks.json",
        "scan-initial-field-checks.json",
        "scan-corrected-field-checks.json",
        "scan-state.json",
        "pytest-api.xml",
        "pytest-api.log",
        "pytest-api.exit",
        "checkpoint-tests.xml",
        "feedback-tests.xml",
        "processing-tests.log",
        "processing-tests.exit",
        "ocr-tests.log",
        "ocr-tests.exit",
        "final-integrity.json",
        "budget-final.json",
    ):
        copy(ROOT / name, Path("evidence") / name)
    for p in ROOT.glob("*review-session*.json"):
        copy(p, Path("evidence/review-timings") / p.name)
    copy(
        ROOT / "before/app/module3/annotation_checks.py",
        "evidence/method-changes/annotation_checks-before-feedback.py",
    )
    for name in (
        "questions-and-annotations.json",
        "semantic-review.json",
        "source-checks.json",
        "all-real-llm-attempts.json",
        "development-runs.json",
        "quality-summary.json",
    ):
        copy(OLD / name, Path("evidence/text-history") / name)
    copy(
        OLD / "full-9f1fc805-c93f-4f9a-bd51-685a20da48c2/semantic-review.json",
        "evidence/text-history/first-complete-v5-semantic-review.json",
    )
    for folder in OLD.iterdir():
        if folder.is_dir() and folder.name.startswith(("sample-", "full-")):
            for p in folder.iterdir():
                if p.suffix in {".json", ".log"}:
                    copy(p, Path("evidence/text-history") / folder.name / p.name)
    for prefix, report, data in (("text", text_run, text_final), ("scan", scan, final)):
        folder = Path(report["directory"])
        for p in folder.iterdir():
            if p.suffix in {".json", ".log"}:
                copy(p, Path("evidence") / prefix / "full-pipeline" / p.name)
        dump(DEST / "results" / prefix / "final.json", data)
        export_readable(data, DEST / "results" / prefix / "逐题核对表.md")
    for folder in ROOT.iterdir():
        if folder.is_dir() and folder.name.startswith(
            ("align-", "assemble-", "correct-assembly-", "sample-", "full-", "repair-")
        ):
            for p in folder.iterdir():
                if p.suffix in {".json", ".log"}:
                    copy(p, Path("evidence/scan-stages") / folder.name / p.name)
        if folder.is_dir() and folder.name.startswith("paper-probe"):
            for p in folder.rglob("*.json"):
                copy(
                    p,
                    Path("evidence/ocr-development")
                    / folder.name
                    / p.relative_to(folder),
                )
    for p in ROOT.glob("paper-probe*.log"):
        copy(p, Path("evidence/ocr-development") / p.name)
    # Small trace files and source page images only; acoustic matrices/models excluded.
    for task_id in sorted({v for v in state.values() if isinstance(v, str)}):
        for p in (ROOT / "artifacts" / task_id).rglob("*"):
            if p.is_file() and p.suffix in {".json", ".log", ".png"}:
                copy(
                    p,
                    Path("evidence/scan-artifacts")
                    / task_id
                    / p.relative_to(ROOT / "artifacts" / task_id),
                )
    source_paths = chain(
        BACKEND.iterdir(),
        *(
            (BACKEND / name).rglob("*")
            for name in ("app", "alembic", "config", "scripts", "tests")
        ),
    )
    for p in source_paths:
        relative = p.relative_to(BACKEND)
        if any(
            part.startswith(".") or part in {"__pycache__", "var", "node_modules"}
            for part in relative.parts
        ):
            continue
        if p.is_file() and p.suffix in {
            ".py",
            ".json",
            ".toml",
            ".ini",
            ".txt",
            ".md",
            ".mako",
        }:
            copy(p, Path("source/backend") / relative)
    copy(BACKEND / ".env.example", "source/backend/.env.example")
    for p in WORKSPACE.glob("模块三*.md"):
        copy(p, Path("requirements") / p.name)
    for p in (BACKEND.parent / "docs").rglob("*.md"):
        if "module3" in str(p).lower() or "module-3" in str(p).lower():
            copy(p, Path("source/docs") / p.relative_to(BACKEND.parent / "docs"))
    copy(ROOT / "独立验收说明.md", "README_先读.md")
    copy(ROOT / "verify_handoff.py", "verify_handoff.py")
    for name in ("核听验收空表.tsv", "独立验收清单.md", "接口验收请求.json"):
        copy(ROOT / name, Path("acceptance") / name)
    # Check exported bytes against actual secrets without saving their values.
    from dotenv import dotenv_values

    private_values = dotenv_values(BACKEND / ".env")
    secrets = [
        str(v).encode()
        for k, v in private_values.items()
        if v
        and any(t in k.upper() for t in ("SECRET", "API_KEY", "PASSWORD"))
        and len(str(v)) >= 12
    ]
    if private_values.get("DATABASE_URL"):
        secrets.append(private_values["DATABASE_URL"].encode())
    files = sorted(
        p for p in DEST.rglob("*") if p.is_file() and p.name != "manifest.json"
    )
    assert all(
        not any(secret in p.read_bytes() for secret in secrets) for p in files
    ), "Secret detected; refuse package"
    assert not any(
        re.search(
            rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
            p.read_bytes(),
        )
        for p in files
        if p.suffix.lower() in {".json", ".log", ".md", ".py", ".txt"}
    ), "JWT detected; refuse package"
    manifest = {
        "paper": "CET4 2025-06 set1 listening, 25 questions, 8 passages",
        "files": [
            {
                "path": p.relative_to(DEST).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": sha(p),
            }
            for p in files
        ],
        "secret_scan": "PASS",
        "excluded": [
            ".env",
            "credentials",
            "JWT",
            "model binaries",
            "virtual environments",
            "database credentials",
            "acoustic matrices",
        ],
    }
    dump(DEST / "manifest.json", manifest)
    archive = DEST.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DEST.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(DEST.parent))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in manifest["files"]:
            assert (
                hashlib.sha256(z.read(DEST.name + "/" + item["path"])).hexdigest()
                == item["sha256"]
            )
    dump(
        ROOT / "package-verification.json",
        {
            "status": "PASS",
            "archive": str(archive),
            "sha256": sha(archive),
            "files": len(files) + 1,
            "bytes": archive.stat().st_size,
            "crc": "PASS",
            "every_archived_sha256": "PASS",
            "secret_scan": "PASS",
        },
    )
    print("PACKAGE_PASS", str(archive), archive.stat().st_size)


if __name__ == "__main__":
    main()
