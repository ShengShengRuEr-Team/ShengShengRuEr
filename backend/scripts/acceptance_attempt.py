"""API-1 端到端验收脚本（真实服务 + 真实库/音频；对齐 T09/V-E 可自动部分）。

用法（在 backend 目录）：
    python -m scripts.acceptance_attempt --base-url http://127.0.0.1:8000 \
        --paper-id <可访问试卷ID> --student-user <学生账号> --admin-user <管理员账号> \
        [--database-url postgresql+psycopg://...]

可选可见性场景（需另一张专用未作答卷）：
    ... --check-visibility --visibility-paper-id <专用卷ID>
    ... --inject-interrupt          # 取消可见后注入受控中断，验证 finally 恢复
    ... --inject-restore-failure    # 模拟恢复本身失败，脚本必须明确 FAIL

设计边界：
- 只做可自动部分：登录→列表/详情→提交→同键回放→不同键 E08→权限→可选可见性；
- 逐题判分正确性抽查、真实专用样例准备与只读 SQL 最终回填属 T10/验收人；
- V-E4 完整口径（P1/D-14）、V-E5b（API-2）、V-E2/E3（读取冻结）打印 BLOCKED，不计 PASS；
- 脚本会写入 attempt/永久标记（这是验收对象），不删除、不宣称撤销；可见性在 finally 恢复；
- 传 --database-url 时只执行 SELECT 并拒绝开发库（库名为 shengshengruer）；
- 退出码：0 无 FAIL（允许 BLOCKED）；1 行为错误或可见性恢复失败；2 参数/服务/数据前置不满足。
"""

import argparse
import getpass
import os
import sys
import uuid

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEV_DATABASE_NAME = "shengshengruer"
PASSWORD_ENV_STUDENT = "ATTEMPT_ACCEPT_STUDENT_PASSWORD"
PASSWORD_ENV_ADMIN = "ATTEMPT_ACCEPT_ADMIN_PASSWORD"

RESULTS: list[tuple[str, str, str]] = []


def _record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))


def _pass(name: str, detail: str = "") -> None:
    _record("PASS", name, detail)


def _fail(name: str, detail: str = "") -> None:
    _record("FAIL", name, detail)


def _blocked(name: str, detail: str = "") -> None:
    _record("BLOCKED", name, detail)


def _mask(value: str | None) -> str:
    if not value:
        return "-"
    return f"{value[:8]}…"


def _password(env_key: str, prompt: str) -> str:
    value = os.environ.get(env_key)
    if value:
        return value
    return getpass.getpass(prompt)


def _json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {}


def _detail_question_ids(detail_data: dict) -> list[int]:
    ids: list[int] = []
    for passage in detail_data.get("passages", []):
        for question in passage.get("questions", []):
            ids.append(question["question_id"])
    return ids


def _submit_headers(token: str | None, attempt_key: str) -> dict[str, str]:
    headers = {"Idempotency-Key": attempt_key}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _submit(client: httpx.Client, paper_id: int, payload: dict, headers: dict) -> httpx.Response:
    return client.post(
        f"/api/v1/listening-papers/{paper_id}/attempts",
        json=payload,
        headers=headers,
    )


def _check_submit_contract(data: dict) -> list[str]:
    expected = {
        "attempt_code",
        "exam_paper_id",
        "submitted_at",
        "question_count",
        "correct_count",
        "correct_rate",
        "practice_score",
    }
    errors = []
    if set(data) != expected:
        errors.append(f"字段集合不符：{sorted(data)}")
    practice = data.get("practice_score", {})
    if set(practice) != {"available", "value", "max", "label", "reason"}:
        errors.append("practice_score 字段集合不符")
    if "非官方成绩" not in str(practice.get("label", "")):
        errors.append("练习估分标签缺少“非官方成绩”")
    return errors


def _forbidden_text_present(text: str) -> list[str]:
    forbidden = (
        "correct_option",
        "explanation_text",
        "explanation_source",
        '"segments"',
        "selected_option",
        "is_correct",
    )
    return [item for item in forbidden if item in text]


