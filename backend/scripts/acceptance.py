"""真实服务 + PostgreSQL 的端到端验收脚本（开发文档 2.2 的 10 条）。

用法：
    # 终端 1：启动服务
    uvicorn app.main:app --host 127.0.0.1 --port 8000

    # 终端 2：执行验收
    python scripts/acceptance.py
"""

from __future__ import annotations

import argparse
import sys

import httpx

EXPECTED_STUDENT_FIELDS = {
    "id",
    "question_no",
    "prompt_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
}


class Acceptance:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=10.0)
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.rows.append((name, condition, detail))
        print(f"[{'PASS' if condition else 'FAIL'}] {name} {detail}")

    def login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/v1/login",
            json={"username": username, "password": password},
        )
        response.raise_for_status()
        return response.json()["data"]["token"]

    @staticmethod
    def headers(token: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"} if token else {}

    def run(self) -> bool:
        admin_token = self.login("admin", "admin123")
        student_token = self.login("student", "student123")

        admin_info = self.client.get(
            "/api/v1/getInfo", headers=self.headers(admin_token)
        ).json()
        self.check(
            "1 管理员 getInfo 返回 admin",
            admin_info["code"] == 200 and "admin" in admin_info["data"]["roles"],
        )

        student_info = self.client.get(
            "/api/v1/getInfo", headers=self.headers(student_token)
        ).json()
        self.check(
            "2 学生 getInfo 返回 student",
            student_info["code"] == 200
            and student_info["data"]["roles"] == ["student"],
        )

        admin_probe = [
            self.client.get(
                "/api/v1/admin/papers/1/questions",
                headers=self.headers(student_token),
            ),
            self.client.post(
                "/api/v1/admin/processing-tasks",
                headers=self.headers(student_token),
                json={"paper_id": 1},
            ),
            self.client.get(
                "/api/v1/admin/processing-tasks",
                headers=self.headers(student_token),
            ),
            self.client.get(
                "/api/v1/admin/processing-tasks/1",
                headers=self.headers(student_token),
            ),
        ]
        self.check(
            "3 学生 token 调接口 6–9 均 403",
            all(item.status_code == 403 for item in admin_probe),
        )

        papers = self.client.get(
            "/api/v1/papers", headers=self.headers(admin_token)
        ).json()
        paper_id = papers["data"]["items"][0]["id"]

        student_questions = self.client.get(
            f"/api/v1/papers/{paper_id}/questions",
            headers=self.headers(student_token),
        )
        student_items = student_questions.json()["data"]["items"]
        sensitive_absent = not any(
            key in student_questions.text
            for key in ("correct_option", "explanation_text", "transcript_text")
        )
        self.check(
            "4 学生题目字段集合等于白名单且不含敏感字段",
            all(set(item) == EXPECTED_STUDENT_FIELDS for item in student_items)
            and sensitive_absent,
        )

        admin_questions = self.client.get(
            f"/api/v1/admin/papers/{paper_id}/questions",
            headers=self.headers(admin_token),
        )
        admin_items = admin_questions.json()["data"]["items"]
        self.check(
            "4b 管理员题目含答案/解析/原文，且学生响应不含这些值",
            all(
                item.get("correct_option")
                and item.get("explanation_text")
                and item.get("transcript_text")
                for item in admin_items
            )
            and all(
                item["explanation_text"] not in student_questions.text
                and item["transcript_text"] not in student_questions.text
                for item in admin_items
            ),
        )

        no_token_probes = [
            self.client.post("/api/v1/logout"),
            self.client.get("/api/v1/getInfo"),
            self.client.get("/api/v1/papers"),
            self.client.get(f"/api/v1/papers/{paper_id}/questions"),
            self.client.get(f"/api/v1/admin/papers/{paper_id}/questions"),
            self.client.post(
                "/api/v1/admin/processing-tasks", json={"paper_id": paper_id}
            ),
            self.client.get("/api/v1/admin/processing-tasks"),
            self.client.get("/api/v1/admin/processing-tasks/1"),
        ]
        self.check(
            "5 无 token 调接口 2–9 均 401",
            all(item.status_code == 401 for item in no_token_probes),
        )

        replay_token = self.login("admin", "admin123")
        logout = self.client.post(
            "/api/v1/logout", headers=self.headers(replay_token)
        )
        replay_info = self.client.get(
            "/api/v1/getInfo", headers=self.headers(replay_token)
        )
        replay_papers = self.client.get(
            "/api/v1/papers", headers=self.headers(replay_token)
        )
        self.check(
            "6 退出后重放旧 token 返回 401",
            logout.status_code == 200
            and replay_info.status_code == 401
            and replay_papers.status_code == 401,
        )

        created = self.client.post(
            "/api/v1/admin/processing-tasks",
            headers=self.headers(admin_token),
            json={"paper_id": paper_id},
        )
        created_task = created.json()["data"]
        self.check(
            "7 管理员启动任务 status=pending",
            created.status_code == 200
            and created_task["status"] == "pending"
            and created_task["progress"] == 0,
        )

        task_id = created_task["id"]
        task_list = self.client.get(
            "/api/v1/admin/processing-tasks", headers=self.headers(admin_token)
        ).json()
        task_detail = self.client.get(
            f"/api/v1/admin/processing-tasks/{task_id}",
            headers=self.headers(admin_token),
        )
        detail = task_detail.json()["data"]
        self.check(
            "7b 管理员任务列表与详情字段齐全",
            task_list["code"] == 200
            and any(item["id"] == task_id for item in task_list["data"]["items"])
            and {"status", "progress", "message", "result"}
            <= set(detail),
        )

        student_task_probes = [
            self.client.post(
                "/api/v1/admin/processing-tasks",
                headers=self.headers(student_token),
                json={"paper_id": paper_id},
            ),
            self.client.get(
                "/api/v1/admin/processing-tasks",
                headers=self.headers(student_token),
            ),
            self.client.get(
                f"/api/v1/admin/processing-tasks/{task_id}",
                headers=self.headers(student_token),
            ),
        ]
        self.check(
            "8 学生调任务接口均 403",
            all(item.status_code == 403 for item in student_task_probes),
        )

        passed = sum(1 for _, ok, _ in self.rows if ok)
        total = len(self.rows)
        print(f"\n验收汇总：{passed}/{total} 通过")
        return passed == total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="服务地址"
    )
    args = parser.parse_args()

    acceptance = Acceptance(args.base_url)
    try:
        passed = acceptance.run()
    except httpx.HTTPError as exc:
        print(f"请求失败：{exc}")
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
