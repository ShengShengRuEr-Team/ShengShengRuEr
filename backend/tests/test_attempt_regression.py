"""T07 权限、错误顺序与既有接口回归（只写测试，不改实现）。

覆盖：API-1 权限/顺序（401→403→404）、既有模块一/二接口回归（交卷前后字段
集合、音频 Range、管理员 3 接口、鉴权语义）、错误外壳与日志脱敏（M-23a）。
测试数据全部在独立测试库自建并清理，不污染模块二共享夹具。
"""

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from tests.conftest import auth_headers, login

IDENTITY_MAPPING = {"A": "A", "B": "B", "C": "C", "D": "D"}
AUDIO_BYTES = b"T07-AUDIO-" + bytes(range(256)) * 15  # 4096 字节

FORBIDDEN_DETAIL_KEYS = {
    "correct_option",
    "correct_option_base",
    "explanation_text",
    "explanation_source",
    "segments",
    "transcript",
    "transcript_segments",
}


# --------------------------------------------------------------------------- #
# 通用辅助
# --------------------------------------------------------------------------- #
def _key() -> str:
    return str(uuid.uuid4())


def _payload(question_ids):
    return {
        "loaded_question_ids": list(question_ids),
        "answers": [
            {"question_id": qid, "selected_option": "A"} for qid in question_ids
        ],
    }


def _post(client, paper_id, payload, *, key=None, token=None):
    headers = {}
    if token is not None:
        headers.update(auth_headers(token))
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(
        f"/api/v1/listening-papers/{paper_id}/attempts",
        json=payload,
        headers=headers,
    )


def _flatten_keys(value, keys=None):
    if keys is None:
        keys = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            _flatten_keys(item, keys)
    elif isinstance(value, list):
        for item in value:
            _flatten_keys(item, keys)
    return keys


def _attempt_rows(paper_id):
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        attempts = session.execute(
            text("SELECT count(*) FROM attempts WHERE exam_paper_id = :paper"),
            {"paper": paper_id},
        ).scalar_one()
        answers = session.execute(
            text(
                "SELECT count(*) FROM attempt_answers a "
                "JOIN attempts t ON t.id = a.attempt_id "
                "WHERE t.exam_paper_id = :paper"
            ),
            {"paper": paper_id},
        ).scalar_one()
    return attempts, answers


