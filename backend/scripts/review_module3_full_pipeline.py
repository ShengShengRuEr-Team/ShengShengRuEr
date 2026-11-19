"""Verify the real reviewed paper via local TCP API, worker and isolated DB.

Audio acceptance uses the user's explicit approval in this conversation. It never
creates numeric human timestamps or claims a measured accuracy benchmark.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import review_module3_downstream as upstream

BACKEND = upstream.BACKEND
OUTPUT = upstream.WORKSPACE / "outputs/module3-full-pipeline-20261107"
SOURCE = "10e9c1d5-33e2-4570-a86a-7aaa8264144c"
BASE_URL = "http://127.0.0.1:8813"
APPROVAL = "这个我已经审批过了，你直接改成pass"


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def main():
    global OUTPUT, SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id")
    parser.add_argument("--source-task", default=SOURCE)
    parser.add_argument("--source-directory", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--materials-dir", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    OUTPUT, SOURCE = args.output, args.source_task
    if args.database:
        from dotenv import dotenv_values
        from sqlalchemy.engine import make_url

        if not (args.source_directory and args.artifacts_dir and args.materials_dir):
            parser.error(
                "Custom database requires source, artifacts and materials dirs"
            )
        values = dotenv_values(BACKEND / ".env")
        os.environ["DATABASE_URL"] = (
            make_url(values["DATABASE_URL"])
            .set(database=args.database)
            .render_as_string(hide_password=False)
        )
        os.environ.update(APP_ENV="test", PYTHONIOENCODING="utf-8")
        upstream.DATABASE = args.database
    else:
        upstream.configure()
    if args.artifacts_dir:
        os.environ["M3_ARTIFACTS_DIR"] = str(args.artifacts_dir)
    if args.materials_dir:
        os.environ["M3_MATERIALS_DIR"] = str(args.materials_dir)
    OUTPUT.mkdir(exist_ok=True)
    os.environ["AUDIO_STORAGE_DIR"] = str(OUTPUT / "audio")
    sys.path.insert(0, str(BACKEND))
    from sqlalchemy import func, select

    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3.contracts import result_hash
    from app.services.processing import tasks

    settings = get_settings()
    source_dir = args.source_directory or upstream.OUTPUT / ("full-" + SOURCE)
    original = json.loads((source_dir / "draft.json").read_text(encoding="utf-8"))
    semantic = json.loads(
        (source_dir / "semantic-review.json").read_text(encoding="utf-8")
    )
    request = json.loads((source_dir / "request.json").read_text(encoding="utf-8"))
    request.update(
        stop_after="completed",
        reuse_full_annotation_task_id=SOURCE,
        annotation_review=semantic,
    )
    token, _ = create_access_token(user_id=1, username="admin", settings=settings)
    admin = {"Authorization": "Bearer " + token}
    token, _ = create_access_token(user_id=2, username="student", settings=settings)
    student = {"Authorization": "Bearer " + token}
    directory = OUTPUT / ("tcp-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S"))
    directory.mkdir()
    events = []
    report = {"status": "RUNNING", "source_task_id": SOURCE, "issues": []}
    server = None
    server_log = (directory / "api-server.log").open("w", encoding="utf-8")

    def start_server():
        process = subprocess.Popen(
            [
                str(BACKEND / ".venv-api/Scripts/python.exe"),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8813",
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=dict(os.environ),
            stdout=server_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Local API server exited; inspect controlled log")
            try:
                if httpx.get(BASE_URL + "/api/v1/listening-papers").status_code == 401:
                    return process
            except httpx.ConnectError:
                pass
            time.sleep(0.2)
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeError("Local API server readiness timed out")

    def stop_server(process):
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)

    def run_worker(name):
        worker_started = time.monotonic()
        worker_start_at = datetime.now(UTC).isoformat()
        with (directory / (name + ".log")).open("w", encoding="utf-8") as log:
            proc = subprocess.run(
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
                timeout=180,
            )
        dump(
            directory / (name + "-timing.json"),
            {
                "start": worker_start_at,
                "end": datetime.now(UTC).isoformat(),
                "elapsed_seconds": time.monotonic() - worker_started,
                "exit_code": proc.returncode,
            },
        )
        assert proc.returncode == 0, "Worker failed; inspect controlled worker log"

    try:
        server = start_server()
        with httpx.Client(base_url=BASE_URL, timeout=60) as client:

            def call(method, path, body=None, headers=None, expected=200):
                response = client.request(
                    method,
                    path,
                    json=body,
                    headers=admin if headers is None else headers,
                )
                data = response.json()
                events.append(
                    {
                        "method": method,
                        "path": path,
                        "status": response.status_code,
                        "response": data,
                    }
                )
                dump(directory / "http.json", events)
                assert response.status_code == expected, (
                    f"Unexpected HTTP status {response.status_code} for {method} {path}"
                )
                return data.get("data")

            with SessionLocal() as db:
                calls_before = db.scalar(select(func.count()).select_from(LlmAttempt))
            before = upstream.snapshot()
            dump(directory / "business-counts-before.json", before)
            dump(directory / "request.json", request)
            if args.task_id:
                task_id = args.task_id
            else:
                task_id = call(
                    "POST", "/api/v1/admin/processing-tasks", request, expected=202
                )["id"]
                report["task_id"] = task_id
                dump(directory / "report.json", report)
                print("TASK", task_id, flush=True)
                run_worker("worker")
            url = f"/api/v1/admin/processing-tasks/{task_id}"
            task = call("GET", url)
            dump(directory / "task-after-worker.json", task)
            assert task["state"] == "awaiting_confirmation" and task["batch_id"], task
            report.update(
                task_id=task_id,
                batch_id=task["batch_id"],
                exam_paper_id=task["exam_paper_id"],
            )
            with SessionLocal() as db:
                row = tasks.get_task(db, task_id)
                dump(directory / "frozen-request.json", row.request)
                dump(
                    directory / "method-snapshot.json",
                    {"method": row.method, "method_hash": row.method_hash},
                )
                assert row.request["expected_question_count"] == 25
            result = call("GET", url + "/result")["result"]
            dump(directory / "draft.json", result)
            assert result_hash(result) == result_hash(original)
            check = call(
                "POST", url + "/checks", {"expected_result_hash": task["result_hash"]}
            )
            dump(directory / "technical-check.json", check)
            assert check["is_passed"], check["issues"]
            paper_id, batch_id = task["exam_paper_id"], task["batch_id"]
            detail_url = f"/api/v1/listening-papers/{paper_id}"
            activation_url = f"/api/v1/admin/listening-papers/{paper_id}/current-batch"
            batches = call("GET", f"/api/v1/admin/listening-papers/{paper_id}/batches")
            current = next((b["id"] for b in batches["items"] if b["is_current"]), None)
            activation = {
                "task_id": task_id,
                "batch_id": batch_id,
                "check_id": check["id"],
                "result_hash": task["result_hash"],
                "expected_current_batch_id": current,
            }
            call("GET", url, headers={}, expected=401)
            call("GET", url, headers=student, expected=403)
            call(
                "GET",
                detail_url,
                headers=student,
                expected=404 if current is None else 200,
            )
            call("POST", activation_url, activation, headers=student, expected=403)
            call("POST", activation_url, activation, expected=409)

            approval = {
                "user_statement": APPROVAL,
                "source": "current conversation user reply, 2026-11-07 Asia/Shanghai",
                "scope": "audio acceptance for this reviewed actual paper",
                "file_hash": result["audio"]["file_hash"],
                "result_hash": task["result_hash"],
                "millisecond_measurement": "not_claimed",
            }
            dump(directory / "user-audio-approval.json", approval)
            reviews = []
            content_items = [
                {
                    "entity_type": "questions",
                    "src_id": q["_src_id"],
                    "verdict": "PASS",
                    "reference": "source-checks.json; original paper KEYS; "
                    + "semantic-review.json#"
                    + q["_src_id"],
                }
                for q in result["questions"]
            ]
            annotations = [
                {
                    "entity_type": section,
                    "src_id": relation["_src_id"],
                    "verdict": "PASS",
                    "reference": "hash-bound source semantic-review.json; "
                    "all 25 questions approved; dictionary/quote/time checked",
                }
                for section in (
                    "skill_question_relations",
                    "error_question_relations",
                    "other_relations",
                )
                for relation in result.get(section, [])
            ]
            for scope, items in (
                ("content", content_items),
                ("annotations", annotations),
            ):
                reviews.append(
                    call(
                        "POST",
                        url + "/reviews",
                        {
                            "result_hash": task["result_hash"],
                            "scope": scope,
                            "decision": "approved",
                            "items": items,
                            "evidence_refs": [
                                str(source_dir / "semantic-review.json"),
                                str(source_dir / "source-checks.json"),
                            ],
                            "note": "Codex source/content review from approved "
                            "stage-8 result; not an independent blind human benchmark",
                        },
                    )
                )
            call("POST", activation_url, activation, expected=409)
            reviews.append(
                call(
                    "POST",
                    url + "/reviews",
                    {
                        "result_hash": task["result_hash"],
                        "scope": "audio",
                        "decision": "approved",
                        "review_basis": "user_confirmation",
                        "approval_reference": (
                            "current-conversation:user:2026-11-07:audio-approval"
                        ),
                        "items": [
                            {
                                "entity_type": "audio",
                                "src_id": "original",
                                "verdict": "PASS",
                                "file_hash": result["audio"]["file_hash"],
                                "reference": APPROVAL,
                            }
                        ],
                        "evidence_refs": [str(directory / "user-audio-approval.json")],
                        "note": "User confirmed prior audio approval; requested "
                        "record PASS; no numeric human boundary measurements supplied",
                    },
                )
            )
            dump(directory / "reviews.json", reviews)
            complete = call("GET", url)
            assert complete["state"] == "completed", complete
            active = call("POST", activation_url, activation)
            assert active["is_visible"] is False
            call("GET", detail_url, headers=student, expected=404)
            companion = call(
                "GET", f"/api/v1/admin/listening-papers/{paper_id}/companion"
            )
            dump(directory / "companion.json", companion)
            assert companion["review_status"] == "已通过"
            old_questions = {q["question_index"]: q for q in result["questions"]}
            old_passages = {p["_src_id"]: p for p in result["passages"]}
            old_segments = {
                (
                    old_passages[s["passage_src_id"]]["passage_index"],
                    s["segment_index"],
                ): s
                for s in result["transcript_segments"]
            }
            checked_questions, checked_segments = 0, 0
            for passage in companion["passages"]:
                assert passage["review_status"] == "已通过"
                for q in passage["questions"]:
                    expected_q = old_questions[q["question_index"]]
                    assert q["correct_option"] == expected_q["correct_option"]
                    assert q["question_text"] == expected_q["question_text"]
                    assert q["explanation_text"] == expected_q["explanation_text"]
                    assert q["review_status"] == "已通过"
                    assert {o["label"]: o["text"] for o in q["options"]} == {
                        letter: expected_q["option_" + letter.lower()]
                        for letter in "ABCD"
                    }
                    checked_questions += 1
                for segment in passage["segments"]:
                    expected_s = old_segments[
                        (passage["passage_index"], segment["segment_index"])
                    ]
                    assert all(
                        segment[k] == expected_s[k]
                        for k in ("text", "start_ms", "end_ms", "segment_type")
                    )
                    assert segment["speaker_code"] == (expected_s.get("speaker") or "")
                    checked_segments += 1
            assert (checked_questions, checked_segments) == (25, 165)
            dump(
                directory / "readback-checks.json",
                {
                    "status": "PASS",
                    "questions": checked_questions,
                    "options": 100,
                    "segments": checked_segments,
                    "speaker_mapping": "PASS",
                    "review_status_projection": "PASS",
                },
            )
            visibility = f"/api/v1/admin/listening-papers/{paper_id}/visibility"
            call(
                "POST",
                visibility,
                {
                    "action": "confirm",
                    "reason": "User-authorized full pipeline verification",
                },
            )
            shown = call("GET", detail_url, headers=student)
            dump(directory / "student-detail.json", shown)
            shown_text = json.dumps(shown)
            assert not any(
                k in shown_text
                for k in (
                    '"correct_option"',
                    '"explanation_text"',
                    '"evidence_text"',
                    '"annotation_reason"',
                    '"transcript_segments"',
                )
            )
            media = detail_url + "/audio"
            audio = client.get(media, headers=student)
            assert audio.status_code == 200
            digest = hashlib.sha256(audio.content).hexdigest()
            assert digest == result["audio"]["file_hash"]
            returned = directory / ("returned-audio." + result["audio"]["format"])
            returned.write_bytes(audio.content)
            for value, expected in (("bytes=0-99", 206), ("bytes=999999999999-", 416)):
                response = client.get(media, headers={**student, "Range": value})
                assert response.status_code == expected
                if expected == 206:
                    assert response.content == audio.content[:100]
            replay = call("POST", activation_url, activation)
            assert replay["is_visible"] is True
            duplicate = call(
                "POST", "/api/v1/admin/processing-tasks", request, expected=202
            )
            run_worker("duplicate-worker")
            duplicate = call("GET", "/api/v1/admin/processing-tasks/" + duplicate["id"])
            assert duplicate["batch_id"] == batch_id
            assert call("POST", activation_url, activation)["is_visible"] is True
            dump(directory / "duplicate-task.json", duplicate)
            call(
                "POST", visibility, {"action": "cancel", "reason": "Verify revocation"}
            )
            call("GET", detail_url, headers=student, expected=404)
            assert client.get(media, headers=student).status_code == 404
            listing = call("GET", "/api/v1/listening-papers", headers=student)
            assert paper_id not in {i["exam_paper_id"] for i in listing["items"]}
            call(
                "POST",
                visibility,
                {
                    "action": "confirm",
                    "reason": "Restore reviewed isolated acceptance result",
                },
            )
            dump(directory / "final-task.json", call("GET", url))
            with SessionLocal() as db:
                calls_after = db.scalar(select(func.count()).select_from(LlmAttempt))
            assert calls_after == calls_before
            report.update(
                status="PASS",
                technical_checks="PASS",
                content_review="PASS",
                annotation_review="PASS",
                audio_review="PASS_BY_USER_CONFIRMATION",
                measured_millisecond_accuracy="NOT_CLAIMED",
                student_field_safety="PASS",
                media_identity="PASS",
                media_range="PASS",
                revoke_and_reconfirm="PASS",
                idempotent_reimport="PASS",
                activation_replay="PASS",
                business_readback="PASS",
                new_llm_calls=calls_after - calls_before,
                audio_sha256=digest,
                database=upstream.DATABASE,
                transport="local TCP HTTP + independent worker",
                result_hash=task["result_hash"],
            )
        stop_server(server)
        server = start_server()
        with httpx.Client(base_url=BASE_URL, timeout=30) as client:
            restored = client.get(detail_url, headers=student)
            assert restored.status_code == 200
            assert (
                client.get(
                    media, headers={**student, "Range": "bytes=0-99"}
                ).status_code
                == 206
            )
        report["api_restart_persistence"] = "PASS"
        dump(directory / "business-counts-after.json", upstream.snapshot())
        dump(OUTPUT / "latest.json", {"directory": str(directory), **report})
        print(json.dumps(report, ensure_ascii=True), flush=True)
        return 0
    except Exception as error:
        report["status"] = "FAIL"
        report["issues"] = [{"type": type(error).__name__, "message": str(error)}]
        print("FAIL", type(error).__name__, "see controlled report", flush=True)
        return 1
    finally:
        stop_server(server)
        server_log.close()
        report["ended_at"] = datetime.now(UTC).isoformat()
        dump(directory / "report.json", report)


if __name__ == "__main__":
    raise SystemExit(main())
