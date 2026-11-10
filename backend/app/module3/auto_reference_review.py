"""Raw paper+answer+audio -> source sentences -> acoustic locator -> alignment.

No pre-entered reference text, old transcript, old times, annotation or DB writes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import BASE_DIR, get_settings
from app.module3 import audio, auto_reference, reference
from app.module3.alignment_review import export_review
from app.module3.contracts import ProcessingError, atomic_json, file_hash
from app.module3.document_reference import paper_structure, parse_groups, split_groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text-only", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "state": "running",
        "stage": "extract",
        "text_source": "reference",
        "asr_calls": 0,
        "llm_calls": 0,
        "business_db_writes": 0,
        "manual_reference_files_used": False,
        "historical_transcript_used": False,
        "technical_status": "BLOCKED",
        "content_status": "BLOCKED",
        "precision_status": "BLOCKED",
        "method_files_sha256": {
            str(p.relative_to(BASE_DIR)): file_hash(p)
            for p in sorted((BASE_DIR / "app/module3").glob("*.py"))
        },
    }
    begin = time.monotonic()
    method_files = dict(report["method_files_sha256"])
    method_files["config/module3/model-artifact-manifest.json"] = file_hash(
        BASE_DIR / "config/module3/model-artifact-manifest.json"
    )
    report["method_files_sha256"] = method_files
    try:
        materials = []
        for number, (kind, path) in enumerate(
            [
                ("paper_text", args.paper),
                ("answer_explanation", args.answer),
                ("audio", args.audio),
            ],
            1,
        ):
            materials.append(
                {
                    "material_id": number,
                    "source_kind": kind,
                    "path": str(path.resolve()),
                    "storage_key": path.name,
                    "sha256": file_hash(path),
                }
            )
        report["source_materials"] = materials
        documents = out / "documents"
        documents.mkdir()
        manifest = {
            "prepare_reference": True,
            "reference_only": True,
            "model_root": str(settings.m3_path("m3_model_root")),
            "nltk_data": str(settings.nltk_data),
            "files": [m for m in materials if m["source_kind"] != "audio"],
        }
        atomic_json(documents, "input-manifest.json", manifest)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.upper().startswith(("DEEPSEEK", "PG", "JWT"))
            and k.upper() != "DATABASE_URL"
        }
        env.update(
            PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True",
            HF_HUB_OFFLINE="1",
            PYTHONIOENCODING="utf-8",
            OMP_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
        )
        command = [
            str(Path(settings.m3_ocr_python).resolve()),
            "-X",
            "utf8",
            "-m",
            "app.module3.ocr_worker",
            "--manifest",
            str(documents / "input-manifest.json"),
            "--output",
            str(documents),
        ]
        with (out / "document-process.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command,
                cwd=BASE_DIR,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=3600,
            )
        if completed.returncode:
            raise ProcessingError("OCR_PROCESS_FAILED", "文档提取失败，见受控日志")
        extracted = json.loads(
            (documents / "extracted.json").read_text(encoding="utf-8")
        )
        structure = paper_structure(extracted["pages"])
        groups = parse_groups(extracted["pages"], structure, materials)
        rows = split_groups(groups, settings.nltk_data)
        atomic_json(
            out,
            "source-text.json",
            {"structure": structure, "groups": groups, "segments": rows},
        )
        print(f"source text prepared: {len(rows)} sentences", flush=True)
        if args.text_only:
            report.update(
                state="awaiting_confirmation",
                stage="reference",
                technical_status="PASS",
            )
            return 0
        report["stage"] = "normalize"
        meta = audio.decode(args.audio.resolve(), out / "normalized.npy", settings)
        atomic_json(out, "normalize.json", meta)
        report["stage"] = "reference"
        prepared = auto_reference.prepare(
            extracted, materials, out / "normalized.npy", settings, out
        )
        atomic_json(out, "reference.json", prepared)
        report["stage"] = "align"
        aligned = reference.align(
            out / "normalized.npy", prepared["segments"], settings
        )
        atomic_json(out, "align.json", aligned)
        report.update(
            state="awaiting_confirmation",
            technical_status="PARTIAL" if aligned.get("issues") else "PASS",
        )
        report["stop_after"] = "align"
        export_review(out, aligned, report)
        return 2 if aligned.get("issues") else 0
    except ProcessingError as exc:
        report.update(
            state="awaiting_confirmation", issues=[exc.issue(report["stage"])]
        )
        return 2
    finally:
        changed = [
            name
            for name, digest in method_files.items()
            if file_hash(BASE_DIR / name) != digest
        ]
        changed_sources = [
            m["storage_key"]
            for m in report.get("source_materials", [])
            if file_hash(Path(m["path"])) != m["sha256"]
        ]
        if changed or changed_sources:
            report.update(
                technical_status="BLOCKED",
                content_status="BLOCKED",
                precision_status="BLOCKED",
                changed_method_files=changed,
                changed_sources=changed_sources,
            )
        report["seconds"] = round(time.monotonic() - begin, 3)
        report["ended_at"] = datetime.now(UTC).isoformat()
        atomic_json(out, "report.json", report)


if __name__ == "__main__":
    raise SystemExit(main())
