"""API-1 端到端验收脚本（真实服务 + 真实库/音频；对齐 T09/V-E 可自动部分）。

用法（在 backend 目录；--base-url 为必填，缺失时退出码 2）：
    python -m scripts.acceptance_attempt --base-url http://127.0.0.1:8000 \
        --paper-id <可访问试卷ID> --student-user <学生账号> --admin-user <管理员账号> \
        [--database-url postgresql+psycopg://...]

可选可见性场景（需另一张专用未作答卷）：
    ... --check-visibility --visibility-paper-id <专用卷ID>
    ... --inject-interrupt          # 取消可见后注入受控中断，验证 finally 恢复
    ... --inject-restore-failure    # 模拟恢复本身失败，脚本必须明确 FAIL

退出码：
    0 = 无 FAIL 且无 BLOCKED
    3 = 存在 BLOCKED 但无 FAIL
    1 = 存在 FAIL（含可见性恢复失败）
    2 = 参数/服务/数据前置不满足

边界：
- 只做可自动部分：登录→列表/详情→提交→同键回放→不同键 E08→权限→可选可见性；
- 首提交结果未知（超时/连接断）按 2.6.4 用原键重试一次，不直接 FAIL；
- 逐题判分正确性抽查、真实专用样例与只读 SQL 最终回填属 T10/验收人；
- V-E4 完整口径（P1/D-14）、V-E5b（API-2）、V-E2/E3（读取冻结）打印 BLOCKED，不计 PASS；
- 脚本会写入 attempt/永久标记（验收对象），不删除、不宣称撤销；可见性在 finally 恢复；
- --database-url 仅 SELECT 并拒绝开发库（库名 shengshengruer）；
- 所有退出路径都会打印“写入资源清单 + 永久记录不删除”说明。
"""

import argparse
import getpass
import os
import sys
import uuid

import httpx

DEV_DATABASE_NAME = "shengshengruer"
PASSWORD_ENV_STUDENT = "ATTEMPT_ACCEPT_STUDENT_PASSWORD"
PASSWORD_ENV_ADMIN = "ATTEMPT_ACCEPT_ADMIN_PASSWORD"

RESULTS: list[tuple[str, str, str]] = []
WRITES: list[str] = []


# --------------------------------------------------------------------------- #
# 结果记录与输出
# --------------------------------------------------------------------------- #
def _record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))


def _pass(name: str, detail: str = "") -> None:
    _record("PASS", name, detail)


def _fail(name: str, detail: str = "") -> None:
    _record("FAIL", name, detail)


def _blocked(name: str, detail: str = "") -> None:
    _record("BLOCKED", name, detail)


def _print_resource_notice() -> None:
    print("本次写入资源（脚本不会删除，也不宣称撤销永久记录）：")
    if WRITES:
        for item in WRITES:
            print(f"  - {item}")
    else:
        print("  - （无成功提交写入 attempts；可见性操作按 finally 处理）")
    print("说明：本次运行可能已消耗提交机会并写入永久 attempt/拒绝标记；永久记录不撤销。")


def _print_summary() -> int:
    print()
    for status, name, detail in RESULTS:
        print(f"[{status}] {name} -> {detail}")
    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    failed = sum(1 for status, _, _ in RESULTS if status == "FAIL")
    blocked = sum(1 for status, _, _ in RESULTS if status == "BLOCKED")
    print(f"\n汇总：PASS={passed} FAIL={failed} BLOCKED={blocked}")
    _print_resource_notice()
    if failed:
        print("退出码：1（存在 FAIL）")
        return 1
    if blocked:
        print("退出码：3（存在 BLOCKED，无 FAIL）")
        return 3
    print("退出码：0（无 FAIL 且无 BLOCKED）")
    return 0


def _abort(code: int, message: str) -> int:
    print(f"[BLOCKED] {message}")
    _print_resource_notice()
    print(f"退出码：{code}（前置不满足）")
    return code


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


