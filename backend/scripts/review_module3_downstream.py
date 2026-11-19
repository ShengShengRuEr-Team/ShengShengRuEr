"""Run authorized stage-7/8 drafts through admin ASGI API and an independent worker.

Uses the existing isolated acceptance DB. Never connects its worker to the normal
application database, resets a database, or calls a business check/import endpoint.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
WORKSPACE = BACKEND.parents[1]
UPSTREAM = (
    WORKSPACE / "outputs/module3-auto-reference-20261106/real-api-run-6-paddle-native"
)
OUTPUT = WORKSPACE / "outputs/module3-assembly-annotation-20261106"
SOURCE_TASK = "379ec20c-f12a-42c4-97cb-628dd131cb1b"
DATABASE = "m3_auto_real_20261106_124443"


def configure():
    values = dotenv_values(BACKEND / ".env")
    os.environ["DATABASE_URL"] = (
        make_url(values["DATABASE_URL"])
        .set(database=DATABASE)
        .render_as_string(hide_password=False)
    )
    os.environ["APP_ENV"] = "test"
    os.environ["M3_ARTIFACTS_DIR"] = str(OUTPUT / "artifacts")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    OUTPUT.mkdir(exist_ok=True)
    source = UPSTREAM / "artifacts" / SOURCE_TASK
    target = OUTPUT / "artifacts" / SOURCE_TASK
    if not target.exists():
        shutil.copytree(source, target)


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def snapshot():
    from sqlalchemy import text

    from app.db.base import engine

    with engine.connect() as c:
        names = (
            c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            .scalars()
            .all()
        )
        return {
            name: c.execute(text('SELECT count(*) FROM "' + name + '"')).scalar()
            for name in names
            if not name.startswith("processing_")
            and name not in {"alembic_version", "material_sources", "task_materials"}
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["assemble", "sample", "full", "export"])
    parser.add_argument("--source-task")
    parser.add_argument("--scan-task")
    parser.add_argument("--sample-task")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--full-source-task")
    parser.add_argument("--annotation-review", type=Path)
    parser.add_argument("--task")
    args = parser.parse_args()
    configure()
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.main import app
    from app.module3.contracts import file_hash
    from app.services.processing import tasks

    settings = get_settings()
    token, _ = create_access_token(user_id=1, username="admin", settings=settings)
    headers = {"Authorization": "Bearer " + token}
    with TestClient(app) as client:
        if args.mode != "export":
            request = json.loads(
                (UPSTREAM / "request.json").read_text(encoding="utf-8")
            )
            request["stop_after"] = {
                "assemble": "assemble",
                "sample": "annotate_sample",
                "full": "annotate",
            }[args.mode]
            request["reuse_alignment_task_id"] = SOURCE_TASK
            if args.source_task:
                request["reuse_assembly_task_id"] = args.source_task
            if args.scan_task:
                request["reuse_assembly_scan_task_id"] = args.scan_task
            if args.sample_task:
                request["reuse_annotation_task_id"] = args.sample_task
                request["sample_review"] = json.loads(
                    args.review.read_text(encoding="utf-8")
                )
            if args.full_source_task:
                request["reuse_full_annotation_task_id"] = args.full_source_task
                request["annotation_review"] = json.loads(
                    args.annotation_review.read_text(encoding="utf-8")
                )
            before = snapshot()
            response = client.post(
                "/api/v1/admin/processing-tasks", headers=headers, json=request
            )
            if response.status_code != 202:
                dump(OUTPUT / (args.mode + "-create-error.json"), response.json())
                raise RuntimeError("task API rejected request; see controlled evidence")
            task_id = response.json()["data"]["id"]
            directory = OUTPUT / (args.mode + "-" + task_id)
            directory.mkdir(exist_ok=True)
            dump(directory / "request.json", request)
            dump(directory / "registered-task.json", response.json())
            dump(directory / "business-before.json", before)
            with SessionLocal() as db:
                task = tasks.get_task(db, task_id)
                dump(
                    directory / "method-snapshot.json",
                    {"method": task.method, "method_hash": task.method_hash},
                )
            print("TASK", task_id, "MODE", args.mode, flush=True)
            command = [
                str(BACKEND / ".venv-asr/Scripts/python.exe"),
                "-m",
                "app.module3.worker",
                "--once",
            ]
            with (directory / "worker.log").open("w", encoding="utf-8") as log:
                worker = subprocess.run(
                    command,
                    cwd=BACKEND,
                    env=dict(os.environ),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            print("WORKER_EXIT", worker.returncode, flush=True)
        else:
            task_id = args.task
            directory = OUTPUT / ("export-" + task_id)
            directory.mkdir(exist_ok=True)
        response = client.get(
            f"/api/v1/admin/processing-tasks/{task_id}", headers=headers
        )
        dump(directory / "final-task.json", response.json())
        for stage in (
            "extract",
            "reference",
            "align",
            "reuse",
            "assembly_extract",
            "assemble",
            "annotate",
            "annotation_checks",
        ):
            r = client.get(
                f"/api/v1/admin/processing-tasks/{task_id}/stages/{stage}",
                headers=headers,
            )
            dump(directory / (stage + "-api.json"), r.json())
        with SessionLocal() as db:
            task = tasks.get_task(db, task_id)
            draft = tasks.get_draft(db, task)
            if draft:
                dump(directory / "draft.json", draft.payload)
                dump(
                    directory / "draft-identity.json",
                    {"result_hash": draft.result_hash},
                )
            attempts = db.scalars(
                select(LlmAttempt)
                .where(LlmAttempt.task_id == task.id)
                .order_by(LlmAttempt.id)
            ).all()
            dump(
                directory / "llm-attempts.json",
                [
                    {
                        k: getattr(r, k)
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
                    for r in attempts
                ],
            )
            dump(
                directory / "artifacts.json",
                [
                    {"file": str(p.relative_to(OUTPUT)), "sha256": file_hash(p)}
                    for p in (OUTPUT / "artifacts" / str(task.id)).rglob("*.json")
                ],
            )
            print(
                "FINAL",
                task.state,
                task.stage,
                "BATCH",
                task.batch_id,
                "ISSUES",
                [i["issue_code"] for i in task.issues],
                flush=True,
            )
        after = snapshot()
        dump(directory / "business-after.json", after)
        if args.mode != "export":
            dump(
                directory / "boundary-check.json",
                {
                    "business_rows_unchanged": before == after,
                    "no_batch": task.batch_id is None,
                    "stage_9_started": task.stage
                    in {"validate", "persist", "completed"},
                    "api_transport": (
                        "FastAPI TestClient ASGI + real PostgreSQL; "
                        "worker is independent subprocess"
                    ),
                },
            )
        print("EVIDENCE", directory, flush=True)


if __name__ == "__main__":
    main()
