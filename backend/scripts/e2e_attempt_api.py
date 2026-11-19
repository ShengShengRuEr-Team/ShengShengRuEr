"""真实服务 API-1/API-3 链路验收（独立 E2E 库、已由前端完成一次提交）。

前置：backend 在 127.0.0.1:8000 以 E2E 库运行，且 E2E 学生已提交 E2E_ATTEMPT_001。
运行：backend\\venv\\Scripts\\python.exe scripts\\e2e_attempt_api.py
输出：docs/acceptance/attempt-system/e2e-api-results.json
"""

import json
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
PAPER_CODE = "E2E_ATTEMPT_001"
OUT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "acceptance"
    / "attempt-system"
    / "e2e-api-results.json"
)

MSG_E08 = "本轮同一试卷仅允许提交一次"
MSG_NOT_ACCESSIBLE = "资源不存在"
MSG_E05 = "缺少或非法的提交键 Idempotency-Key"
MSG_E09 = "提交键已用于其他提交，请使用新键"
PAPER_EDGE_CODE = "E2E_ATTEMPT_003"

results: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' — ' + detail if detail else ''}")


def login(client: httpx.Client, username: str, password: str = "student123") -> str:
    response = client.post(
        f"{BASE}/api/v1/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["data"]["token"]


def headers(token: str, key: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {token}"}
    if key:
        result["Idempotency-Key"] = key
    return result


def main() -> None:
    with httpx.Client(timeout=20) as client:
        student = login(client, "student")
        admin = login(client, "admin", "admin123")

        # 0) 从列表解析 E2E 试卷 ID，不硬编码（重置数据库后自增 ID 会变化）
        listing = client.get(
            f"{BASE}/api/v1/listening-papers", headers=headers(student)
        )
        listing.raise_for_status()
        paper_id = next(
            (
                item["exam_paper_id"]
                for item in listing.json()["data"]["items"]
                if item["exam_paper_code"] == PAPER_CODE
            ),
            None,
        )
        if paper_id is None:
            raise SystemExit(f"未找到可访问试卷 {PAPER_CODE}")
        record("API-DETAIL 定位试卷", True, f"id={paper_id}")

        # 1) 详情提供真实题目 ID（不硬编码）
        detail = client.get(
            f"{BASE}/api/v1/listening-papers/{paper_id}", headers=headers(student)
        )
        detail.raise_for_status()
        question_ids = [
            question["question_id"]
            for passage in detail.json()["data"]["passages"]
            for question in passage["questions"]
        ]
        record("API-DETAIL 题目 ID", len(question_ids) > 0, f"{len(question_ids)} 题")

        # 2) API-3 已提交 + 字段白名单 + no-store
        status = client.get(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempt-status",
            headers=headers(student),
        )
        status.raise_for_status()
        data = status.json()["data"]
        record(
            "API-3 已提交",
            data["submitted"] is True and data["attempt_count"] >= 1,
            f"count={data['attempt_count']}",
        )
        record(
            "API-3 字段白名单",
            set(data)
            == {"exam_paper_id", "submitted", "attempt_count", "latest_attempt"},
            "",
        )
        latest = data["latest_attempt"]
        record(
            "API-3 汇总字段",
            latest is not None
            and set(latest)
            == {
                "attempt_code",
                "exam_paper_id",
                "submitted_at",
                "question_count",
                "correct_count",
                "correct_rate",
                "practice_score",
            },
            "",
        )
        record(
            "API-3 no-store",
            status.headers.get("Cache-Control") == "no-store",
            status.headers.get("Cache-Control", ""),
        )
        record(
            "API-3 无受保护字段",
            all(
                field not in status.text
                for field in (
                    "correct_option",
                    "explanation",
                    "transcript",
                    "question_id",
                )
            ),
            "",
        )

        # 3) API-1 同卷二次提交 → E08（真实限次）
        duplicate = client.post(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempts",
            headers=headers(student, str(uuid.uuid4())),
            json={
                "loaded_question_ids": question_ids,
                "answers": [
                    {"question_id": question_ids[0], "selected_option": "A"}
                ],
            },
        )
        record(
            "API-1 同卷二次提交 E08",
            duplicate.status_code == 400
            and duplicate.json().get("msg") == MSG_E08,
            f"{duplicate.status_code} {duplicate.json().get('msg')}",
        )

        # 4) 权限：未登录 401、管理员 API-3/API-1 403
        anonymous = client.get(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempt-status"
        )
        record("API-3 未登录 401", anonymous.status_code == 401, "")
        admin_status = client.get(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempt-status",
            headers=headers(admin),
        )
        record("API-3 管理员 403", admin_status.status_code == 403, "")
        admin_submit = client.post(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempts",
            headers=headers(admin, str(uuid.uuid4())),
            json={"loaded_question_ids": question_ids, "answers": []},
        )
        record("API-1 管理员 403", admin_submit.status_code == 403, "")

        # 5) API-1 幂等回放：用已提交的 attempt 的原 Idempotency-Key 无法取得，
        # 这里验证 422（缺 Header）与错误顺序 401 优先于 422。
        no_key = client.post(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempts",
            headers=headers(student),
            json={"loaded_question_ids": question_ids, "answers": []},
        )
        record("API-1 缺幂等键 400 E05", no_key.status_code == 400, "")
        record(
            "API-1 缺幂等键文案",
            no_key.json().get("msg") == MSG_E05,
            str(no_key.json().get("msg")),
        )
        anonymous_submit = client.post(
            f"{BASE}/api/v1/listening-papers/{paper_id}/attempts",
            json={"loaded_question_ids": [], "answers": []},
        )
        record("API-1 未登录 401 优先", anonymous_submit.status_code == 401, "")

        # 6) 不存在的试卷统一 404，不泄露存在性
        missing = client.get(
            f"{BASE}/api/v1/listening-papers/987654321/attempt-status",
            headers=headers(student),
        )
        record(
            "API-3 不可访问 404",
            missing.status_code == 404
            and missing.json().get("msg") == MSG_NOT_ACCESSIBLE,
            "",
        )
        record(
            "API-3 404 no-store",
            missing.headers.get("Cache-Control") == "no-store",
            missing.headers.get("Cache-Control", ""),
        )
        record(
            "API-3 语义不变量",
            data["submitted"] is (data["attempt_count"] > 0)
            and data["attempt_count"] >= 1
            and latest["exam_paper_id"] == data["exam_paper_id"],
            "submitted === (attempt_count > 0)",
        )

        # 7) 独立试卷 003：幂等回放 / E09 / E08 / 学生隔离（真实后端）
        listing = client.get(
            f"{BASE}/api/v1/listening-papers", headers=headers(student)
        )
        listing.raise_for_status()
        edge_id = next(
            (
                item["exam_paper_id"]
                for item in listing.json()["data"]["items"]
                if item["exam_paper_code"] == PAPER_EDGE_CODE
            ),
            None,
        )
        if edge_id is None:
            raise SystemExit(f"未找到可访问试卷 {PAPER_EDGE_CODE}")
        edge_detail = client.get(
            f"{BASE}/api/v1/listening-papers/{edge_id}", headers=headers(student)
        )
        edge_detail.raise_for_status()
        edge_ids = [
            question["question_id"]
            for passage in edge_detail.json()["data"]["passages"]
            for question in passage["questions"]
        ]

        other = login(client, "e2e_student_b")
        other_status = client.get(
            f"{BASE}/api/v1/listening-papers/{edge_id}/attempt-status",
            headers=headers(other),
        )
        other_data = other_status.json()["data"]
        record(
            "API-3 学生隔离（B 无提交）",
            other_status.status_code == 200
            and other_data["submitted"] is False
            and other_data["attempt_count"] == 0
            and other_data["latest_attempt"] is None,
            f"count={other_data.get('attempt_count')}",
        )

        first_key = str(uuid.uuid4())
        first_payload = {
            "loaded_question_ids": edge_ids,
            "answers": [{"question_id": edge_ids[0], "selected_option": "A"}],
        }
        first = client.post(
            f"{BASE}/api/v1/listening-papers/{edge_id}/attempts",
            headers=headers(student, first_key),
            json=first_payload,
        )
        record("API-1 首次提交 200", first.status_code == 200, str(first.status_code))
        first_code = first.json().get("data", {}).get("attempt_code")

        replay = client.post(
            f"{BASE}/api/v1/listening-papers/{edge_id}/attempts",
            headers=headers(student, first_key),
            json=first_payload,
        )
        record(
            "API-1 同键同 payload 幂等回放",
            replay.status_code == 200
            and replay.json().get("data", {}).get("attempt_code") == first_code,
            f"code={first_code}",
        )

        conflict = client.post(
            f"{BASE}/api/v1/listening-papers/{edge_id}/attempts",
            headers=headers(student, first_key),
            json={
                "loaded_question_ids": edge_ids,
                "answers": [
                    {"question_id": edge_ids[1], "selected_option": "B"}
                ],
            },
        )
        record(
            "API-1 同键异 payload E09",
            conflict.status_code == 400
            and conflict.json().get("msg") == MSG_E09,
            f"{conflict.status_code} {conflict.json().get('msg')}",
        )

        limit = client.post(
            f"{BASE}/api/v1/listening-papers/{edge_id}/attempts",
            headers=headers(student, str(uuid.uuid4())),
            json=first_payload,
        )
        record(
            "API-1 异键限次 E08",
            limit.status_code == 400 and limit.json().get("msg") == MSG_E08,
            f"{limit.status_code} {limit.json().get('msg')}",
        )

        edge_status = client.get(
            f"{BASE}/api/v1/listening-papers/{edge_id}/attempt-status",
            headers=headers(student),
        )
        edge_data = edge_status.json()["data"]
        record(
            "API-3 已提交与 API-1 汇总一致",
            edge_data["submitted"] is True
            and edge_data["attempt_count"] == 1
            and edge_data["latest_attempt"]["attempt_code"] == first_code,
            f"count={edge_data['attempt_count']}",
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item for item in results if item["status"] == "FAIL"]
    print(
        json.dumps(
            {"total": len(results), "failed": len(failed)}, ensure_ascii=False
        )
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
