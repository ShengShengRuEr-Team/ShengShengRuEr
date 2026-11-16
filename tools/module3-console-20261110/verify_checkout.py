"""Fresh-checkout console checks: disposable DB, synthetic sources, no paid calls."""

from __future__ import annotations

import copy
import hashlib
import importlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from console_config import BACKEND, ROOT

sys.path.insert(0, str(BACKEND))
from dotenv import dotenv_values
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url


def synthetic_payload():
    """Original test text only; this is not an exam or a semantic gold label."""
    return {
        "audio": {"file_hash": "0" * 64},
        "assembly_audit": {"draft_first": True},
        "questions": [
            {
                "_src_id": f"q:{n}",
                "question_index": n,
                "passage_src_id": "p:1",
                "question_text": f"Synthetic question {n}: when does the shop open?",
                "option_a": "At nine.",
                "option_b": "At ten.",
                "option_c": "At eleven.",
                "option_d": "At twelve.",
                "correct_option": "A",
                "explanation_text": "合成验证材料：店铺九点开门。",
            }
            for n in range(1, 8)
        ],
        "transcript_segments": [
            {
                "_src_id": "s:1",
                "passage_src_id": "p:1",
                "segment_type": "body",
                "segment_index": 1,
                "text": "The shop opens at nine.",
                "start_ms": 100,
                "end_ms": 2000,
                "alignment_status": "aligned",
            }
        ],
        "skill_question_relations": [],
        "evidences": [],
        "error_question_relations": [],
        "other_relations": [],
    }


