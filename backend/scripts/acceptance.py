"""真实服务 + PostgreSQL 的端到端验收脚本（开发文档 2.2）。

用法（后端已启动时，在 backend 目录）：
    python -m scripts.acceptance --base-url http://127.0.0.1:8000
"""

import argparse
import sys

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_results: list[tuple[bool, str, str]] = []


def _check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((bool(condition), name, detail))


def main() -> int:
    parser = argparse.ArgumentParser(description="模块一端到端验收")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        admin_login = client.post(
            "/api/v1/login",
            json={"username": "admin", "password": "admin123"},
        )
        admin_ok = admin_login.status_code == 200 and bool(
            admin_login.json().get("data", {}).get("token")
        )
        _check("1 管理员登录返回 token", admin_ok, f"HTTP {admin_login.status_code}")
        admin_token = admin_login.json()["data"]["token"] if admin_ok else ""

        student_login = client.post(
            "/api/v1/login",
            json={"username": "student", "password": "student123"},
        )
        student_ok = student_login.status_code == 200 and bool(
            student_login.json().get("data", {}).get("token")
        )
        _check("2 学生登录返回 token", student_ok, f"HTTP {student_login.status_code}")
        student_token = student_login.json()["data"]["token"] if student_ok else ""

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        student_headers = {"Authorization": f"Bearer {student_token}"}

        response = client.get("/api/v1/getInfo", headers=admin_headers)
        body = response.json()
        _check(
            "3 管理员 getInfo 返回 admin 角色",
            response.status_code == 200 and body["data"]["roles"] == ["admin"],
            f"roles={body['data'].get('roles')}",
        )

        response = client.get("/api/v1/getInfo", headers=student_headers)
        body = response.json()
        _check(
            "4 学生 getInfo 返回 student 角色",
            response.status_code == 200 and body["data"]["roles"] == ["student"],
            f"roles={body['data'].get('roles')}",
        )

        response = client.get("/api/v1/admin/overview", headers=admin_headers)
        _check(
            "5 管理员访问管理端接口返回 200",
            response.status_code == 200,
            f"HTTP {response.status_code}",
        )

        response = client.get("/api/v1/admin/overview", headers=student_headers)
        _check(
            "6 学生访问管理端接口返回 403",
            response.status_code == 403,
            f"HTTP {response.status_code}",
        )

        codes = [
            client.get("/api/v1/getInfo").status_code,
            client.get("/api/v1/admin/overview").status_code,
            client.post("/api/v1/logout").status_code,
        ]
        _check(
            "7 无 token 调受保护接口均返回 401",
            all(code == 401 for code in codes),
            f"HTTP {codes}",
        )

        logout = client.post("/api/v1/logout", headers=admin_headers)
        replay = client.get("/api/v1/getInfo", headers=admin_headers)
        _check(
            "8 退出后重放旧 token 返回 401",
            logout.status_code == 200 and replay.status_code == 401,
            f"logout={logout.status_code}, replay={replay.status_code}",
        )

    print()
    for passed, name, detail in _results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} -> {detail}")

    passed_count = sum(1 for passed, _, _ in _results if passed)
    print(f"\n验收汇总：{passed_count}/{len(_results)} 通过")
    return 0 if passed_count == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