# --------------------------------------------------------------------------- #
# 只读 DB 核验（可选；拒绝开发库）
# --------------------------------------------------------------------------- #
def _open_readonly_connection(database_url: str):
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if url.database == DEV_DATABASE_NAME:
        print(f"[BLOCKED] 拒绝连接开发库 {DEV_DATABASE_NAME}（只允许测试库/独立库）")
        return None
    import psycopg

    psycopg_dsn = database_url.replace("postgresql+psycopg://", "postgresql://")
    connection = psycopg.connect(psycopg_dsn, autocommit=False)
    try:
        connection.read_only = True
    except Exception:  # noqa: BLE001 - 驱动差异时退化为显式只读事务
        pass
    return connection


def _read_counts(connection, username: str, paper_id: int):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row is None:
            return None
        student_id = row[0]
        cursor.execute(
            "SELECT count(*) FROM attempts WHERE student_id = %s AND exam_paper_id = %s",
            (student_id, paper_id),
        )
        attempts = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM attempt_answers a JOIN attempts t ON t.id = a.attempt_id "
            "WHERE t.student_id = %s AND t.exam_paper_id = %s",
            (student_id, paper_id),
        )
        answers = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM attempt_rejections "
            "WHERE student_id = %s AND exam_paper_id = %s",
            (student_id, paper_id),
        )
        markers = cursor.fetchone()[0]
    connection.rollback()
    return {"attempts": attempts, "answers": answers, "markers": markers}


def _read_attempt_codes(connection, username: str, paper_id: int) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row is None:
            return []
        cursor.execute(
            "SELECT attempt_code FROM attempts "
            "WHERE student_id = %s AND exam_paper_id = %s ORDER BY id",
            (row[0], paper_id),
        )
        codes = [item[0] for item in cursor.fetchall()]
    connection.rollback()
    return codes


# --------------------------------------------------------------------------- #
# 可见性辅助
# --------------------------------------------------------------------------- #
def _read_visibility(client: httpx.Client, admin_headers: dict, paper_id: int):
    response = client.get(
        f"/api/v1/admin/listening-papers/{paper_id}/companion",
        headers=admin_headers,
    )
    if response.status_code != 200:
        return None
    return bool(_json(response).get("data", {}).get("is_visible"))


def _set_visibility(
    client: httpx.Client, admin_headers: dict, paper_id: int, visible: bool
) -> bool:
    action = "confirm" if visible else "cancel"
    response = client.post(
        f"/api/v1/admin/listening-papers/{paper_id}/visibility",
        json={"action": action, "reason": "T09 验收脚本"},
        headers=admin_headers,
    )
    if response.status_code != 200:
        return False
    return bool(_json(response).get("data", {}).get("is_visible")) == visible