def main():
    os.chdir(BACKEND)
    base = make_url(
        os.getenv("DATABASE_URL") or dotenv_values(BACKEND / ".env")["DATABASE_URL"]
    )
    name = "m3_console_checkout_" + uuid4().hex
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    checks = []
    created = False
    sleeper = None

    def check(value, label):
        if not value:
            raise AssertionError(label)
        checks.append(label)

    try:
        # Only the exact database created below is eligible for final cleanup.
        with admin.connect() as db:
            db.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        with tempfile.TemporaryDirectory(prefix="m3-console-checkout-") as temporary:
            os.environ.update(
                DATABASE_URL=base.render_as_string(hide_password=False),
                M3_CONSOLE_DATABASE=name,
                M3_CONSOLE_DATA_DIR=temporary,
                M3_CONSOLE_EXAMPLES_DIR=str(Path(temporary) / "no-examples"),
                M3_CONSOLE_WORKER="0",
                M3_CONSOLE_MONITOR="0",
                DEEPSEEK_API_KEY="",
            )
            from fastapi.testclient import TestClient

            ui = importlib.import_module("server")
            import draft_generation as dg
            from alignment_revision import edit_reference
            from app.core.errors import AppError
            from app.db import models_processing as m
            from app.db.base import SessionLocal, engine
            from app.module3.contracts import ProcessingError

            check(
                make_url(ui.settings.database_url).database == name,
                "database bootstrap stays isolated",
            )
            check(
                ui.settings.m3_path("m3_materials_dir")
                == Path(temporary) / "materials",
                "media bootstrap stays isolated",
            )
            ui.initialize_database()
            with TestClient(ui.app) as client:
                check(
                    client.get("/console-api/workflows").status_code == 401,
                    "anonymous denied",
                )
                headers = {}
                for role in ("admin", "student"):
                    response = client.post(
                        "/api/v1/login",
                        json={"username": role, "password": role + "123"},
                    )
                    check(response.status_code == 200, role + " login")
                    headers[role] = {
                        "Authorization": "Bearer " + response.json()["data"]["token"]
                    }
                auth = headers["admin"]
                check(
                    client.get(
                        "/console-api/config", headers=headers["student"]
                    ).status_code
                    == 403,
                    "student denied",
                )
                check(
                    client.get("/console-api/config", headers=auth).json()["data"][
                        "examples"
                    ]
                    == [],
                    "fresh checkout has no broken example links",
                )
                check(
                    client.get("/console-api/examples/text", headers=auth).status_code
                    == 404,
                    "missing optional example returns 404",
                )
                for resource in (
                    "/",
                    "/app.js",
                    "/app.css",
                    "/progress.js",
                    "/alignment.js",
                    "/draft.js",
                ):
                    check(client.get(resource).status_code == 200, "static " + resource)
                definition = {
                    "title": "合成验证任务",
                    "exam_paper": {
                        "exam_paper_code": "CONSOLE_CHECKOUT",
                        "exam_level": "CET4",
                        "exam_year": 2025,
                        "exam_month": 6,
                        "paper_set": 1,
                    },
                    "document_mode": "text",
                }
                response = client.post(
                    "/console-api/workflows", json=definition, headers=auth
                )
                check(response.status_code == 201, "workflow created")
                wid = response.json()["data"]["id"]
                endpoint = f"/console-api/workflows/{wid}"
                check(
                    client.put(
                        endpoint + "/files/paper?name=../bad.pdf",
                        content=b"test",
                        headers=auth,
                    ).status_code
                    == 422,
                    "path traversal rejected",
                )
                check(
                    client.put(
                        endpoint + "/files/paper?name=empty.pdf",
                        content=b"",
                        headers=auth,
                    ).status_code
                    == 422,
                    "empty upload rejected",
                )
                audio = io.BytesIO()
                with wave.open(audio, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\0\0" * 160)
                for kind, filename, content in (
                    ("paper", "paper.pdf", b"%PDF-1.4\nsynthetic paper"),
                    ("answer", "answer.pdf", b"%PDF-1.4\nsynthetic answers"),
                    ("audio", "audio.wav", audio.getvalue()),
                ):
                    response = client.put(
                        endpoint + f"/files/{kind}?name={filename}",
                        content=content,
                        headers=auth,
                    )
                    check(
                        response.status_code == 200
                        and response.json()["data"]["sha256"]
                        == hashlib.sha256(content).hexdigest(),
                        kind + " streaming hash",
                    )
                response = client.post(endpoint + "/start", headers=auth)
                check(
                    response.status_code == 200, "materials registered and task queued"
                )
                task_id = response.json()["data"]["task_id"]
                check(
                    len(response.json()["data"]["progress"]["stages"]) == 5,
                    "five phase progress rows",
                )
                check(
                    client.post(
                        endpoint + "/stop", json={"task_id": str(uuid4())}, headers=auth
                    ).status_code
                    == 409,
                    "stale stop rejected",
                )
                response = client.post(
                    endpoint + "/stop", json={"task_id": task_id}, headers=auth
                )
                check(
                    response.status_code == 200 and response.json()["data"]["stopped"],
                    "queued stop persisted",
                )
                check(
                    client.post(
                        endpoint + "/continue", json={"task_id": task_id}, headers=auth
                    ).status_code
                    == 409,
                    "stopped workflow cannot continue",
                )
                response = client.post(
                    endpoint + "/retry",
                    json={"reason": "SYNTHETIC lifecycle test"},
                    headers=auth,
                )
                check(response.status_code == 200, "explicit retry creates child")
                task_id = response.json()["data"]["task_id"]
                if os.name == "nt":
                    child_code = "import time;time.sleep(120)"
                    parent_code = (
                        "import subprocess,sys,time;"
                        "subprocess.Popen([sys.executable,'-c',"
                        + repr(child_code)
                        + ",'app.module3.worker'],"
                        "creationflags=subprocess.CREATE_NO_WINDOW);time.sleep(120)"
                    )
                    sleeper = subprocess.Popen(
                        [sys.executable, "-c", parent_code, "app.module3.worker"],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    from console_runtime import AdoptedWorker, process_tree

                    time.sleep(1)
                    descendants = []
                    for pid in process_tree(sleeper.pid) - {sleeper.pid}:
                        try:
                            descendants.append(AdoptedWorker(pid))
                        except RuntimeError:
                            pass  # A Windows console host has no worker command marker.
                    check(bool(descendants), "real owned descendant exists")
                    ui.worker = AdoptedWorker(sleeper.pid)
                    with SessionLocal() as db:
                        task = db.get(m.ProcessingTask, task_id)
                        task.state = "running"
                        task.worker_id = socket.gethostname() + ":" + str(sleeper.pid)
                        task.lease_token = uuid4()
                        task.expires_at = ui.tasks.utcnow() + timedelta(seconds=120)
                        task.heartbeat_at = ui.tasks.utcnow()
                        db.commit()
                    response = client.post(
                        endpoint + "/stop", json={"task_id": task_id}, headers=auth
                    )
                    check(response.status_code == 200, "running stop accepted")
                    sleeper.wait(timeout=10)
                    check(
                        all(process.poll() is not None for process in descendants),
                        "owned descendants actually stopped",
                    )
                    with SessionLocal() as db:
                        task = db.get(m.ProcessingTask, task_id)
                        check(
                            task.lease_token is None and task.expires_at is None,
                            "lease fenced after stop",
                        )

                payload = synthetic_payload()
                events, calls = [], []
                failures = {"q:3"}

                def fake_request(_task, _run, _phase, _prompt, data, _settings):
                    qid = data["question"]["_src_id"]
                    calls.append(qid)
                    if qid in failures:
                        raise ProcessingError("LLM_TRANSPORT", "SYNTHETIC failure")
                    return {
                        "question_src_id": qid,
                        "skills": [
                            {
                                "skill_code": "S21",
                                "role": "PRIMARY",
                                "rationale": "合成测试：直接事实提取。",
                                "evidence_segment_src_ids": ["s:1"],
                                "quote": "The shop opens at nine.",
                            }
                        ],
                        "answer_evidence": [
                            {
                                "evidence_segment_src_ids": ["s:1"],
                                "quote": "The shop opens at nine.",
                                "support_note": "合成测试：九点对应A。",
                            }
                        ],
                        "candidate_errors": [],
                        "language_items": [],
                        "genre_candidate": None,
                    }, {"synthetic": True}

                def generate(value):
                    with patch(
                        "app.module3.llm.request_json", side_effect=fake_request
                    ):
                        dg.annotate_questions(
                            SimpleNamespace(
                                id=uuid4(),
                                parent_task_id=None,
                                request={"stop_after": "annotate_sample"},
                            ),
                            uuid4(),
                            value,
                            ui.settings,
                            lambda *args, **_kw: events.append(args[2]),
                        )

                generate(payload)
                check(
                    calls == [f"q:{n}" for n in range(1, 6)],
                    "sample makes requests for original first five only",
                )
                annotated = {
                    r.get("question_src_id")
                    for r in payload["skill_question_relations"]
                    if r.get("role") == "PRIMARY"
                }
                check(
                    annotated == {"q:1", "q:2", "q:4", "q:5"},
                    "single candidate failure preserves subsequent annotations",
                )
                check(
                    dg.pending_report(payload, "annotate_sample")[0]["question_src_id"]
                    == "q:3",
                    "failed question listed in sample pending",
                )
                partial = synthetic_payload()
                partial["questions"][4]["correct_option"] = None
                calls.clear()
                generate(partial)
                check(
                    "q:5" not in calls and len(partial["questions"]) == 7,
                    "missing answer skips request and preserves numbering",
                )
                empty = synthetic_payload()
                review = ui.semantic_review(
                    {"items": []},
                    empty,
                    5,
                    "0" * 64,
                    SimpleNamespace(username="SYNTHETIC"),
                )
                check(
                    review["decision"] == "deferred",
                    "no generated candidates cannot fabricate approval",
                )

                # A completed sample is retained until explicit review.
                failures.clear()
                calls.clear()
                payload = synthetic_payload()
                generate(payload)
                annotated = {
                    r.get("question_src_id")
                    for r in payload["skill_question_relations"]
                    if r.get("role") == "PRIMARY"
                }
                check(
                    annotated == {f"q:{n}" for n in range(1, 6)},
                    "successful sample contains exactly five primary annotations",
                )
                with SessionLocal() as db:
                    parent = ui.tasks.get_task(db, task_id)
                    sample = ui.tasks.child_task(
                        db, parent, 1, state="awaiting_confirmation"
                    )
                    sample.stage = "annotate"
                    sample.request = {**sample.request, "stop_after": "annotate_sample"}
                    ui.tasks.store_draft(db, sample, payload, view="auto_draft")
                    ui.tasks.store_draft(db, sample, payload, view="final")
                    db.commit()
                    sample_id = str(sample.id)
                    digest = sample.result_hash
                job = ui.load_job(wid)
                job.update(
                    task_id=sample_id,
                    phase="annotate_sample",
                    stopped=False,
                    error=None,
                )
                job["history"].append(
                    {"phase": "annotate_sample", "task_id": sample_id, "at": ui.now()}
                )
                ui.save_job(job)
                with patch.object(ui.stop_monitor, "wait", side_effect=[False, True]):
                    ui.monitor()
                response = client.get(endpoint, headers=auth).json()["data"]
                check(
                    response["phase"] == "annotate_sample"
                    and response["task"]["state"] == "awaiting_confirmation",
                    "monitor leaves sample at review without full annotation",
                )
                check(
                    client.post(
                        endpoint + "/continue",
                        json={"task_id": sample_id, "result_hash": digest, "items": []},
                        headers=auth,
                    ).status_code
                    == 422,
                    "generated candidates require actual review",
                )
                job["phase"] = "annotate"
                ui.save_job(job)
                items = [
                    {
                        "question_src_id": qid,
                        "decision": "approved",
                        "support_reason": "SYNTHETIC",
                        "skill_reason": "SYNTHETIC",
                    }
                    for qid in sorted(annotated)
                ]
                check(
                    client.post(
                        endpoint + "/continue",
                        json={
                            "task_id": sample_id,
                            "result_hash": digest,
                            "items": items,
                            "content_confirmed": True,
                        },
                        headers=auth,
                    ).status_code
                    == 409,
                    "pending source or annotations block formal import",
                )
                with SessionLocal() as db:
                    check(
                        db.scalar(select(func.count()).select_from(m.LlmAttempt)) == 0,
                        "zero paid calls or reservations",
                    )

                def page(number, lines):
                    return {
                        "source_kind": "answer_explanation",
                        "material_id": 1,
                        "sha256": "0" * 64,
                        "page": number,
                        "page_image_sha256": "1" * 64,
                        "blocks": [
                            {
                                "text": line,
                                "box": [0, 0, 10, 10],
                                "block_index": i,
                                "confidence": 0.99,
                            }
                            for i, line in enumerate(lines)
                        ],
                    }

                pages = [
                    page(
                        1,
                        [
                            "News Report One",
                            "答案详解",
                            "5. What is stated?",
                            "A) One",
                            "B) Two",
                            "C) Three",
                            "D) Four",
                            "析：合成解释。",
                        ],
                    ),
                    page(
                        2,
                        [
                            "选项C为正确答案。",
                            "6. What comes next?",
                            "A) One",
                            "B) Two",
                            "C) Three",
                            "D) Four",
                        ],
                    ),
                ]
                answers = dg.collect_answers(
                    pages, {"groups": [{"key": "news1", "start": 5, "end": 6}]}
                )
                check(
                    answers[5]["correct_option"] == "C",
                    "cross-page split explanation recovers explicit answer",
                )
                check(
                    answers[6]["correct_option"] is None,
                    "answer ownership never shifts to following question",
                )
                ref = {
                    "segments": [
                        {
                            "segment_id": f"b:{n}",
                            "text": word,
                            "segment_type": "body",
                            "passage_key": "p",
                            "speaker": "M",
                            "source_storage_key": "answers.pdf",
                            "source_sha256": "0" * 64,
                            "source_pages": [1],
                            "search_start_ms": 0,
                            "search_end_ms": 3000,
                        }
                        for n, word in enumerate(("Hello.", "Welcome."), 1)
                    ]
                }
                values = {
                    "segment_id": "b:1",
                    "operation": "merge_next",
                    "listened": True,
                    "reason": "SYNTHETIC",
                    "search_start_ms": 0,
                    "search_end_ms": 3000,
                }
                merged, _audit = edit_reference(ref, {"duration_ms": 5000}, values)
                check(
                    len(merged) == 1
                    and merged[0]["text"] == "Hello. Welcome."
                    and len(ref["segments"]) == 2,
                    "alignment edit retains original words and original version",
                )
                invalid = copy.deepcopy(ref)
                invalid["segments"][1]["speaker"] = "W"
                try:
                    edit_reference(invalid, {"duration_ms": 5000}, values)
                except AppError:
                    checks.append("cross-speaker merge rejected")
                else:
                    raise AssertionError("cross-speaker merge accepted")
                if os.getenv("M3_CONSOLE_BROWSER_TEST") == "1":
                    job["phase"] = "annotate_sample"
                    ui.save_job(job)
                    with socket.socket() as free_port:
                        free_port.bind(("127.0.0.1", 0))
                        port = free_port.getsockname()[1]
                    browser_env = {
                        **os.environ,
                        "M3_CONSOLE_PORT": str(port),
                        "M3_CONSOLE_TEST_URL": f"http://127.0.0.1:{port}",
                        "M3_CONSOLE_TEST_WORKFLOW": wid,
                    }
                    with (Path(temporary) / "browser-server.log").open("w") as log:
                        preview = subprocess.Popen(
                            [sys.executable, str(ROOT / "server.py")],
                            env=browser_env,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        try:
                            for _ in range(80):
                                try:
                                    urllib.request.urlopen(
                                        browser_env["M3_CONSOLE_TEST_URL"], timeout=1
                                    ).close()
                                    break
                                except OSError:
                                    if preview.poll() is not None:
                                        raise RuntimeError(
                                            "Browser server exited"
                                        ) from None
                                    time.sleep(0.25)
                            subprocess.run(
                                ["node", str(ROOT / "verify_browser.mjs")],
                                env=browser_env,
                                check=True,
                                timeout=90,
                            )
                            checks.append("desktop/mobile browser checks")
                        finally:
                            preview.terminate()
                            preview.wait(timeout=10)
            engine.dispose()
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "checks": checks,
                    "count": len(checks),
                    "paid_calls": 0,
                },
                ensure_ascii=True,
            )
        )
    finally:
        if sleeper and sleeper.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(sleeper.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        if created:
            with admin.connect() as db:
                db.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