def _submit(
    client: httpx.Client, paper_id: int, payload: dict, headers: dict
) -> httpx.Response:
    return client.post(
        f"/api/v1/listening-papers/{paper_id}/attempts",
        json=payload,
        headers=headers,
    )


def _submit_first_with_recovery(
    client: httpx.Client,
    paper_id: int,
    payload: dict,
    student_token: str,
    attempt_key: str,
) -> httpx.Response | None:
    """首提交结果未知（超时/连接断）时按 2.6.4 用原键重试一次；两次均未知 → FAIL。"""

    headers = _submit_headers(student_token, attempt_key)
    for attempt in (1, 2):
        try:
            return _submit(client, paper_id, payload, headers)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            if attempt == 1:
                _pass(
                    "首提交结果未知，按 2.6.4 原键重试",
                    f"{type(exc).__name__} -> 同键重试一次（不改键）",
                )
                continue
            _fail(
                "首提交结果未知且原键重试仍失败",
                f"{type(exc).__name__}；保留原键供人工恢复",
            )
            return None
    return None


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
    except Exception:  # noqa: BLE001 - 驱动差异时退化为只读 SELECT
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
    parser = argparse.ArgumentParser(
        description="API-1 端到端验收（T09）",
        epilog=(
            "--base-url 必填。退出码：0=无 FAIL 且无 BLOCKED；3=有 BLOCKED 无 FAIL；"
            "1=有 FAIL；2=前置不满足。"
        ),
    )
    parser.add_argument(
        "--base-url", help="必填，例：http://127.0.0.1:8000"
    )
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
            ("--base-url", args.base_url),
            ("--paper-id", args.paper_id),
            ("--student-user", args.student_user),
            ("--admin-user", args.admin_user),
        )
        if not value
    ]
    if args.check_visibility and not args.visibility_paper_id:
        missing.append("--visibility-paper-id（启用 --check-visibility 时必填）")
    if missing:
        return _abort(
            2, f"缺少目标参数：{', '.join(missing)}；本脚本不自动挑选共享试卷"
        )
    if args.check_visibility and args.visibility_paper_id == args.paper_id:
        return _abort(2, "主流程试卷与可见性专用试卷必须不同")

    connection = None
    if args.database_url:
        connection = _open_readonly_connection(args.database_url)
        if connection is None:
            return _abort(2, "数据库前置不满足（拒绝/无法连接）")
    else:
        _blocked(
            "DB 行数核验",
            "未提供 --database-url；仅做 HTTP 断言（行数核验由 T10 只读 SQL 完成）",
        )

    base_url = args.base_url.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=args.timeout, trust_env=False) as client:
        try:
            probe = client.get("/api/v1/listening-papers")
        except httpx.HTTPError as exc:
            return _abort(2, f"服务不可达：{base_url}（{type(exc).__name__}）")
        if probe.status_code != 401:
            return _abort(
                2,
                f"服务探测异常：无 token 列表返回 {probe.status_code}，预期 401",
            )
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
            return _abort(2, "登录失败（账号/密码/服务前置不满足）")
        _pass("学生与管理员登录", "均返回 token")

        student_headers = {"Authorization": f"Bearer {student_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        listing = client.get("/api/v1/listening-papers", headers=student_headers)
        items = (
            _json(listing).get("data", {}).get("items", [])
            if listing.status_code == 200
            else []
        )
        visible_ids = [item["exam_paper_id"] for item in items]
        if args.paper_id not in visible_ids:
            return _abort(
                2,
                f"目标试卷 {args.paper_id} 不在学生可见列表（ids={visible_ids}）；"
                "请使用 T10 准备的专用可访问样例",
            )
        _pass("学生列表包含目标试卷", f"paper_id={args.paper_id}")

        detail = client.get(
            f"/api/v1/listening-papers/{args.paper_id}", headers=student_headers
        )
        if detail.status_code != 200:
            return _abort(2, f"学生详情不可读：HTTP {detail.status_code}")
        forbidden = _forbidden_text_present(detail.text)
        question_ids = _detail_question_ids(_json(detail).get("data", {}))
        if forbidden:
            _fail("学生详情无答案/解析/正文", f"出现受限字段：{forbidden}")
        else:
            _pass("学生详情无答案/解析/正文", f"questions={len(question_ids)}")
        if not question_ids:
            _fail("学生详情题集非空", "questions=0")
        else:
            _pass("学生详情题集非空", f"questions={len(question_ids)}")

        if connection is not None:
            counts = _read_counts(connection, args.student_user, args.paper_id)
            if counts is None:
                return _abort(2, f"测试库中找不到学生账号 {args.student_user}")
            if counts["attempts"] > 0 or counts["markers"] > 0:
                return _abort(
                    2,
                    "样例已被该学生使用（attempts>0 或 markers>0）；"
                    "按 A5 不删除记录、不自动换卷",
                )

        payload = {
            "loaded_question_ids": question_ids,
            "answers": [
                {"question_id": question_id, "selected_option": "A"}
                for question_id in question_ids
            ],
        }
        attempt_key = str(uuid.uuid4())

        submit = _submit_first_with_recovery(
            client, args.paper_id, payload, student_token, attempt_key
        )
        if submit is None:
            return _print_summary()
        if submit.status_code == 400 and _json(submit).get("msg") == (
            "本轮同一试卷仅允许提交一次"
        ):
            return _abort(2, "首提交返回 E08：样例已消耗（不靠改键绕过）")
        if submit.status_code != 200:
            _fail("V-E1 学生提交 200", f"HTTP {submit.status_code} {submit.text[:200]}")
            return _print_summary()

        data = _json(submit).get("data", {})
        errors = _check_submit_contract(data)
        if errors:
            _fail("提交响应契约", "; ".join(errors))
        else:
            _pass(
                "V-E1 学生提交 200 且响应契约完整",
                f"attempt_code={data.get('attempt_code')} "
                f"rate={data.get('correct_rate')} "
                f"score={data.get('practice_score', {}).get('value')}",
            )
        attempt_code = data.get("attempt_code")
        if attempt_code:
            WRITES.append(
                f"attempt(paper={args.paper_id}, code={attempt_code}, "
                f"key={_mask(attempt_key)})"
            )

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

        second_key = str(uuid.uuid4())
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
                    f"attempts=1 answers={len(question_ids)} markers=0 code 一致",
                )
            else:
                _fail(
                    "V-E1/同键/限次 库内行数", f"counts={counts} codes={codes}"
                )

        # ---------------- 可选可见性场景 ----------------
        if args.check_visibility:
            visibility_paper = args.visibility_paper_id
            original = _read_visibility(client, admin_headers, visibility_paper)
            if original is None:
                return _abort(2, f"无法读取可见性专用卷 {visibility_paper} 的状态")
            if not original:
                return _abort(
                    2, f"可见性专用卷 {visibility_paper} 当前不可见，无法验证取消"
                )
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
                return _abort(
                    2, f"无法读取可见性专用卷 {visibility_paper} 的题目集合"
                )
            visibility_payload = {
                "loaded_question_ids": visible_ids,
                "answers": [
                    {"question_id": question_id, "selected_option": "A"}
                    for question_id in visible_ids
                ],
            }

            interrupted = False
            restored_ok = False
            rejected_key: str | None = None
            rejected_msg: str | None = None
            try:
                if not _set_visibility(
                    client, admin_headers, visibility_paper, False
                ):
                    _fail("可见性场景：取消可见", "admin 取消失败")
                else:
                    _pass("可见性场景：取消可见", f"paper_id={visibility_paper}")
                    if args.inject_interrupt:
                        interrupted = True
                        raise _InjectedInterrupt("T09 受控中断（已取消可见）")
                    if args.inject_restore_failure:
                        interrupted = True
                        raise _InjectedInterrupt("T09 受控恢复失败模拟")

                    rejected_key = str(uuid.uuid4())
                    rejected = _submit(
                        client,
                        visibility_paper,
                        visibility_payload,
                        _submit_headers(student_token, rejected_key),
                    )
                    if rejected.status_code == 404:
                        rejected_msg = _json(rejected).get("msg")
                        _pass(
                            "V-07 取消可见后提交 → 404",
                            f"HTTP 404 msg={rejected_msg}",
                        )
                    else:
                        _fail(
                            "V-07 取消可见后提交 → 404",
                            f"HTTP {rejected.status_code}",
                        )
                    replay_rejected = _submit(
                        client,
                        visibility_paper,
                        visibility_payload,
                        _submit_headers(student_token, rejected_key),
                    )
                    if (
                        replay_rejected.status_code == 404
                        and _json(replay_rejected).get("msg") == rejected_msg
                    ):
                        _pass("永久标记同键回放同一 404", "同一 msg")
                    else:
                        _fail(
                            "永久标记同键回放同一 404",
                            f"HTTP {replay_rejected.status_code}",
                        )
                    if connection is not None:
                        counts = _read_counts(
                            connection, args.student_user, visibility_paper
                        )
                        if counts == {"attempts": 0, "answers": 0, "markers": 1}:
                            _pass(
                                "准入拒绝库内 0 attempt + 1 标记", f"counts={counts}"
                            )
                        else:
                            _fail(
                                "准入拒绝库内 0 attempt + 1 标记", f"counts={counts}"
                            )
            except _InjectedInterrupt as exc:
                _pass("受控中断注入", str(exc))
            finally:
                if args.inject_restore_failure:
                    _fail(
                        "可见性恢复（模拟失败）",
                        "脚本明确 FAIL、保留定位证据、不显示整体通过",
                    )
                else:
                    restored_ok = _set_visibility(
                        client, admin_headers, visibility_paper, original
                    )
                    if restored_ok:
                        _pass("可见性 finally 恢复原状态", f"is_visible={original}")
                    else:
                        _fail("可见性 finally 恢复原状态", "恢复请求失败")
                    if interrupted and restored_ok:
                        _pass("受控中断后 finally 已恢复", "中断不掩盖恢复结果")

            if args.inject_restore_failure:
                _fail(
                    "恢复后旧键/新键断言",
                    "模拟恢复失败：不执行后续断言，也不打印恢复成功文案",
                )
            elif not restored_ok:
                _fail("恢复后旧键/新键断言", "可见性恢复失败，未执行")
            else:
                if rejected_key is not None:
                    old_key_after_restore = _submit(
                        client,
                        visibility_paper,
                        visibility_payload,
                        _submit_headers(student_token, rejected_key),
                    )
                    if (
                        old_key_after_restore.status_code == 404
                        and _json(old_key_after_restore).get("msg") == rejected_msg
                    ):
                        _pass("恢复可见后旧键仍按标记返回 404", "永久标记语义")
                    else:
                        _fail(
                            "恢复可见后旧键仍按标记返回 404",
                            f"HTTP {old_key_after_restore.status_code}",
                        )
                fresh_key = str(uuid.uuid4())
                fresh = _submit(
                    client,
                    visibility_paper,
                    visibility_payload,
                    _submit_headers(student_token, fresh_key),
                )
                if fresh.status_code == 200:
                    _pass("恢复可见后新键可提交", "HTTP 200")
                else:
                    _fail(
                        "恢复可见后新键可提交",
                        f"HTTP {fresh.status_code} {fresh.text[:160]}",
                    )

    # 冻结/口径未决项：打印 BLOCKED，不判 PASS
    _blocked(
        "V-E4 同卷再次作答完整口径",
        "P1/D-14 未决；本轮按 BR-18a 限 1 次，见 E08 检查",
    )
    _blocked("V-E5b 管理员读取学生结果", "API-2 冻结（FZ1/P1/P6）")
    _blocked("V-E2/V-E3 结果读取与取消可见后读取", "API-2 冻结（FZ1）")
    _blocked(
        "V-E1 判分正确性人工抽查",
        "脚本只验证契约/行数；逐题判分抽查须 T10/验收人用专用样例完成",
    )

    code = _print_summary()
    if connection is not None:
        connection.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