class _InjectedInterrupt(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API-1 端到端验收（T09）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--paper-id", type=int)
    parser.add_argument("--student-user")
    parser.add_argument("--admin-user")
    parser.add_argument("--database-url")
    parser.add_argument("--check-visibility", action="store_true")
    parser.add_argument("--visibility-paper-id", type=int)
    parser.add_argument("--inject-interrupt", action="store_true")
    parser.add_argument("--inject-restore-failure", action="store_true")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)

    missing = [
        name
        for name, value in (
            ("--paper-id", args.paper_id),
            ("--student-user", args.student_user),
            ("--admin-user", args.admin_user),
        )
        if not value
    ]
    if args.check_visibility and not args.visibility_paper_id:
        missing.append("--visibility-paper-id（启用 --check-visibility 时必填）")
    if missing:
        print(f"[BLOCKED] 缺少目标参数：{', '.join(missing)}；本脚本不自动挑选共享试卷")
        return 2
    if args.check_visibility and args.visibility_paper_id == args.paper_id:
        print("[BLOCKED] 主流程试卷与可见性专用试卷必须不同")
        return 2

    connection = None
    if args.database_url:
        connection = _open_readonly_connection(args.database_url)
        if connection is None:
            return 2
    else:
        _blocked(
            "DB 行数核验",
            "未提供 --database-url；仅做 HTTP 断言（行数核验由 T10 只读 SQL 完成）",
        )

    base_url = args.base_url.rstrip("/")
    writes: list[str] = []
    attempt_keys: list[str] = []
    exit_code = 0

    with httpx.Client(base_url=base_url, timeout=args.timeout, trust_env=False) as client:
        # 服务可达性
        try:
            probe = client.get("/api/v1/listening-papers")
        except httpx.HTTPError as exc:
            print(f"[BLOCKED] 服务不可达：{base_url}（{type(exc).__name__}）")
            return 2
        if probe.status_code != 401:
            print(
                f"[BLOCKED] 服务探测异常：无 token 列表返回 {probe.status_code}，预期 401"
            )
            return 2
        _pass("服务可达且未认证返回 401", f"GET /listening-papers -> {probe.status_code}")

        student_password = _password(PASSWORD_ENV_STUDENT, "学生密码：")
        admin_password = _password(PASSWORD_ENV_ADMIN, "管理员密码：")

        def _login(username: str, password: str) -> str | None:
            response = client.post(
                "/api/v1/login", json={"username": username, "password": password}
            )
            if response.status_code != 200:
                return None
            return _json(response).get("data", {}).get("token")

        student_token = _login(args.student_user, student_password)
        admin_token = _login(args.admin_user, admin_password)
        if not student_token or not admin_token:
            print("[BLOCKED] 登录失败（账号/密码/服务前置不满足）")
            return 2
        _pass("学生与管理员登录", "均返回 token")

        student_headers = {"Authorization": f"Bearer {student_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 取卷：列表 + 详情（可访问性前置）
        listing = client.get("/api/v1/listening-papers", headers=student_headers)
        items = _json(listing).get("data", {}).get("items", []) if listing.status_code == 200 else []
        visible_ids = [item["exam_paper_id"] for item in items]
        if args.paper_id not in visible_ids:
            print(
                f"[BLOCKED] 目标试卷 {args.paper_id} 不在学生可见列表（ids={visible_ids}）；"
                "请使用 T10 准备的专用可访问样例"
            )
            return 2
        _pass("学生列表包含目标试卷", f"paper_id={args.paper_id}")

        detail = client.get(
            f"/api/v1/listening-papers/{args.paper_id}", headers=student_headers
        )
        if detail.status_code != 200:
            print(f"[BLOCKED] 学生详情不可读：HTTP {detail.status_code}")
            return 2
        detail_text = detail.text
        forbidden = _forbidden_text_present(detail_text)
        question_ids = _detail_question_ids(_json(detail).get("data", {}))
        if forbidden:
            _fail("学生详情无答案/解析/正文", f"出现受限字段：{forbidden}")
            exit_code = 1
        else:
            _pass("学生详情无答案/解析/正文", f"questions={len(question_ids)}")
        if not question_ids:
            _fail("学生详情题集非空", "questions=0")
        else:
            _pass("学生详情题集非空", f"questions={len(question_ids)}")

        # DB 前置：样例未被该学生消耗
        if connection is not None:
            counts = _read_counts(connection, args.student_user, args.paper_id)
            if counts is None:
                print(f"[BLOCKED] 测试库中找不到学生账号 {args.student_user}")
                return 2
            if counts["attempts"] > 0:
                print(
                    f"[BLOCKED] 样例已被该学生成功作答（attempts={counts['attempts']}）；"
                    "按 A5 不删除记录、不自动换卷"
                )
                return 2

        payload = {
            "loaded_question_ids": question_ids,
            "answers": [
                {"question_id": question_id, "selected_option": "A"}
                for question_id in question_ids
            ],
        }
        attempt_key = str(uuid.uuid4())
        attempt_keys.append(attempt_key)

        submit = _submit(
            client,
            args.paper_id,
            payload,
            _submit_headers(student_token, attempt_key),
        )
        if submit.status_code == 400 and _json(submit).get("msg") == (
            "本轮同一试卷仅允许提交一次"
        ):
            print("[BLOCKED] 首提交返回 E08：样例已消耗（不靠改键绕过）")
            return 2
        if submit.status_code != 200:
            _fail("V-E1 学生提交 200", f"HTTP {submit.status_code} {submit.text[:200]}")
            exit_code = 1
        else:
            data = _json(submit).get("data", {})
            errors = _check_submit_contract(data)
            if errors:
                _fail("提交响应契约", "; ".join(errors))
                exit_code = 1
            else:
                _pass(
                    "V-E1 学生提交 200 且响应契约完整",
                    f"attempt_code={data.get('attempt_code')} "
                    f"rate={data.get('correct_rate')} score={data.get('practice_score', {}).get('value')}",
                )
            attempt_code = data.get("attempt_code")
            if attempt_code:
                writes.append(
                    f"attempt(paper={args.paper_id}, code={attempt_code}, key={_mask(attempt_key)})"
                )

            # 同键回放
            replay = _submit(
                client,
                args.paper_id,
                payload,
                _submit_headers(student_token, attempt_key),
            )
            if (
                replay.status_code == 200
                and _json(replay).get("data", {}).get("attempt_code") == attempt_code
            ):
                _pass("同键同内容回放同一 attempt_code", "HTTP 200，标识一致")
            else:
                _fail(
                    "同键同内容回放同一 attempt_code",
                    f"HTTP {replay.status_code} {replay.text[:160]}",
                )
                exit_code = 1

            # 不同键第二次 → E08
            second_key = str(uuid.uuid4())
            attempt_keys.append(second_key)
            limited = _submit(
                client,
                args.paper_id,
                payload,
                _submit_headers(student_token, second_key),
            )
            if (
                limited.status_code == 400
                and _json(limited).get("msg") == "本轮同一试卷仅允许提交一次"
            ):
                _pass("同卷不同键第二次 → 400 E08", "未新增记录（DB 核验见下）")
            else:
                _fail(
                    "同卷不同键第二次 → 400 E08",
                    f"HTTP {limited.status_code} {limited.text[:160]}",
                )
                exit_code = 1

            # 管理员 / 未认证权限
            admin_submit = _submit(
                client,
                args.paper_id,
                payload,
                _submit_headers(admin_token, str(uuid.uuid4())),
            )
            if admin_submit.status_code == 403:
                _pass("V-E5a 管理员提交 → 403", "HTTP 403")
            else:
                _fail("V-E5a 管理员提交 → 403", f"HTTP {admin_submit.status_code}")
                exit_code = 1

            unauth = _submit(
                client,
                args.paper_id,
                payload,
                {"Idempotency-Key": str(uuid.uuid4())},
            )
            if unauth.status_code == 401:
                _pass("未认证提交 → 401", "HTTP 401")
            else:
                _fail("未认证提交 → 401", f"HTTP {unauth.status_code}")
                exit_code = 1

            # 只读 DB 行数核验
            if connection is not None:
                counts = _read_counts(connection, args.student_user, args.paper_id)
                codes = _read_attempt_codes(connection, args.student_user, args.paper_id)
                if (
                    counts is not None
                    and counts["attempts"] == 1
                    and counts["answers"] == len(question_ids)
                    and counts["markers"] == 0
                    and codes == [attempt_code]
                ):
                    _pass(
                        "V-E1/同键/限次 库内行数",
                        f"attempts=1 answers={len(question_ids)} markers=0 code一致",
                    )
                else:
                    _fail("V-E1/同键/限次 库内行数", f"counts={counts} codes={codes}")
                    exit_code = 1

        # 可选可见性场景
        if args.check_visibility:
            visibility_paper = args.visibility_paper_id
            original = _read_visibility(client, admin_headers, visibility_paper)
            if original is None:
                print(f"[BLOCKED] 无法读取可见性专用卷 {visibility_paper} 的状态")
                return 2
            if not original:
                print(f"[BLOCKED] 可见性专用卷 {visibility_paper} 当前不可见，无法验证取消")
                return 2

            visible_detail = client.get(
                f"/api/v1/listening-papers/{visibility_paper}",
                headers=student_headers,
            )
            visible_ids = (
                _detail_question_ids(_json(visible_detail).get("data", {}))
                if visible_detail.status_code == 200
                else []
            )
            if not visible_ids:
                print(
                    f"[BLOCKED] 无法读取可见性专用卷 {visibility_paper} 的题目集合"
                )
                return 2
            visibility_payload = {
                "loaded_question_ids": visible_ids,
                "answers": [
                    {"question_id": question_id, "selected_option": "A"}
                    for question_id in visible_ids
                ],
            }

            interrupt = False
            try:
                if not _set_visibility(client, admin_headers, visibility_paper, False):
                    _fail("可见性场景：取消可见", "admin 取消失败")
                    exit_code = 1
                else:
                    _pass("可见性场景：取消可见", f"paper_id={visibility_paper}")
                    if args.inject_interrupt:
                        interrupt = True
                        raise _InjectedInterrupt("T09 受控中断（已取消可见）")
                    if args.inject_restore_failure:
                        interrupt = True
                        raise _InjectedInterrupt("T09 受控恢复失败模拟")

                    new_key = str(uuid.uuid4())
                    attempt_keys.append(new_key)
                    rejected = _submit(
                        client,
                        visibility_paper,
                        visibility_payload,
                        _submit_headers(student_token, new_key),
                    )
                    if rejected.status_code == 404:
                        _pass("V-E7 取消可见后提交 → 404", "HTTP 404")
                    else:
                        _fail(
                            "V-E7 取消可见后提交 → 404",
                            f"HTTP {rejected.status_code}",
                        )
                        exit_code = 1
                    replay_rejected = _submit(
                        client,
                        visibility_paper,
                        visibility_payload,
                        _submit_headers(student_token, new_key),
                    )
                    if (
                        replay_rejected.status_code == 404
                        and _json(replay_rejected).get("msg")
                        == _json(rejected).get("msg")
                    ):
                        _pass("永久标记同键回放同一 404", "同一 msg")
                    else:
                        _fail(
                            "永久标记同键回放同一 404",
                            f"HTTP {replay_rejected.status_code}",
                        )
                        exit_code = 1
                    if connection is not None:
                        counts = _read_counts(
                            connection, args.student_user, visibility_paper
                        )
                        if counts == {"attempts": 0, "answers": 0, "markers": 1}:
                            _pass(
                                "准入拒绝库内 0 attempt + 1 标记",
                                f"counts={counts}",
                            )
                        else:
                            _fail("准入拒绝库内 0 attempt + 1 标记", f"counts={counts}")
                            exit_code = 1
            except _InjectedInterrupt as exc:
                _pass("受控中断注入", str(exc))
            finally:
                interrupted = interrupt
                restore_failed = bool(args.inject_restore_failure)
                if restore_failed:
                    _fail(
                        "可见性恢复（模拟失败）",
                        "脚本必须明确 FAIL、保留定位证据、不显示整体通过",
                    )
                    exit_code = 1
                else:
                    restored = _set_visibility(
                        client, admin_headers, visibility_paper, original
                    )
                    if restored:
                        _pass("可见性 finally 恢复原状态", f"is_visible={original}")
                    else:
                        _fail("可见性 finally 恢复原状态", "恢复请求失败")
                        exit_code = 1
                if interrupted and not restore_failed:
                    _pass("受控中断后 finally 已恢复", "中断不掩盖恢复结果")

            if not args.inject_restore_failure:
                fresh_key = str(uuid.uuid4())
                attempt_keys.append(fresh_key)
                fresh = _submit(
                    client,
                    visibility_paper,
                    visibility_payload,
                    _submit_headers(student_token, fresh_key),
                )
                if fresh.status_code == 200:
                    _pass("可见性恢复后新键可提交", "HTTP 200")
                else:
                    _fail(
                        "可见性恢复后新键可提交",
                        f"HTTP {fresh.status_code} {fresh.text[:160]}",
                    )
                    exit_code = 1

    # 冻结/口径未决项：打印 BLOCKED，不判 PASS
    _blocked("V-E4 同卷再次作答完整口径", "P1/D-14 未决；本轮按 BR-18a 限 1 次，见 E08 检查")
    _blocked("V-E5b 管理员读取学生结果", "API-2 冻结（FZ1/P1/P6）")
    _blocked("V-E2/V-E3 结果读取与取消可见后读取", "API-2 冻结（FZ1）")
    _blocked(
        "V-E1 判分正确性人工抽查",
        "脚本只验证契约/行数；逐题判分抽查须 T10/验收人用专用样例完成",
    )

    print()
    for status, name, detail in RESULTS:
        print(f"[{status}] {name} -> {detail}")
    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    failed = sum(1 for status, _, _ in RESULTS if status == "FAIL")
    blocked = sum(1 for status, _, _ in RESULTS if status == "BLOCKED")
    print(f"\n汇总：PASS={passed} FAIL={failed} BLOCKED={blocked}")
    print("本次写入资源（脚本不会删除，也不宣称撤销永久记录）：")
    for item in writes:
        print(f"  - {item}")
    print(
        "说明：本次运行已消耗提交机会并可能写入永久 attempt/拒绝标记；"
        "可见性已在 finally 恢复，但永久记录不撤销。"
    )
    if connection is not None:
        connection.close()
    return 1 if any(status == "FAIL" for status, _, _ in RESULTS) else 0


if __name__ == "__main__":
    sys.exit(main())
