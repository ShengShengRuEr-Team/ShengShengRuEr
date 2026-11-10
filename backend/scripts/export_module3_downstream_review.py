"""Export final stage-8 review evidence without business checks or writes."""

import csv
import json
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

import review_module3_downstream as runner

runner.configure()
sys.path.insert(0, str(runner.BACKEND))

from sqlalchemy import create_engine, select, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import SessionLocal, engine  # noqa: E402
from app.db.models_processing import LlmAttempt, ProcessingArtifact  # noqa: E402
from app.module3 import reuse  # noqa: E402
from app.module3.contracts import file_hash, fingerprint  # noqa: E402
from app.services.processing import tasks  # noqa: E402
from app.services.processing.validation import load_dictionary  # noqa: E402

FINAL_TASK = "10e9c1d5-33e2-4570-a86a-7aaa8264144c"
SAMPLE_TASK = "b82b749d-7c88-4101-814d-819f0a8e1fdf"
ASSEMBLY_TASK = "15c21d62-4a0f-4b7c-9997-ee2d75f8286a"
OUTPUT = runner.OUTPUT


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def stamp(ms):
    return f"{ms // 60000:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def main():
    directory = OUTPUT / ("full-" + FINAL_TASK)
    payload = load(directory / "draft.json")
    tables = {t["name"]: t for t in load_dictionary()["tables"]}
    skills = {r["skill_code"]: r["skill_name"] for r in tables["skill"]["rows"]}
    segments = {s["_src_id"]: s for s in payload["transcript_segments"]}
    evidences = {e["_src_id"]: e for e in payload["evidences"]}
    selected_attempts = []
    accepted = {}
    for path in (OUTPUT / "artifacts" / FINAL_TASK / "annotate").glob("*.json"):
        value = load(path)
        accepted[value["question_src_id"]] = value
        selected_attempts.append(value["call"]["attempt_id"])
    assert len(accepted) == 25 and len(set(selected_attempts)) == 25
    run_key = fingerprint({"audio": payload["audio"]["file_hash"]})
    with SessionLocal() as db:
        task = tasks.get_task(db, FINAL_TASK)
        assert task.state == "awaiting_confirmation" and task.stage == "annotate"
        assert task.batch_id is None
        changed = [
            key
            for key, expected in task.method["implementation_sha256"].items()
            if file_hash(runner.BACKEND / key) != expected
        ]
        assert not changed and task.method_hash == fingerprint(task.method)
        _, provenance = reuse.load(db, task, get_settings())
        dump(OUTPUT / "upstream-reuse-final.json", provenance)
        dump(
            OUTPUT / "integrity-final.json",
            {
                "task_id": FINAL_TASK,
                "method_hash": task.method_hash,
                "method_hash_matches": True,
                "changed_method_files": changed,
                "state": task.state,
                "stage": task.stage,
                "batch_id": task.batch_id,
                "all_material_hashes_verified": True,
            },
        )
        attempts = db.scalars(
            select(LlmAttempt)
            .where(LlmAttempt.run_key == run_key)
            .order_by(LlmAttempt.id)
        ).all()
        fields = (
            "id",
            "task_id",
            "run_key",
            "phase",
            "request_hash",
            "request_payload",
            "response_payload",
            "response_model",
            "input_tokens",
            "output_tokens",
            "reserved_usd",
            "charged_usd",
            "billing_status",
            "status",
            "error_code",
            "created_at",
        )
        dump(
            OUTPUT / "all-real-llm-attempts.json",
            [
                {
                    **{key: getattr(row, key) for key in fields},
                    "prompt_version": tasks.get_task(db, row.task_id).method[
                        "prompt_version"
                    ],
                }
                for row in attempts
            ],
        )
        attempts_by_id = {r.id: r for r in attempts}
        assert set(selected_attempts) <= set(attempts_by_id)
        task_ids = {r.task_id for r in attempts} | {task.id}
        artifacts = db.scalars(
            select(ProcessingArtifact).where(ProcessingArtifact.task_id.in_(task_ids))
        ).all()
        assert not any(
            r.stage in {"validate", "persist", "review", "completed"} for r in artifacts
        )
        rejection_records = []
        for artifact in artifacts:
            if artifact.stage == "annotation_rejected":
                path = OUTPUT / "artifacts" / artifact.storage_key
                assert file_hash(path) == artifact.artifact_hash
                value = load(path)
                rejection_records.append({"task_id": str(artifact.task_id), **value})
        dump(OUTPUT / "contract-rejections.json", rejection_records)

        def billed(rows):
            return sum(
                (
                    r.charged_usd if r.charged_usd is not None else r.reserved_usd
                    for r in rows
                ),
                Decimal(0),
            )

        sample_rows = [r for r in attempts if r.phase == "sample"]
        stats = {
            "calls": len(attempts),
            "sample_calls_including_revisions": len(sample_rows),
            "sample_commitment_usd": str(billed(sample_rows)),
            "run_commitment_usd": str(billed(attempts)),
            "selected_25_response_cost_estimate_usd": str(
                billed([attempts_by_id[i] for i in selected_attempts])
            ),
            "input_tokens": sum(r.input_tokens or 0 for r in attempts),
            "output_tokens": sum(r.output_tokens or 0 for r in attempts),
            "response_models": sorted({r.response_model for r in attempts}),
            "http_or_transport_failures": sum(
                r.status != "succeeded" for r in attempts
            ),
            "bounded_contract_retry_count": len(rejection_records),
            "review_repair_calls": sum(
                "semantic_review_constraints"
                in json.loads(r.request_payload["messages"][1]["content"])
                for r in attempts
            ),
            "final_review_worker_new_calls": sum(
                r.task_id == task.id for r in attempts
            ),
            "account_debit_verified": False,
            "pricing_policy": (
                "frozen peak cache-miss estimate; unknown costs retain reservation"
            ),
        }
    ledgers = []
    with engine.connect() as connection:
        names = (
            connection.execute(
                text(
                    "SELECT datname FROM pg_database "
                    "WHERE NOT datistemplate AND datallowconn"
                )
            )
            .scalars()
            .all()
        )
    for name in names:
        other = create_engine(engine.url.set(database=name))
        try:
            with other.connect() as connection:
                if not connection.execute(
                    text("SELECT to_regclass('public.processing_llm_attempts')")
                ).scalar():
                    continue
                row = connection.execute(
                    text("""
                    SELECT count(*),coalesce(sum(charged_usd),0),
                    coalesce(sum(reserved_usd) FILTER (WHERE charged_usd IS NULL),0)
                    FROM processing_llm_attempts
                """)
                ).one()
                ledgers.append(
                    {
                        "database": name,
                        "attempts": row[0],
                        "estimated_usd": str(row[1]),
                        "unknown_reserved_usd": str(row[2]),
                    }
                )
        finally:
            other.dispose()
    cumulative = sum(
        (
            Decimal(r["estimated_usd"]) + Decimal(r["unknown_reserved_usd"])
            for r in ledgers
        ),
        Decimal(0),
    )
    audit = {
        "observed_at": datetime.now(UTC).isoformat(),
        "run": stats,
        "stage_commitment_usd": str(cumulative),
        "ledgers": ledgers,
        "limits_usd": {"sample": "0.50", "run": "2.00", "stage": "5.00"},
        "all_within_limits": Decimal(stats["sample_commitment_usd"]) <= Decimal(".5")
        and Decimal(stats["run_commitment_usd"]) <= 2
        and cumulative <= 5,
        "legacy_unknown_test_reservations_included_conservatively": True,
    }
    assert audit["all_within_limits"]
    dump(OUTPUT / "budget-audit.json", audit)
    with (OUTPUT / "usage-costs.tsv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.writer(stream, dialect="excel-tab")
        writer.writerow(
            [
                "attempt_id",
                "task_id",
                "phase",
                "model",
                "input_tokens",
                "output_tokens",
                "estimated_usd",
                "reserved_usd",
                "status",
            ]
        )
        for row in attempts:
            writer.writerow(
                [
                    row.id,
                    row.task_id,
                    row.phase,
                    row.response_model,
                    row.input_tokens,
                    row.output_tokens,
                    row.charged_usd,
                    row.reserved_usd,
                    row.status,
                ]
            )
    for name, source in (
        ("questions-and-annotations.json", directory / "draft.json"),
        ("questions.tsv", directory / "questions.tsv"),
        ("skills-evidence.tsv", directory / "skills-evidence.tsv"),
        ("source-checks.json", directory / "source-checks.json"),
        ("annotation-checks.json", directory / "annotation-recheck.json"),
        ("semantic-review.json", directory / "semantic-review.json"),
    ):
        shutil.copy2(source, OUTPUT / name)
    primary = [
        r
        for r in payload["skill_question_relations"]
        if r["relation_kind"] == "QUESTION_SKILL"
    ]
    errors = [
        r
        for r in payload["error_question_relations"]
        if r["relation_kind"] == "QUESTION_ERROR_CANDIDATE"
    ]
    dump(
        OUTPUT / "quality-summary.json",
        {
            "step_7": "PASS",
            "step_8": "PASS_WITHIN_AUTHORIZED_DRAFT_SCOPE",
            "questions": len(payload["questions"]),
            "passages": len(payload["passages"]),
            "body_sentences": sum(
                s["segment_type"] == "body" for s in segments.values()
            ),
            "question_sentences": sum(
                s["segment_type"] == "question" for s in segments.values()
            ),
            "primary_skills": len(primary),
            "skill_counts": dict(Counter(r["skill_code"] for r in primary)),
            "answer_evidences": len(payload["other_relations"]),
            "evidences": len(evidences),
            "candidate_errors": len(errors),
            "semantic_review_items": 25,
            "stage_9_started": False,
            "batch_id": None,
            "unresolved_step_7_8_issues": [],
            "limitations": [
                "single Codex content review, not blind human accuracy benchmark",
                "upstream time consistency, "
                "not independent absolute millisecond accuracy",
                "no new business batch, activation or student visibility",
            ],
        },
    )
    lines = [
        "# 全部25题：原件题目与关联标注草稿",
        "",
        "来源/结构检查通过；25题已完成本轮逐题内容复核。实际标注由DeepSeek生成，"
        "时间由程序取得。这里是第8步冻结处理草稿，不是已入库/发布题库。",
        "",
    ]
    for question in payload["questions"]:
        qid = question["_src_id"]
        lines.extend(
            [
                f"## 第{question['question_index']}题 · {question['passage_src_id']}",
                "",
                question["question_text"],
                "",
            ]
        )
        for letter in "ABCD":
            lines.append(f"- **{letter}** {question['option_' + letter.lower()]}")
        lines.extend(
            [
                "",
                f"**标准答案：{question['correct_option']}**",
                "",
                "**原件解析**：" + question["explanation_text"].replace("\n", ""),
                "",
            ]
        )
        for relation in primary:
            if relation["question_src_id"] == qid:
                lines.append(
                    f"**主要技能：{relation['skill_code']} "
                    f"{skills[relation['skill_code']]}**"
                )
                lines.extend(["", relation["attributes_json"]["annotation_reason"], ""])
        for relation in payload["other_relations"]:
            if relation["question_src_id"] != qid:
                continue
            evidence = evidences[relation["evidence_src_id"]]
            lines.extend(
                [
                    "**答案证据**：`"
                    + ", ".join(evidence["segment_src_ids"])
                    + "`；"
                    + stamp(evidence["start_ms"])
                    + "—"
                    + stamp(evidence["end_ms"]),
                    "",
                    "> " + evidence["evidence_text"],
                    "",
                    relation["attributes_json"]["support_note"],
                    "",
                ]
            )
        for relation in errors:
            if relation["question_src_id"] == qid:
                lines.extend(
                    [
                        f"**候选错因**：`{relation['error_cause_code']}` / "
                        f"选项{relation['option_letter']}",
                        "",
                        relation["attributes_json"]["trigger_mechanism"],
                        "",
                    ]
                )
        pages = sorted({r["locator"]["page"] for r in question["source_refs"]})
        lines.extend(
            [
                f"来源页：{pages}（各材料ID、SHA-256和框位置见JSON）；"
                "标准答案与原卷第8页KEYS独立一致。",
                "",
            ]
        )
    (OUTPUT / "questions-review.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "final_task": FINAL_TASK,
                "run": stats,
                "stage_commitment_usd": str(cumulative),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
