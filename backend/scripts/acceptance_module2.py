"""模块二真实服务 + 真实数据的端到端验收脚本（对齐验收 B01–B16 可执行项）。

前置：开发库已完成迁移、样例已导入（python -m app.import_module2 ...），
且后端已启动。

用法（在 backend 目录）：
    python -m scripts.acceptance_module2 --base-url http://127.0.0.1:8000

说明：本脚本验证可自动执行的部分；逐题内容核对与整套音频核听（B16）须由
真实人员完成并留记录，不在脚本覆盖范围内。
"""

import argparse
import sys

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_results: list[tuple[bool, str, str]] = []


def _check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((bool(condition), name, detail))


def _login(client: httpx.Client, username: str, password: str) -> str:
    response = client.post("/api/v1/login", json={"username": username, "password": password})
    if response.status_code == 200:
        return response.json()["data"]["token"]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="模块二端到端验收")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    # trust_env=False：本脚本只打本机服务，显式忽略环境里的 HTTP_PROXY/NO_PROXY，
    # 否则请求会被外部代理接管，出现 404 或空响应等与本服务无关的假失败。
    with httpx.Client(base_url=base_url, timeout=15.0, trust_env=False) as client:
        admin_token = _login(client, "admin", "admin123")
        student_token = _login(client, "student", "student123")
        _check("1 管理员/学生登录返回 token", bool(admin_token and student_token))
        admin_h = {"Authorization": f"Bearer {admin_token}"}
        student_h = {"Authorization": f"Bearer {student_token}"}

        # 先确认可见，保证后续学生侧用例可执行
        papers_admin = client.get("/api/v1/listening-papers", headers=admin_h)
        admin_items = papers_admin.json()["data"]["items"] if papers_admin.status_code == 200 else []
        _check("2 管理员试卷列表可见全部", papers_admin.status_code == 200 and len(admin_items) >= 1,
               f"count={len(admin_items)}")
        if not admin_items:
            print("没有已导入试卷，请先运行导入工具。")
            return 1
        paper_id = admin_items[0]["exam_paper_id"]

        confirm = client.post(
            f"/api/v1/admin/listening-papers/{paper_id}/visibility",
            json={"action": "confirm", "reason": "验收确认"},
            headers=admin_h,
        )
        _check("3 管理员确认可见", confirm.status_code == 200 and confirm.json()["data"]["is_visible"],
               f"HTTP {confirm.status_code} {confirm.text[:120]}")

        # 学生列表
        listing = client.get("/api/v1/listening-papers", headers=student_h)
        student_ids = [i["exam_paper_id"] for i in listing.json()["data"]["items"]] if listing.status_code == 200 else []
        _check("4 学生列表返回可见试卷", paper_id in student_ids, f"ids={student_ids}")

        # 学生详情：完整 25 题、无受限字段
        detail = client.get(f"/api/v1/listening-papers/{paper_id}", headers=student_h)
        d = detail.json().get("data", {}) if detail.status_code == 200 else {}
        total_q = sum(len(p["questions"]) for p in d.get("passages", []))
        raw = detail.text
        no_restricted = all(f not in raw for f in ("correct_option", "explanation_text", "explanation_source"))
        no_body = '"segments"' not in raw
        _check("5 学生详情返回 25 题", total_q == 25, f"questions={total_q}")
        _check("6 学生响应不含答案/解析/原文", no_restricted and no_body)

        # 管理员配套：答案/解析/状态
        comp = client.get(f"/api/v1/admin/listening-papers/{paper_id}/companion", headers=admin_h)
        c = comp.json().get("data", {}) if comp.status_code == 200 else {}
        cq = sum(len(p["questions"]) for p in c.get("passages", []))
        has_answer = any(q.get("correct_option") for p in c.get("passages", []) for q in p["questions"])
        has_segments = any(p.get("segments") for p in c.get("passages", []))
        _check("7 管理员配套返回 25 题与答案/解析/原文", cq == 25 and has_answer and has_segments,
               f"questions={cq}")
        _check("8 状态字段彼此独立", all(k in c for k in ("is_current", "check_passed", "is_visible", "is_pending_confirmation")))

        # 权限
        _check("9 学生调管理员接口 403",
               client.get(f"/api/v1/admin/listening-papers/{paper_id}/companion", headers=student_h).status_code == 403)
        _check("10 学生不能改可见性",
               client.post(f"/api/v1/admin/listening-papers/{paper_id}/visibility",
                           json={"action": "cancel", "reason": ""}, headers=student_h).status_code == 403)
        _check("11 无 token 调业务接口 401",
               client.get("/api/v1/listening-papers").status_code == 401)

        # 音频 Range
        audio = client.get(f"/api/v1/listening-papers/{paper_id}/audio",
                           headers={**student_h, "Range": "bytes=0-1023"})
        _check("12 学生音频 Range 返回 206 与 Accept-Ranges",
               audio.status_code == 206 and audio.headers.get("Accept-Ranges") == "bytes",
               f"HTTP {audio.status_code} CR={audio.headers.get('Content-Range')}")

        # 取消可见 → 学生拒绝
        cancel = client.post(f"/api/v1/admin/listening-papers/{paper_id}/visibility",
                             json={"action": "cancel", "reason": "验收取消"}, headers=admin_h)
        _check("13 管理员取消可见", cancel.status_code == 200 and not cancel.json()["data"]["is_visible"])
        after_list = client.get("/api/v1/listening-papers", headers=student_h).json()["data"]["items"]
        after_ids = [i["exam_paper_id"] for i in after_list]
        _check("14 取消后学生列表不含该卷", paper_id not in after_ids)
        _check("15 取消后学生详情 404",
               client.get(f"/api/v1/listening-papers/{paper_id}", headers=student_h).status_code == 404)
        _check("16 取消后学生音频 404",
               client.get(f"/api/v1/listening-papers/{paper_id}/audio", headers=student_h).status_code == 404)

        # 恢复可见，便于后续使用
        client.post(f"/api/v1/admin/listening-papers/{paper_id}/visibility",
                    json={"action": "confirm", "reason": "验收后恢复"}, headers=admin_h)

    print()
    for passed, name, detail in _results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} -> {detail}")
    passed_count = sum(1 for p, _, _ in _results if p)
    print(f"\n验收汇总：{passed_count}/{len(_results)} 通过")
    print("提示：B16 逐题内容核对与整套核听须人工完成并留记录，不在本脚本范围。")
    return 0 if passed_count == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
