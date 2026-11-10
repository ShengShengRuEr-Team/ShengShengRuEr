"""Standalone worker extension: ordinary jobs use the unchanged project worker."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from console_config import BACKEND

sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
import draft_generation
from alignment_revision import process_revision, revision_record
from app.db.base import SessionLocal
from app.module3 import worker

original_process = worker.process


def dispatch(task_id, token, settings):
    with SessionLocal() as db:
        is_revision = revision_record(db, task_id) is not None or bool(
            worker.tasks.get_task(db, task_id).method.get("console_alignment_revision")
        )
    return (
        process_revision(task_id, token, settings, worker)
        if is_revision
        else draft_generation.dispatch(
            task_id, token, settings, worker, original_process
        )
    )


worker.process = dispatch
if __name__ == "__main__":
    raise SystemExit(worker.main())
