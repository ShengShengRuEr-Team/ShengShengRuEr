"""Exercise real processing HTTP endpoints; never generate human review approvals."""

from __future__ import annotations

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

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8803")
    parser.add_argument("--mode", choices=("text", "scan"), default="text")
    parser.add_argument("--start-worker", action="store_true")
    parser.add_argument("--task-id")
    parser.add_argument("--poll-timeout", type=int, default=7200)
    parser.add_argument("--reviews-file", type=Path)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env", override=False)
    from app.core.config import get_settings

    settings = get_settings()
    if args.activate and not args.reviews_file:
        parser.error("--activate requires actual --reviews-file records")
    out = args.evidence_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    events = []
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "mode": args.mode,
        "status": "BLOCKED",
        "human_review": "BLOCKED",
        "issues": [],
    }
    worker = None
    worker_log = None
    try:
        with httpx.Client(base_url=args.base_url, timeout=30) as client:

            def login(role):
                username = os.getenv(f"M3_{role.upper()}_USERNAME")
                password = os.getenv(f"M3_{role.upper()}_PASSWORD")
                if not username or not password:
                    raise RuntimeError(
                        "Controlled credentials missing: "
                        f"M3_{role.upper()}_USERNAME/PASSWORD"
                    )
                response = client.post(
                    "/api/v1/login", json={"username": username, "password": password}
                )
                response.raise_for_status()
                events.append(
                    {
                        "method": "POST",
                        "path": "/api/v1/login",
                        "status": response.status_code,
                        "role": role,
                        "response": "credentials and token omitted",
                    }
                )
                return {"Authorization": "Bearer " + response.json()["data"]["token"]}

            admin = login("admin")
            student = login("student")

            def request(method, path, body=None, headers=None, expected=200):
                response = client.request(
                    method, path, json=body, headers=headers or admin
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
                (out / "http.json").write_text(
                    json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                if response.status_code != expected:
                    raise RuntimeError(
                        f"Unexpected HTTP {response.status_code}: {method} {path}"
                    )
                return data["data"]

            if args.task_id:
                task_id = args.task_id
            else:
                material_ids, pages, document = [], {}, None
                for definition in manifest["materials"]:
                    if (
                        definition["source_kind"] in {"paper_text", "paper_scan"}
                        and definition["source_kind"] != "paper_" + args.mode
                    ):
                        continue
                    body = {k: v for k, v in definition.items() if k != "pages"}
                    body["exam_paper_code"] = manifest["exam_paper"]["exam_paper_code"]
                    row = request("POST", "/api/v1/admin/materials", body, expected=201)
                    material_ids.append(row["id"])
                    if definition.get("pages"):
                        pages[str(row["id"])] = definition["pages"]
                    if definition["source_kind"] == "paper_" + args.mode:
                        document = row
                body = {
                    "exam_paper": manifest["exam_paper"],
                    "material_ids": material_ids,
                    "material_pages": pages,
                    "document_mode": args.mode,
                    "expected_question_count": manifest["expected_question_count"],
                    "expected_question_count_source": {
                        "document": document["storage_key"],
                        "sha256": document["sha256"],
                        "locator": manifest["expected_question_count_locator"],
                    },
                    "expected_question_ranges": manifest["expected_question_ranges"],
                    "dictionary_snapshot_sha256": manifest[
                        "dictionary_snapshot_sha256"
                    ],
                    "profile_version": "M3-WIN64-1.1.0",
                }
                task_id = request(
                    "POST", "/api/v1/admin/processing-tasks", body, expected=202
                )["id"]
            report["task_id"] = task_id
            (out / "run.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            if args.start_worker:
                worker_log = (out / "worker.log").open("w", encoding="utf-8")
                worker = subprocess.Popen(
                    [settings.m3_asr_python, "-m", "app.module3.worker", "--once"],
                    cwd=BACKEND,
                    stdout=worker_log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            deadline = time.monotonic() + args.poll_timeout
            url = f"/api/v1/admin/processing-tasks/{task_id}"
            while True:
                task = request("GET", url)
                print(task["state"], task["stage"], flush=True)
                if task["state"] not in {"pending", "running"}:
                    break
                if worker and worker.poll() is not None and task["state"] == "pending":
                    raise RuntimeError("Worker exited before claiming this task")
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Processing poll timeout; retained task for follow-up"
                    )
                time.sleep(5)
            report["task"] = task
            for view in ("auto_draft", "final"):
                data = request("GET", url + "/result?view=" + view)
                (out / f"{view}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            if task["state"] == "failed" or task["issues"]:
                report["issues"] = task["issues"]
                return 2
            checked = request(
                "POST", url + "/checks", {"expected_result_hash": task["result_hash"]}
            )
            report["technical_checks"] = checked
            if not checked["is_passed"]:
                report["issues"] = checked["issues"]
                return 1
            if not args.reviews_file:
                report["issues"] = [
                    "Actual per-question, full-audio and annotation "
                    "review records required"
                ]
                return 2
            reviews = json.loads(args.reviews_file.read_text(encoding="utf-8"))
            if (
                reviews["task_id"] != task_id
                or reviews["result_hash"] != task["result_hash"]
            ):
                raise RuntimeError("Human records belong to a different task/result")
            for review in reviews["reviews"]:
                request(
                    "POST",
                    url + "/reviews",
                    {**review, "result_hash": task["result_hash"]},
                )
            report["human_review"] = "submitted"
            if not args.activate:
                return 2
            paper_id = task["exam_paper_id"]
            batches = request(
                "GET", f"/api/v1/admin/listening-papers/{paper_id}/batches?limit=100"
            )
            old = next((b["id"] for b in batches["items"] if b["is_current"]), None)
            request(
                "POST",
                f"/api/v1/admin/listening-papers/{paper_id}/current-batch",
                {
                    "task_id": task_id,
                    "batch_id": task["batch_id"],
                    "check_id": checked["id"],
                    "result_hash": task["result_hash"],
                    "expected_current_batch_id": old,
                },
            )
            visible = f"/api/v1/admin/listening-papers/{paper_id}/visibility"
            request(
                "POST",
                visible,
                {
                    "action": "confirm",
                    "reason": "Real reviewed module-three acceptance",
                },
            )
            request("GET", f"/api/v1/listening-papers/{paper_id}", headers=student)
            request("GET", f"/api/v1/admin/listening-papers/{paper_id}/companion")
            media = f"/api/v1/listening-papers/{paper_id}/audio"
            response = client.get(media, headers=student)
            response.raise_for_status()
            actual = hashlib.sha256(response.content).hexdigest()
            result = request("GET", url + "/result")["result"]
            if actual != result["audio"]["file_hash"]:
                raise RuntimeError("Downloaded audio identity mismatch")
            file = out / ("returned-audio." + result["audio"]["format"])
            file.write_bytes(response.content)
            for value, status in (("bytes=0-99", 206), ("bytes=999999999999-", 416)):
                part = client.get(media, headers={**student, "Range": value})
                if part.status_code != status:
                    raise RuntimeError("Audio Range response mismatch")
            request(
                "POST", visible, {"action": "cancel", "reason": "Acceptance cleanup"}
            )
            hidden = client.get(f"/api/v1/listening-papers/{paper_id}", headers=student)
            if hidden.status_code != 404:
                raise RuntimeError("Canceled paper remains accessible")
            report["status"] = "PARTIAL"
            report["issues"] = [
                "This run verifies one real document path; full A01-A36 matrix, "
                "decoder and quality report remain separate"
            ]
            return 3
    except Exception as exc:
        report["issues"] = [type(exc).__name__, str(exc)]
        return 2
    finally:
        report["ended_at"] = datetime.now(UTC).isoformat()
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if worker_log:
            worker_log.close()
        print(report["status"], *report["issues"], sep="\n", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