# --------------------------------------------------------------------------- #
# 测试数据：独立 25 题试卷（可见 / 不可见 / 未绑定音频）
# --------------------------------------------------------------------------- #
@pytest.fixture
def t07_data():
    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import (
        AudioFile,
        ContentCheck,
        ExamPaper,
        ImportBatch,
        PaperVisibility,
        Passage,
        Presentation,
        Question,
    )

    settings = get_settings()
    audio_dir = settings.audio_storage_path
    audio_dir.mkdir(parents=True, exist_ok=True)
    state = SimpleNamespace(papers=[], audio=[], files=[])

    def _build(*, visible=True, with_audio=True):
        tag = uuid.uuid4().hex[:12]
        audio_path = audio_dir / f"t07_{tag}.m4a"
        audio_path.write_bytes(AUDIO_BYTES)
        with SessionLocal() as session:
            audio = AudioFile(
                audio_code=f"T07A_{tag}",
                storage_key=f"t07_{tag}.m4a",
                duration_ms=5000,
                mime_type="audio/mp4",
                file_hash=hashlib.sha256(AUDIO_BYTES).hexdigest(),
            )
            session.add(audio)
            session.flush()
            paper = ExamPaper(
                exam_paper_code=f"T07_{tag}",
                exam_level="CET4",
                exam_year=2025,
                exam_month=6,
                paper_set=1,
                playback_audio_id=audio.id if with_audio else None,
                expected_question_count=25,
                expected_question_count_source={"kind": "test"},
            )
            session.add(paper)
            session.flush()
            batch = ImportBatch(
                exam_paper_id=paper.id,
                audio_id=audio.id if with_audio else None,
                batch_code=f"T07B_{tag}",
                status="active",
                is_current=True,
            )
            session.add(batch)
            session.flush()
            layout = (("短篇新闻", 7), ("长对话", 8), ("听力篇章", 10))
            questions = []
            for passage_index, (passage_type, passage_count) in enumerate(
                layout, start=1
            ):
                passage = Passage(
                    batch_id=batch.id,
                    exam_paper_id=paper.id,
                    audio_id=audio.id if with_audio else None,
                    passage_code=f"T07P_{tag}_{passage_index}",
                    passage_index=passage_index,
                    passage_type=passage_type,
                    start_ms=0,
                    end_ms=5000,
                )
                session.add(passage)
                session.flush()
                for _ in range(passage_count):
                    index = len(questions) + 1
                    question = Question(
                        batch_id=batch.id,
                        passage_id=passage.id,
                        question_code=f"T07Q_{tag}_{index}",
                        question_text=f"T07 question {index}",
                        option_a=f"q{index} A",
                        option_b=f"q{index} B",
                        option_c=f"q{index} C",
                        option_d=f"q{index} D",
                        correct_option="A",
                        explanation_text="T07 explanation（不应出现在学生接口）",
                    )
                    session.add(question)
                    questions.append(question)
            session.flush()
            for position, question in enumerate(questions, start=1):
                session.add(
                    Presentation(
                        batch_id=batch.id,
                        exam_paper_id=paper.id,
                        question_id=question.id,
                        question_no=position,
                        option_letter_mapping=dict(IDENTITY_MAPPING),
                        mapping_source="test",
                    )
                )
            session.add(
                ContentCheck(
                    exam_paper_id=paper.id,
                    batch_id=batch.id,
                    is_passed=True,
                    issues=[],
                )
            )
            session.add(
                PaperVisibility(
                    exam_paper_id=paper.id,
                    batch_id=batch.id,
                    is_visible=visible,
                )
            )
            session.commit()
            result = SimpleNamespace(
                paper_id=paper.id,
                batch_id=batch.id,
                question_ids=[question.id for question in questions],
                audio_path=audio_path,
            )
        state.papers.append(result.paper_id)
        state.audio.append(audio.id)
        state.files.append(audio_path)
        return result

    yield SimpleNamespace(
        visible=_build(visible=True, with_audio=True),
        invisible=_build(visible=False, with_audio=True),
        unbound=_build(visible=True, with_audio=False),
        audio_dir=audio_dir,
    )

    with SessionLocal() as session:
        for paper_id in state.papers:
            session.execute(
                text(
                    "DELETE FROM attempt_answers WHERE attempt_id IN "
                    "(SELECT id FROM attempts WHERE exam_paper_id = :paper)"
                ),
                {"paper": paper_id},
            )
            session.execute(
                text("DELETE FROM attempts WHERE exam_paper_id = :paper"),
                {"paper": paper_id},
            )
            session.execute(
                text(
                    "DELETE FROM attempt_rejections WHERE exam_paper_id = :paper"
                ),
                {"paper": paper_id},
            )
            session.execute(
                text("DELETE FROM exam_papers WHERE id = :paper"),
                {"paper": paper_id},
            )
        for audio_id in state.audio:
            session.execute(
                text("DELETE FROM audio_files WHERE id = :audio"),
                {"audio": audio_id},
            )
        session.commit()
    for path in state.files:
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def t07_users(client):
    """临时用户：无角色用户（403）、student 用户（用于撤销 token 后 401）。"""

    from app.core.security import hash_password
    from app.db.base import SessionLocal
    from app.db.models import Role, TokenRevocation, User, UserRole

    created = []

    def _make(suffix: str, role_key: str | None = None):
        username = f"t07_{suffix}_{uuid.uuid4().hex[:8]}"
        password = "T07-password-123"
        with SessionLocal() as session:
            user = User(
                username=username,
                password_hash=hash_password(password),
                nickname="T07 临时用户",
            )
            session.add(user)
            session.flush()
            if role_key is not None:
                role = session.query(Role).filter(Role.role_key == role_key).one()
                session.add(UserRole(user_id=user.id, role_id=role.id))
            session.commit()
            user_id = user.id
        created.append(user_id)
        return SimpleNamespace(
            user_id=user_id,
            username=username,
            password=password,
            token=login(client, username, password),
        )

    yield _make

    with SessionLocal() as session:
        for user_id in created:
            session.execute(
                text("DELETE FROM token_revocations WHERE user_id = :user"),
                {"user": user_id},
            )
            session.execute(
                text("DELETE FROM user_roles WHERE user_id = :user"),
                {"user": user_id},
            )
            session.execute(
                text("DELETE FROM users WHERE id = :user"),
                {"user": user_id},
            )
        session.commit()


# --------------------------------------------------------------------------- #
# T07-A1：无 token 401 / admin 403 / 无学生角色 403 / 学生 200
# --------------------------------------------------------------------------- #
def test_a1_api1_role_matrix(
    client, student_token, admin_token, t07_data, t07_users
):
    content = t07_data.visible
    payload = _payload(content.question_ids)

    no_token = _post(client, content.paper_id, payload, key=_key())
    assert no_token.status_code == 401, no_token.text

    admin = _post(client, content.paper_id, payload, key=_key(), token=admin_token)
    assert admin.status_code == 403, admin.text
    assert admin.json()["msg"] == "没有访问该接口的权限：需要学生角色"

    no_role_user = t07_users("norole")
    no_role = _post(
        client, content.paper_id, payload, key=_key(), token=no_role_user.token
    )
    assert no_role.status_code == 403, no_role.text
    assert no_role.json()["msg"] == "没有访问该接口的权限：需要学生角色"

    student = _post(
        client, content.paper_id, payload, key=_key(), token=student_token
    )
    assert student.status_code == 200, student.text
    assert student.json()["msg"] == "提交成功"

    assert _attempt_rows(content.paper_id) == (1, 25)


