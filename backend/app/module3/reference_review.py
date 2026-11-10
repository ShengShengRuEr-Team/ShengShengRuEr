"""Decode audio and align supplied answer-PDF sentences, without running ASR."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import BASE_DIR, get_settings
from app.module3 import audio, reference
from app.module3.alignment_review import export_review
from app.module3.contracts import (
    ProcessingError,
    atomic_json,
    controlled_path,
    file_hash,
)
from app.module3.diagnostics import diagnose
from app.schemas_processing import ReferenceSegment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "stage": "preflight",
        "state": "running",
        "stop_after": "align",
        "text_source": "answer_reference",
        "technical_status": "BLOCKED",
        "content_status": "BLOCKED",
        "precision_status": "BLOCKED",
        "asr_calls": 0,
        "llm_calls": 0,
        "reference_file_sha256": file_hash(args.reference),
        "stages": {},
        "method_files_sha256": {
            key: file_hash(BASE_DIR / key)
            for key in (
                "app/module3/audio.py",
                "app/module3/reference.py",
                "app/module3/ctc_alignment.py",
                "app/module3/reference_review.py",
                "app/module3/diagnostics.py",
                "app/module3/alignment_review.py",
                "app/schemas_processing.py",
                "config/module3/requirements-asr.lock.txt",
                "config/module3/model-artifact-manifest.json",
            )
        },
    }
    try:
        document = json.loads(args.reference.read_text(encoding="utf-8"))
        rows = [
            ReferenceSegment.model_validate(row).model_dump()
            for row in document["segments"]
        ]
        if not rows or len({row["segment_id"] for row in rows}) != len(rows):
            raise ProcessingError("REFERENCE_TEXT_REQUIRED", "原文为空或句子ID重复")
        source = controlled_path(
            settings.m3_path("m3_materials_dir"), document["audio_storage_key"]
        )
        if file_hash(source) != document["audio_sha256"]:
            raise ProcessingError("SOURCE_CHANGED", "原音哈希不符")
        for key, expected in {
            (r["source_storage_key"], r["source_sha256"]) for r in rows
        }:
            if (
                file_hash(controlled_path(settings.m3_path("m3_materials_dir"), key))
                != expected
            ):
                raise ProcessingError("SOURCE_CHANGED", "答案原件哈希不符")
        diagnostic = diagnose("align", settings)
        atomic_json(out, "diagnostics.json", diagnostic)
        if diagnostic["status"] != "PASS":
            raise ProcessingError("ENVIRONMENT_BLOCKED", ";".join(diagnostic["issues"]))
        atomic_json(out, "reference.json", document)
        for stage in ("normalize", "align"):
            report["stage"] = stage
            (out / "progress.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            begin = time.monotonic()
            print(stage, "started", flush=True)
            value = (
                audio.decode(source, out / "normalized.npy", settings)
                if stage == "normalize"
                else reference.align(out / "normalized.npy", rows, settings)
            )
            atomic_json(out, stage + ".json", value)
            if (
                file_hash(source) != document["audio_sha256"]
                or file_hash(args.reference) != report["reference_file_sha256"]
            ):
                raise ProcessingError("SOURCE_CHANGED", "处理过程中原音或原文改变")
            if any(
                file_hash(BASE_DIR / key) != digest
                for key, digest in report["method_files_sha256"].items()
            ):
                raise ProcessingError("METHOD_CHANGED", "处理过程中实现或模型清单改变")
            report["stages"][stage] = {
                "seconds": round(time.monotonic() - begin, 3),
                "sha256": file_hash(out / (stage + ".json")),
            }
            print(stage, "saved", flush=True)
        report["technical_status"] = "PARTIAL" if value.get("issues") else "PASS"
        report["boundary_method"] = value.get("boundary_method")
        report["automatically_refined_window_count"] = sum(
            bool(row.get("search_attempts")) for row in value["segments"]
        )
        report["state"] = "awaiting_confirmation"
        report["body_sentence_count"] = sum(r["segment_type"] == "body" for r in rows)
        report["question_count"] = sum(r["segment_type"] == "question" for r in rows)
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
                "error_type": type(exc).__name__,
                "message": str(exc)[:2000],
            }
        ]
        report["state"] = "failed"
        return 2
    finally:
        report["seconds"] = round(time.monotonic() - started, 3)
        report["ended_at"] = datetime.now(UTC).isoformat()
        for name in ("report.json", "progress.json"):
            (out / name).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )


if __name__ == "__main__":
    raise SystemExit(main())
