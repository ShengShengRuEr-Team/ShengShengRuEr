"""Run the frozen audio components through alignment and export user review files.

This command has no assembly, annotation, activation or database write step.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import BASE_DIR, get_settings
from app.module3 import audio
from app.module3.contracts import (
    ProcessingError,
    atomic_json,
    controlled_path,
    file_hash,
)
from app.module3.diagnostics import diagnose


def subtitle_time(value):
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    seconds, millis = divmod(value, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def export_review(out, aligned, report):
    rows = aligned["segments"]
    source_reference = report.get("text_source") in {"reference", "answer_reference"}
    report["segment_count"] = len(rows)
    report["unverified_segment_count"] = sum(
        row["alignment_status"] != "aligned" for row in rows
    )
    report["missing_timestamp_count"] = sum(
        row["start_ms"] is None or row["end_ms"] is None for row in rows
    )
    with (out / "sentences.tsv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(
            [
                "segment_id",
                "start_ms",
                "end_ms",
                "alignment_status",
                "text",
                "segment_type",
                "passage_key",
                "question_no",
                "source_pages",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row[k]
                    for k in (
                        "_src_id",
                        "start_ms",
                        "end_ms",
                        "alignment_status",
                        "text",
                    )
                ]
                + [
                    row.get(key, "")
                    for key in (
                        "segment_type",
                        "passage_key",
                        "question_no",
                        "source_pages",
                    )
                ]
            )
    subtitles = []
    for row in rows:
        if row["start_ms"] is not None and row["end_ms"] is not None:
            subtitles.append(
                f"{len(subtitles) + 1}\n{subtitle_time(row['start_ms'])} --> "
                f"{subtitle_time(row['end_ms'])}\n{row['text']}\n"
            )
    (out / "aligned.srt").write_text("\n".join(subtitles), encoding="utf-8")
    report["subtitle_count"] = len(subtitles)
    candidates = (
        [row for row in rows if row.get("segment_type") == "body"]
        if source_reference
        else rows
    )
    count = min(30, len(candidates))
    selected = (
        sorted({round(i * (len(candidates) - 1) / (count - 1)) for i in range(count)})
        if count > 1
        else ([0] if count else [])
    )
    with (out / "boundary-review-template.tsv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(
            [
                "segment_id",
                "auto_start_ms",
                "auto_end_ms",
                "text",
                "body_question_or_instruction",
                "reference_start_ms",
                "reference_end_ms",
                "text_correct",
                "review_note",
            ]
        )
        for index in selected:
            row = candidates[index]
            writer.writerow(
                [
                    row["_src_id"],
                    row["start_ms"],
                    row["end_ms"],
                    row["text"],
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    lines = [
        "# 答案原文逐句对齐：等待用户复核"
        if source_reference
        else "# 转写与对齐结果：等待用户复核",
        "",
        f"句数：{len(rows)}；技术结论：{report['technical_status']}；人工内容及300ms精度结论：BLOCKED。",
        "",
        "本次为固定音频组件实跑；完整管理员API链路验收另行执行。",
        "本次没有执行题目组装、DeepSeek标注、正式业务入库或可见性操作。",
        "",
        "逐句结果见 sentences.tsv；字幕见 aligned.srt；"
        + (
            "原文及对齐输出见 reference.json 与 align.json。"
            if source_reference
            else "原始模型输出见 transcribe.json 与 align.json。"
        ),
        "boundary-review-template.tsv 只填入自动候选，"
        "人工参考边界、文字判断和片段类型保持空白。",
        "原文路径抽取30个正文句；提问另见全部逐句表。抽样不替代整套核听。"
        if source_reference
        else "抽样覆盖全音频，仍须人工区分正文、提问和说明。它不替代整套核听。",
        "",
        "## 对齐异常",
        "",
        "```json",
        json.dumps(aligned.get("issues", []), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 前十个候选片段",
        "",
    ]
    for row in rows[:10]:
        lines.append(
            f"- {row['_src_id']}，{row['start_ms']}—{row['end_ms']}ms，"
            f"{row['alignment_status']}：{row['text']}"
        )
    (out / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, help="Relative storage key in M3_MATERIALS_DIR"
    )
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "technical_status": "BLOCKED",
        "content_status": "BLOCKED",
        "precision_status": "BLOCKED",
        "stage": "preflight",
        "state": "running",
        "stop_after": "align",
        "llm_calls": 0,
        "stages": {},
        "source_key": args.source,
        "expected_source_sha256": args.expected_sha256,
        "method_files_sha256": {
            key: file_hash(BASE_DIR / key)
            for key in (
                "config/module3/processing-profile.json",
                "config/module3/requirements-asr.lock.txt",
                "config/module3/model-artifact-manifest.json",
                "app/module3/audio.py",
                "app/module3/alignment_review.py",
                "app/module3/diagnostics.py",
            )
        },
    }
    try:
        source = controlled_path(settings.m3_path("m3_materials_dir"), args.source)
        if file_hash(source) != args.expected_sha256:
            raise ProcessingError("SOURCE_CHANGED", "音频原件哈希与冻结值不符")
        diagnostic = diagnose("asr", settings)
        atomic_json(out, "diagnostics.json", diagnostic)
        if diagnostic["status"] != "PASS":
            raise ProcessingError("ENVIRONMENT_BLOCKED", ";".join(diagnostic["issues"]))
        for stage in ("normalize", "transcribe", "align"):
            report["stage"] = stage
            begin = time.monotonic()
            print(stage, "started", flush=True)
            if stage == "normalize":
                value = audio.decode(source, out / "normalized.npy", settings)
            elif stage == "transcribe":
                value = audio.transcribe(out / "normalized.npy", settings)
                transcription = value
            else:
                value = audio.align(out / "normalized.npy", transcription, settings)
            atomic_json(out, stage + ".json", value)
            if file_hash(source) != args.expected_sha256:
                raise ProcessingError("SOURCE_CHANGED", "处理过程中音频原件发生变化")
            report["stages"][stage] = {
                "seconds": round(time.monotonic() - begin, 3),
                "sha256": file_hash(out / (stage + ".json")),
            }
            print(stage, "saved", flush=True)
            (out / "progress.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        report["technical_status"] = "PARTIAL" if value.get("issues") else "PASS"
        report["state"] = "awaiting_confirmation"
        export_review(out, value, report)
        return 0 if report["technical_status"] == "PASS" else 2
    except ProcessingError as exc:
        report["issues"] = [exc.issue(report["stage"])]
        report["state"] = "awaiting_confirmation"
        return 2
    except Exception as exc:
        report["issues"] = [
            {
                "issue_code": "PROCESSING_FAILED",
                "stage": report["stage"],
                "error_type": type(exc).__name__,
                "message": str(exc)[:2000],
            }
        ]
        report["state"] = "failed"
        return 2
    finally:
        report["seconds"] = round(time.monotonic() - started, 3)
        report["ended_at"] = datetime.now(UTC).isoformat()
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