def test_a1_revoked_token_returns_401(client, t07_data, t07_users):
    content = t07_data.visible
    user = t07_users("revoked", role_key="student")
    logout = client.post("/api/v1/logout", headers=auth_headers(user.token))
    assert logout.status_code == 200, logout.text

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=user.token,
    )

    assert response.status_code == 401, response.text
    assert response.json()["msg"] == "未登录或登录已失效"


# --------------------------------------------------------------------------- #
# T07-A2：无 token/不存在→401；admin/不存在→403；student/不可见→404
# --------------------------------------------------------------------------- #
def test_a2_auth_order_before_resource_lookup(
    client, student_token, admin_token, t07_data
):
    missing_paper_id = 2**62

    no_token = _post(
        client, missing_paper_id, _payload([1]), key=_key()
    )
    assert no_token.status_code == 401, no_token.text

    admin = _post(
        client, missing_paper_id, _payload([1]), key=_key(), token=admin_token
    )
    assert admin.status_code == 403, admin.text
    assert admin.json()["msg"] != "资源不存在"

    invisible = t07_data.invisible
    student = _post(
        client,
        invisible.paper_id,
        _payload(invisible.question_ids),
        key=_key(),
        token=student_token,
    )
    assert student.status_code == 404, student.text
    assert student.json()["msg"] == "资源不存在"


# --------------------------------------------------------------------------- #
# T07-A3：交卷前后学生详情字段集合完全一致，且无答案/解析/正文
# --------------------------------------------------------------------------- #
def test_a3_student_detail_unchanged_before_and_after_attempt(
    client, student_token, t07_data
):
    content = t07_data.visible
    list_url = "/api/v1/listening-papers"
    detail_url = f"/api/v1/listening-papers/{content.paper_id}"
    audio_url = f"/api/v1/listening-papers/{content.paper_id}/audio"

    list_before = client.get(list_url, headers=auth_headers(student_token))
    detail_before = client.get(detail_url, headers=auth_headers(student_token))
    audio_before = client.get(audio_url, headers=auth_headers(student_token))
    assert list_before.status_code == 200
    assert detail_before.status_code == 200
    assert audio_before.status_code == 200

    submit = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )
    assert submit.status_code == 200, submit.text

    list_after = client.get(list_url, headers=auth_headers(student_token))
    detail_after = client.get(detail_url, headers=auth_headers(student_token))
    audio_after = client.get(audio_url, headers=auth_headers(student_token))

    assert list_after.json() == list_before.json()
    assert detail_after.json() == detail_before.json()
    assert audio_after.status_code == audio_before.status_code
    assert audio_after.content == audio_before.content

    detail_keys = _flatten_keys(detail_before.json())
    assert FORBIDDEN_DETAIL_KEYS.isdisjoint(detail_keys), (
        FORBIDDEN_DETAIL_KEYS & detail_keys
    )
    list_keys = _flatten_keys(list_before.json())
    assert FORBIDDEN_DETAIL_KEYS.isdisjoint(list_keys)

    detail_data = detail_before.json()["data"]
    assert "passages" in detail_data
    assert "correct_option" not in detail_before.text
    assert "explanation_text" not in detail_before.text
    assert "segments" not in detail_before.text


# --------------------------------------------------------------------------- #
# T07-A4：音频 200/206/404
# --------------------------------------------------------------------------- #
def test_a4_audio_range_and_unavailable(client, student_token, t07_data):
    visible = t07_data.visible
    invisible = t07_data.invisible
    unbound = t07_data.unbound
    audio_url = f"/api/v1/listening-papers/{visible.paper_id}/audio"

    full = client.get(audio_url, headers=auth_headers(student_token))
    assert full.status_code == 200, full.text
    assert full.headers["Accept-Ranges"] == "bytes"
    assert full.content == AUDIO_BYTES

    ranged = client.get(
        audio_url,
        headers={**auth_headers(student_token), "Range": "bytes=0-1023"},
    )
    assert ranged.status_code == 206, ranged.text
    assert ranged.headers["Content-Range"].startswith("bytes 0-1023/")
    assert len(ranged.content) == 1024

    invisible_audio = client.get(
        f"/api/v1/listening-papers/{invisible.paper_id}/audio",
        headers=auth_headers(student_token),
    )
    assert invisible_audio.status_code == 404, invisible_audio.text

    unbound_audio = client.get(
        f"/api/v1/listening-papers/{unbound.paper_id}/audio",
        headers=auth_headers(student_token),
    )
    assert unbound_audio.status_code == 404, unbound_audio.text
    assert unbound_audio.json()["msg"] == "试卷未绑定音频"


