"""Run R15 image-only paper phases through the admin API and real worker."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parents[1]
OUTPUT = WORKSPACE / "outputs/module3-independent-acceptance-20261107"
DATABASE = "m3_r15_scan_20261107_01"
PAPER_CODE = "CET4_2025_06_1_R15_SCAN"
sys.path.insert(0, str(BACKEND))


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def configure():
    values = dotenv_values(BACKEND / ".env")
    os.environ.update(
        DATABASE_URL=make_url(values["DATABASE_URL"])
        .set(database=DATABASE)
        .render_as_string(hide_password=False),
        APP_ENV="test",
        PYTHONIOENCODING="utf-8",
        M3_ARTIFACTS_DIR=str(OUTPUT / "artifacts"),
        M3_MATERIALS_DIR=str(OUTPUT / "materials"),
        AUDIO_STORAGE_DIR=str(OUTPUT / "audio"),
    )
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "init",
            "align",
            "assemble",
            "correct-assembly",
            "sample",
            "full",
            "repair",
            "export",
        ),
    )
    parser.add_argument("--review", type=Path)
    parser.add_argument("--task")
    args = parser.parse_args()
    values = configure()
    OUTPUT.mkdir(exist_ok=True)
    if args.phase == "init":
        admin_engine = create_engine(
            make_url(values["DATABASE_URL"]).set(database="postgres"),
            isolation_level="AUTOCOMMIT",
        )
        with admin_engine.connect() as c:
            if not c.execute(
                text("SELECT 1 FROM pg_database WHERE datname=:name"),
                {"name": DATABASE},
            ).scalar():
                c.execute(text(f'CREATE DATABASE "{DATABASE}"'))
        admin_engine.dispose()
        from alembic import command
        from alembic.config import Config

        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        config.set_main_option(
            "sqlalchemy.url", os.environ["DATABASE_URL"].replace("%", "%%")
        )
        command.upgrade(config, "head")
        from app.seed import seed

        seed()
        material_dir = OUTPUT / "materials"
        material_dir.mkdir(exist_ok=True)
        original = WORKSPACE / "outputs/module3-implementation-20261104/materials"
        for path in original.iterdir():
            if path.suffix.lower() in {".pdf", ".m4a"}:
                shutil.copy2(path, material_dir / path.name)
        shutil.copy2(
            WORKSPACE
            / "outputs/module3-alignment-review-20261105/derived-scan-300dpi.pdf",
            material_dir / "CET4_2025_06_1_paper_scan_300dpi.pdf",
        )

    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt, ProcessingArtifact
    from app.main import app
    from app.module3.contracts import file_hash
    from app.services.processing import tasks

    settings = get_settings()
    token, _ = create_access_token(user_id=1, username="admin", settings=settings)
    headers = {"Authorization": "Bearer " + token}
    state_file = OUTPUT / "scan-state.json"
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {}
    )
    with TestClient(app) as client:

        def call(method, path, body=None, expected=200):
            response = client.request(method, path, json=body, headers=headers)
            if response.status_code != expected:
                dump(OUTPUT / (args.phase + "-api-error.json"), response.json())
                raise RuntimeError("API rejected request; controlled evidence saved")
            return response.json()["data"]

        if args.phase == "init":
            defs = [
                ("paper_text", "CET4_2025年6月_第1套_真题.pdf"),
                ("paper_scan", "CET4_2025_06_1_paper_scan_300dpi.pdf"),
                ("answer_explanation", "CET4_2025年6月_第1套_答案解析.pdf"),
                ("audio", "CET4_2025_06_1_听力.m4a"),
            ]
            rows = []
            for kind, name in defs:
                body = {
                    "exam_paper_code": PAPER_CODE,
                    "source_kind": kind,
                    "storage_key": name,
                    "expected_sha256": file_hash(OUTPUT / "materials" / name),
                    "source_locator": (
                        "R15; 2025-06 CET4 set1; original or image-only derivative"
                    ),
                }
                if kind == "paper_scan":
                    generation = json.loads(
                        (
                            WORKSPACE
                            / "outputs/module3-alignment-review-20261105"
                            / "scan-generation.json"
                        ).read_text()
                    )
                    body.update(
                        derived_from_material_id=rows[0]["id"], generation=generation
                    )
                rows.append(call("POST", "/api/v1/admin/materials", body, expected=201))
            state["materials"] = rows
            dump(state_file, state)
            print("INITIALIZED", DATABASE, flush=True)
            return
        if args.phase == "export":
            task_id = args.task
        elif args.phase == "correct-assembly":
            source_id = state["assemble"]
            source = call("GET", "/api/v1/admin/processing-tasks/" + source_id)
            result = call(
                "GET", "/api/v1/admin/processing-tasks/" + source_id + "/result"
            )["result"]
            changes = []
            for number, letter in ((4, "b"), (5, "d"), (13, "b"), (13, "d"), (17, "c")):
                question = next(
                    q for q in result["questions"] if q["question_index"] == number
                )
                field = "option_" + letter
                assert not question[field].endswith("."), "Unexpected source state"
                changes.append(
                    {
                        "entity": "questions",
                        "src_id": question["_src_id"],
                        "field": field,
                        "value": question[field] + ".",
                    }
                )
            request = {
                "expected_result_hash": source["result_hash"],
                "reason": (
                    "Five final periods verified against paper images; words unchanged"
                ),
                "source_refs": [
                    "paper_scan SHA256 "
                    "6739b7b5e7d4739210ec1fe737c11b9078baedda0d095cd68bdfe6d694d780f2"
                    " pages 1-2; Q4B Q5D Q13B Q13D Q17C"
                ],
                "changes": changes,
            }
            created = call(
                "POST",
                "/api/v1/admin/processing-tasks/" + source_id + "/corrections",
                request,
                expected=202,
            )
            task_id = created["id"]
            state["raw_assemble"], state["assemble"] = source_id, task_id
            state[args.phase] = task_id
            dump(state_file, state)
            directory = OUTPUT / (args.phase + "-" + task_id)
            directory.mkdir(exist_ok=True)
            dump(directory / "request.json", request)
            dump(directory / "registered-task.json", created)
            started = time.monotonic()
            start_at = datetime.now(UTC).isoformat()
            with (directory / "worker.log").open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    [
                        str(BACKEND / ".venv-asr/Scripts/python.exe"),
                        "-m",
                        "app.module3.worker",
                        "--once",
                    ],
                    cwd=BACKEND,
                    env=dict(os.environ),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            dump(
                directory / "timing.json",
                {
                    "start": start_at,
                    "end": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": time.monotonic() - started,
                    "worker_exit": process.returncode,
                },
            )
        else:
            material_ids = [
                m["id"] for m in state["materials"] if m["source_kind"] != "paper_text"
            ]
            request = {
                "exam_paper": {
                    "exam_paper_code": PAPER_CODE,
                    "exam_level": "CET4",
                    "exam_year": 2025,
                    "exam_month": 6,
                    "paper_set": 1,
                },
                "material_ids": material_ids,
                "document_mode": "scan",
                "text_source": "reference",
                "reference_preparation": "auto",
                "stop_after": {
                    "align": "align",
                    "assemble": "assemble",
                    "sample": "annotate_sample",
                    "full": "annotate",
                    "repair": "annotate",
                }[args.phase],
                "material_pages": {
                    str(state["materials"][1]["id"]): [1, 2],
                    str(state["materials"][2]["id"]): list(range(2, 10)),
                },
                "dictionary_snapshot_sha256": file_hash(
                    BACKEND / "config/module3/dictionary-schema.json"
                ),
                "profile_version": "M3-WIN64-1.1.0",
            }
            if args.phase != "align":
                request["reuse_alignment_task_id"] = state["align"]
            if args.phase in {"sample", "full", "repair"}:
                request["reuse_assembly_task_id"] = state["assemble"]
            if args.phase in {"full", "repair"}:
                request["reuse_annotation_task_id"] = state["sample"]
                request["sample_review"] = json.loads(
                    (
                        OUTPUT / ("sample-" + state["sample"]) / "semantic-review.json"
                    ).read_text(encoding="utf-8")
                )
            if args.phase == "repair":
                request["reuse_full_annotation_task_id"] = state["full"]
                request["annotation_review"] = json.loads(
                    args.review.read_text(encoding="utf-8")
                )
            created = call(
                "POST", "/api/v1/admin/processing-tasks", request, expected=202
            )
            task_id = created["id"]
            state[args.phase] = task_id
            dump(state_file, state)
            directory = OUTPUT / (args.phase + "-" + task_id)
            directory.mkdir(exist_ok=True)
            dump(directory / "request.json", request)
            dump(directory / "registered-task.json", created)
            print("TASK", task_id, "PHASE", args.phase, flush=True)
            started = time.monotonic()
            start_at = datetime.now(UTC).isoformat()
            with (directory / "worker.log").open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    [
                        str(BACKEND / ".venv-asr/Scripts/python.exe"),
                        "-m",
                        "app.module3.worker",
                        "--once",
                    ],
                    cwd=BACKEND,
                    env=dict(os.environ),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            dump(
                directory / "timing.json",
                {
                    "start": start_at,
                    "end": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": time.monotonic() - started,
                    "worker_exit": process.returncode,
                },
            )
        directory = OUTPUT / (args.phase + "-" + task_id)
        directory.mkdir(exist_ok=True)
        task_data = call("GET", "/api/v1/admin/processing-tasks/" + task_id)
        dump(directory / "final-task.json", task_data)
        with SessionLocal() as db:
            task = tasks.get_task(db, task_id)
            dump(
                directory / "method-snapshot.json",
                {"method": task.method, "method_hash": task.method_hash},
            )
            draft = tasks.get_draft(db, task)
            if draft:
                dump(directory / "draft.json", draft.payload)
            auto_draft = tasks.get_draft(db, task, "auto_draft")
            if auto_draft:
                dump(directory / "auto_draft.json", auto_draft.payload)
            artifacts = db.scalars(
                select(ProcessingArtifact)
                .where(ProcessingArtifact.task_id == task.id)
                .order_by(ProcessingArtifact.id)
            ).all()
            dump(
                directory / "artifacts.json",
                [
                    {
                        "stage": a.stage,
                        "storage_key": a.storage_key,
                        "sha256": a.artifact_hash,
                        "source_artifact_id": a.source_artifact_id,
                    }
                    for a in artifacts
                ],
            )
            for stage in {a.stage for a in artifacts}:
                latest = [a for a in artifacts if a.stage == stage][-1]
                source = OUTPUT / "artifacts" / latest.storage_key
                assert file_hash(source) == latest.artifact_hash
                shutil.copy2(source, directory / (stage + ".json"))
            attempts = db.scalars(
                select(LlmAttempt)
                .where(LlmAttempt.task_id == task.id)
                .order_by(LlmAttempt.id)
            ).all()
            dump(
                directory / "llm-attempts.json",
                [
                    {
                        k: getattr(a, k)
                        for k in (
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
                    }
                    for a in attempts
                ],
            )
        print(
            "FINAL",
            task_data["state"],
            task_data["stage"],
            "ISSUES",
            [i["issue_code"] for i in task_data["issues"]],
            flush=True,
        )


if __name__ == "__main__":
    main()