# --------------------------------------------------------------------------- #
# T07-A5：学生调管理员 3 接口 403；管理员正常调用
# --------------------------------------------------------------------------- #
def test_a5_admin_endpoints_permissions(
    client, student_token, admin_token, t07_data
):
    paper_id = t07_data.visible.paper_id
    companion = f"/api/v1/admin/listening-papers/{paper_id}/companion"
    checks = f"/api/v1/admin/listening-papers/{paper_id}/checks"
    visibility = f"/api/v1/admin/listening-papers/{paper_id}/visibility"

    for method, url in (("get", companion), ("get", checks)):
        student = getattr(client, method)(url, headers=auth_headers(student_token))
        assert student.status_code == 403, (url, student.text)
        admin = getattr(client, method)(url, headers=auth_headers(admin_token))
        assert admin.status_code == 200, (url, admin.text)

    student_visibility = client.post(
        visibility,
        json={"action": "cancel", "reason": "t07"},
        headers=auth_headers(student_token),
    )
    assert student_visibility.status_code == 403, student_visibility.text

    admin_visibility = client.post(
        visibility,
        json={"action": "cancel", "reason": "t07"},
        headers=auth_headers(admin_token),
    )
    assert admin_visibility.status_code == 200, admin_visibility.text
    assert admin_visibility.json()["data"]["action"] == "cancel"


# --------------------------------------------------------------------------- #
# 模块一鉴权语义回归（login / logout / getInfo）
# --------------------------------------------------------------------------- #
def test_module1_auth_regression(client, student_token, t07_users):
    denied = client.post(
        "/api/v1/login", json={"username": "admin", "password": "wrong-password"}
    )
    unknown = client.post(
        "/api/v1/login", json={"username": "no-such-user", "password": "x"}
    )
    assert denied.status_code == 401 and unknown.status_code == 401
    assert denied.json()["msg"] == unknown.json()["msg"]

    info = client.get("/api/v1/getInfo", headers=auth_headers(student_token))
    assert info.status_code == 200, info.text
    assert set(info.json()["data"]) == {"user", "roles", "is_admin"}
    assert info.json()["data"]["is_admin"] is False

    assert client.get("/api/v1/getInfo").status_code == 401

    user = t07_users("logout", role_key="student")
    assert (
        client.post("/api/v1/logout", headers=auth_headers(user.token)).status_code
        == 200
    )
    revoked = client.get("/api/v1/getInfo", headers=auth_headers(user.token))
    assert revoked.status_code == 401, revoked.text


# --------------------------------------------------------------------------- #
# T07-A7：数据库错误仍为既有 500 外壳；最终日志无敏感信息（M-23a）
# --------------------------------------------------------------------------- #
def test_a7_db_error_keeps_shell_and_logs_are_safe(
    client, student_token, t07_data, monkeypatch, caplog
):
    import app.services.attempts as service

    content = t07_data.visible
    secret_answer = "T07_SECRET_ANSWER"
    secret_explanation = "T07_SECRET_EXPLANATION"
    secret_body = "T07_SECRET_BODY"

    def _leaky_failure(*args, **kwargs):
        raise OperationalError(
            f"INSERT {secret_answer} {secret_explanation} {secret_body}",
            {},
            Exception(
                f"DETAIL: {secret_answer} {secret_explanation} {secret_body}"
            ),
        )

    monkeypatch.setattr(service, "insert_attempt_with_answers", _leaky_failure)

    with caplog.at_level("WARNING"):
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )

    assert response.status_code == 500, response.text
    assert response.json() == {
        "code": 500,
        "msg": "服务器内部错误",
        "data": None,
    }
    assert secret_answer not in response.text
    assert secret_explanation not in response.text
    assert secret_body not in response.text
    assert secret_answer not in caplog.text
    assert secret_explanation not in caplog.text
    assert secret_body not in caplog.text
    assert "stage=" in caplog.text
    assert "error_type=" in caplog.text
    assert not any("未处理异常" in record.message for record in caplog.records)
    assert _attempt_rows(content.paper_id) == (0, 0)


# --------------------------------------------------------------------------- #
# T08 补测：M-18 / V-R3 越界 Range → 416
# --------------------------------------------------------------------------- #
def test_m18_audio_range_out_of_bounds_416(client, student_token, t07_data):
    content = t07_data.visible
    audio_url = f"/api/v1/listening-papers/{content.paper_id}/audio"

    response = client.get(
        audio_url,
        headers={**auth_headers(student_token), "Range": "bytes=999999-"},
    )

    assert response.status_code == 416, response.text
    assert response.headers["Content-Range"] == f"bytes */{len(AUDIO_BYTES)}"
    assert response.headers["Accept-Ranges"] == "bytes"
