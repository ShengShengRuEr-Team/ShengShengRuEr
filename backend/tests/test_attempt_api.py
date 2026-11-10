"""T06 API-1 集成测试：判定顺序、错误映射、幂等/限次、事务恢复与安全日志。

真实 PostgreSQL 测试库（conftest `shengshengruer_test`）+ FastAPI TestClient，
不连外部服务；app.* 在夹具/函数内延迟导入。
"""

import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from tests.conftest import auth_headers

IDENTITY_MAPPING = {"A": "A", "B": "B", "C": "C", "D": "D"}


# --------------------------------------------------------------------------- #
# HTTP / DB helpers
# --------------------------------------------------------------------------- #
def _key() -> str:
    return str(uuid.uuid4())


def _payload(question_ids, answered=None):
    if answered is None:
        answered = question_ids
    return {
        "loaded_question_ids": list(question_ids),
        "answers": [
            {"question_id": qid, "selected_option": "A"} for qid in answered
        ],
    }


def _post(
    client,
    paper_id,
    payload,
    *,
    key=None,
    token=None,
    raw_headers=None,
):
    headers = {}
    if token is not None:
        headers.update(auth_headers(token))
    if key is not None:
        headers["Idempotency-Key"] = key
    if raw_headers:
        headers.update(raw_headers)
    return client.post(
        f"/api/v1/listening-papers/{paper_id}/attempts",
        json=payload,
        headers=headers,
    )


def _db_counts(paper_id):
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
        markers = session.execute(
            text(
                "SELECT count(*) FROM attempt_rejections "
                "WHERE exam_paper_id = :paper"
            ),
            {"paper": paper_id},
        ).scalar_one()
    return attempts, answers, markers


def _marker_kinds(paper_id):
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        return session.execute(
            text(
                "SELECT rejection_kind FROM attempt_rejections "
                "WHERE exam_paper_id = :paper"
            ),
            {"paper": paper_id},
        ).scalars().all()


def _set_visible(paper_id, batch_id, visible: bool) -> None:
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text("UPDATE paper_visibility SET is_visible = :v WHERE batch_id = :b"),
            {"v": visible, "b": batch_id},
        )
        session.commit()


# --------------------------------------------------------------------------- #
# 数据工厂（committed，供 TestClient 的独立会话读取）
# --------------------------------------------------------------------------- #
@pytest.fixture
def api_data():
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

    def _new_audio(session, tag):
        audio = AudioFile(
            audio_code=f"T06A_{tag}",
            storage_key=f"t06_{tag}.m4a",
            duration_ms=1000,
            mime_type="audio/mpeg",
            file_hash="b" * 64,
        )
        session.add(audio)
        session.flush()
        return audio

    def _add_batch(
        session,
        paper,
        audio,
        *,
        tag,
        is_current=True,
        count=25,
        visible=True,
        check_passed=True,
        mapping=None,
    ):
        batch = ImportBatch(
            exam_paper_id=paper.id,
            audio_id=audio.id,
            batch_code=f"T06B_{tag}",
            status="active",
            is_current=is_current,
        )
        session.add(batch)
        session.flush()
        layout = (
            ("短篇新闻", 7),
            ("长对话", 8),
            ("听力篇章", 10),
        )
        if count != 25:
            layout = (("短篇新闻", count),)
        questions = []
        for passage_index, (passage_type, passage_count) in enumerate(
            layout, start=1
        ):
            passage = Passage(
                batch_id=batch.id,
                exam_paper_id=paper.id,
                audio_id=audio.id,
                passage_code=f"T06P_{tag}_{passage_index}",
                passage_index=passage_index,
                passage_type=passage_type,
                start_ms=0,
                end_ms=1000,
            )
            session.add(passage)
            session.flush()
            for _ in range(passage_count):
                index = len(questions) + 1
                question = Question(
                    batch_id=batch.id,
                    passage_id=passage.id,
                    question_code=f"T06Q_{tag}_{index}",
                    question_text=f"T06 question {index}",
                    option_a=f"q{index} A",
                    option_b=f"q{index} B",
                    option_c=f"q{index} C",
                    option_d=f"q{index} D",
                    correct_option="A",
                    explanation_text="",
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
                    option_letter_mapping=mapping or dict(IDENTITY_MAPPING),
                    mapping_source="test",
                )
            )
        session.add(
            ContentCheck(
                exam_paper_id=paper.id,
                batch_id=batch.id,
                is_passed=check_passed,
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
        session.flush()
        return batch, [question.id for question in questions]

    def build_paper(
        *,
        expected=25,
        count=25,
        visible=True,
        check_passed=True,
        mapping=None,
        write_audio=True,
    ):
        tag = uuid.uuid4().hex[:12]
        with SessionLocal() as session:
            audio = _new_audio(session, tag)
            paper = ExamPaper(
                exam_paper_code=f"T06_{tag}",
                exam_level="CET4",
                exam_year=2025,
                exam_month=6,
                paper_set=1,
                playback_audio_id=audio.id,
                expected_question_count=expected,
                expected_question_count_source={"kind": "test"},
            )
            session.add(paper)
            session.flush()
            batch, question_ids = _add_batch(
                session,
                paper,
                audio,
                tag=tag,
                count=count,
                visible=visible,
                check_passed=check_passed,
                mapping=mapping,
            )
            session.commit()
            paper_id = paper.id
            audio_id = audio.id
            batch_id = batch.id
        audio_path = audio_dir / f"t06_{tag}.m4a"
        if write_audio:
            audio_path.write_bytes(b"T06-TEST-AUDIO")
        state.papers.append(paper_id)
        state.audio.append(audio_id)
        state.files.append(audio_path)
        return SimpleNamespace(
            paper_id=paper_id,
            batch_id=batch_id,
            question_ids=question_ids,
            audio_path=audio_path,
            tag=tag,
        )

    def build_paper_with_old_batch(*, old_count=25, new_count=25):
        tag = uuid.uuid4().hex[:12]
        with SessionLocal() as session:
            audio = _new_audio(session, tag)
            paper = ExamPaper(
                exam_paper_code=f"T06_{tag}",
                exam_level="CET4",
                exam_year=2025,
                exam_month=6,
                paper_set=1,
                playback_audio_id=audio.id,
                expected_question_count=new_count,
                expected_question_count_source={"kind": "test"},
            )
            session.add(paper)
            session.flush()
            _old_batch, old_ids = _add_batch(
                session,
                paper,
                audio,
                tag=f"{tag}_old",
                is_current=False,
                count=old_count,
            )
            new_batch, new_ids = _add_batch(
                session,
                paper,
                audio,
                tag=f"{tag}_new",
                is_current=True,
                count=new_count,
            )
            session.commit()
            paper_id = paper.id
            audio_id = audio.id
            new_batch_id = new_batch.id
        audio_path = audio_dir / f"t06_{tag}.m4a"
        audio_path.write_bytes(b"T06-TEST-AUDIO")
        state.papers.append(paper_id)
        state.audio.append(audio_id)
        state.files.append(audio_path)
        return SimpleNamespace(
            paper_id=paper_id,
            batch_id=new_batch_id,
            old_question_ids=old_ids,
            new_question_ids=new_ids,
        )

    yield SimpleNamespace(
        build_paper=build_paper,
        build_paper_with_old_batch=build_paper_with_old_batch,
        settings=settings,
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


# --------------------------------------------------------------------------- #
# T06-A1：可访问试卷完整提交
# --------------------------------------------------------------------------- #
def test_a1_full_submission(client, student_token, api_data):
    content = api_data.build_paper()

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["msg"] == "提交成功"
    data = body["data"]
    assert set(data) == {
        "attempt_code",
        "exam_paper_id",
        "submitted_at",
        "question_count",
        "correct_count",
        "correct_rate",
        "practice_score",
    }
    assert data["exam_paper_id"] == content.paper_id
    assert data["question_count"] == 25
    assert data["correct_count"] == 25
    assert data["correct_rate"] == 100
    assert data["practice_score"] == {
        "available": True,
        "value": 249,
        "max": 249,
        "label": "练习估分，非官方成绩",
        "reason": None,
    }
    assert len(data["attempt_code"]) == 36
    assert data["submitted_at"].endswith("Z")

    attempts, answers, markers = _db_counts(content.paper_id)
    assert (attempts, answers, markers) == (1, 25, 0)


# --------------------------------------------------------------------------- #
# T06-A2：部分作答 / 空 answers（独立夹具）
# --------------------------------------------------------------------------- #
def test_a2_partial_and_empty_answers(client, student_token, api_data):
    first = api_data.build_paper()
    second = api_data.build_paper()

    partial = _post(
        client,
        first.paper_id,
        _payload(first.question_ids, answered=first.question_ids[:10]),
        key=_key(),
        token=student_token,
    )
    empty = _post(
        client,
        second.paper_id,
        _payload(second.question_ids, answered=[]),
        key=_key(),
        token=student_token,
    )

    assert partial.status_code == 200, partial.text
    assert partial.json()["data"]["correct_count"] == 10
    assert partial.json()["data"]["correct_rate"] == 40
    assert empty.status_code == 200, empty.text
    assert empty.json()["data"]["correct_count"] == 0
    assert empty.json()["data"]["correct_rate"] == 0
    assert empty.json()["data"]["practice_score"]["value"] == 0

    _, answers, _ = _db_counts(second.paper_id)
    assert answers == 25
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        null_selected = session.execute(
            text(
                "SELECT count(*) FROM attempt_answers a "
                "JOIN attempts t ON t.id = a.attempt_id "
                "WHERE t.exam_paper_id = :paper AND a.selected_option IS NULL"
            ),
            {"paper": second.paper_id},
        ).scalar_one()
    assert null_selected == 25


# --------------------------------------------------------------------------- #
# T06-A3：同键同内容回放
# --------------------------------------------------------------------------- #
def test_a3_same_key_replay_returns_same_attempt(client, student_token, api_data):
    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    key = _key()

    first = _post(client, content.paper_id, payload, key=key, token=student_token)
    second = _post(client, content.paper_id, payload, key=key, token=student_token)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert (
        first.json()["data"]["attempt_code"]
        == second.json()["data"]["attempt_code"]
    )
    assert _db_counts(content.paper_id)[0] == 1


# --------------------------------------------------------------------------- #
# T06-A4：同键不同内容 / 换卷 / 换新键限次
# --------------------------------------------------------------------------- #
def test_a4_key_conflict_and_limit(client, student_token, api_data):
    paper_a = api_data.build_paper()
    paper_b = api_data.build_paper()
    key = _key()
    payload_a = _payload(paper_a.question_ids)

    assert (
        _post(client, paper_a.paper_id, payload_a, key=key, token=student_token)
        .status_code
        == 200
    )

    other_answers = _payload(
        paper_a.question_ids, answered=paper_a.question_ids[:5]
    )
    conflict = _post(
        client, paper_a.paper_id, other_answers, key=key, token=student_token
    )
    assert conflict.status_code == 400, conflict.text
    assert conflict.json()["msg"] == "提交键已用于其他提交，请使用新键"
    attempts, _, markers = _db_counts(paper_a.paper_id)
    assert (attempts, markers) == (1, 0)

    limited = _post(
        client, paper_a.paper_id, payload_a, key=_key(), token=student_token
    )
    assert limited.status_code == 400, limited.text
    assert limited.json()["msg"] == "本轮同一试卷仅允许提交一次"
    assert _db_counts(paper_a.paper_id)[0] == 1

    other_paper_same_key = _post(
        client, paper_b.paper_id, _payload(paper_b.question_ids), key=key, token=student_token
    )
    assert other_paper_same_key.status_code == 400
    assert other_paper_same_key.json()["msg"] == "提交键已用于其他提交，请使用新键"

    success_b = _post(
        client,
        paper_b.paper_id,
        _payload(paper_b.question_ids),
        key=_key(),
        token=student_token,
    )
    assert success_b.status_code == 200, success_b.text


# --------------------------------------------------------------------------- #
# T06-A5：同卷不同键第二次 → E08
# --------------------------------------------------------------------------- #
def test_a5_same_paper_new_key_is_limited(client, student_token, api_data):
    content = api_data.build_paper()
    payload = _payload(content.question_ids)

    first = _post(client, content.paper_id, payload, key=_key(), token=student_token)
    second = _post(client, content.paper_id, payload, key=_key(), token=student_token)

    assert first.status_code == 200
    assert second.status_code == 400, second.text
    assert second.json()["msg"] == "本轮同一试卷仅允许提交一次"
    assert _db_counts(content.paper_id)[0] == 1


# --------------------------------------------------------------------------- #
# T06-A6：取消可见 → 404 + 标记；恢复后旧键仍 404、新键成功
# --------------------------------------------------------------------------- #
def test_a6_invisible_paper_writes_marker_and_blocks_old_key(
    client, student_token, api_data
):
    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    key = _key()
    _set_visible(content.paper_id, content.batch_id, False)

    rejected = _post(client, content.paper_id, payload, key=key, token=student_token)
    assert rejected.status_code == 404, rejected.text
    assert rejected.json()["msg"] == "资源不存在"
    attempts, answers, markers = _db_counts(content.paper_id)
    assert (attempts, answers, markers) == (0, 0, 1)
    assert _marker_kinds(content.paper_id) == ["paper_not_accessible"]

    _set_visible(content.paper_id, content.batch_id, True)
    replay = _post(client, content.paper_id, payload, key=key, token=student_token)
    assert replay.status_code == 404, replay.text
    assert _db_counts(content.paper_id)[2] == 1

    fresh = _post(
        client, content.paper_id, payload, key=_key(), token=student_token
    )
    assert fresh.status_code == 200, fresh.text


# --------------------------------------------------------------------------- #
# T06-A7：加载后换批 → 400 E04 + version 标记
# --------------------------------------------------------------------------- #
def test_a7_old_batch_writes_version_marker(client, student_token, api_data):
    content = api_data.build_paper_with_old_batch()
    old_payload = _payload(content.old_question_ids, answered=[])
    key = _key()

    rejected = _post(
        client, content.paper_id, old_payload, key=key, token=student_token
    )
    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["msg"] == "内容已更新，请重新作答"
    attempts, answers, markers = _db_counts(content.paper_id)
    assert (attempts, answers, markers) == (0, 0, 1)
    assert _marker_kinds(content.paper_id) == ["content_version_mismatch"]

    replay = _post(
        client, content.paper_id, old_payload, key=key, token=student_token
    )
    assert replay.status_code == 400
    assert replay.json()["msg"] == "内容已更新，请重新作答"

    fresh = _post(
        client,
        content.paper_id,
        _payload(content.new_question_ids),
        key=_key(),
        token=student_token,
    )
    assert fresh.status_code == 200, fresh.text


# --------------------------------------------------------------------------- #
# T06-A8：管理员 403；无 token 401（即使目标不存在）
# --------------------------------------------------------------------------- #
def test_a8_role_and_auth_order(client, admin_token, student_token, api_data):
    content = api_data.build_paper()
    payload = _payload(content.question_ids)

    admin = _post(client, content.paper_id, payload, key=_key(), token=admin_token)
    assert admin.status_code == 403, admin.text
    assert admin.json()["msg"] == "没有访问该接口的权限：需要学生角色"

    no_token = _post(client, content.paper_id, payload, key=_key())
    assert no_token.status_code == 401, no_token.text

    missing_paper = _post(client, 2**62, payload, key=_key())
    assert missing_paper.status_code == 401, missing_paper.text


# --------------------------------------------------------------------------- #
# T06-A9：提交前失败 / COMMIT 未知（已提交、未提交）/ 响应丢失
# --------------------------------------------------------------------------- #
def test_a9_pre_commit_failure_leaves_no_rows(
    client, student_token, api_data, monkeypatch
):
    import app.services.attempts as service

    content = api_data.build_paper()

    def _fail(*args, **kwargs):
        raise OperationalError("INSERT failed", {}, Exception("boom"))

    monkeypatch.setattr(service, "insert_attempt_with_answers", _fail)
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 500, response.text
    assert response.json()["msg"] == "服务器内部错误"
    assert _db_counts(content.paper_id) == (0, 0, 0)


def test_a9_commit_unknown_but_persisted_replays(
    client, student_token, api_data, monkeypatch
):
    from sqlalchemy.orm import Session

    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    key = _key()
    real_commit = Session.commit
    state = {"raised": False}

    def _flaky_commit(self):
        if not state["raised"]:
            state["raised"] = True
            real_commit(self)
            raise OperationalError("connection lost", {}, Exception("synthetic"))
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", _flaky_commit)
    first = _post(client, content.paper_id, payload, key=key, token=student_token)
    monkeypatch.setattr(Session, "commit", real_commit)

    assert first.status_code == 200, first.text
    assert _db_counts(content.paper_id)[0] == 1
    retry = _post(client, content.paper_id, payload, key=key, token=student_token)
    assert retry.status_code == 200
    assert retry.json()["data"]["attempt_code"] == first.json()["data"]["attempt_code"]


def test_a9_commit_not_persisted_retries_current_state(
    client, student_token, api_data, monkeypatch
):
    from sqlalchemy.orm import Session

    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    key = _key()
    real_commit = Session.commit
    state = {"raised": False}

    def _flaky_commit(self):
        if not state["raised"]:
            state["raised"] = True
            raise OperationalError("connection lost", {}, Exception("synthetic"))
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", _flaky_commit)
    response = _post(client, content.paper_id, payload, key=key, token=student_token)
    monkeypatch.setattr(Session, "commit", real_commit)

    assert response.status_code == 200, response.text
    assert _db_counts(content.paper_id)[0] == 1


def test_a9_failure_then_paper_offline_returns_404_marker(
    client, student_token, api_data, monkeypatch
):
    import app.services.attempts as service

    content = api_data.build_paper()
    state = {"first": True}

    def _fail_first(session, attempt, answers):
        if state["first"]:
            state["first"] = False
            _set_visible(content.paper_id, content.batch_id, False)
            raise OperationalError("insert failed", {}, Exception("boom"))
        raise OperationalError("insert failed", {}, Exception("boom"))

    monkeypatch.setattr(service, "insert_attempt_with_answers", _fail_first)
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 404, response.text
    assert _db_counts(content.paper_id) == (0, 0, 1)


# --------------------------------------------------------------------------- #
# T06-A10：同键并发（两个 TestClient 线程）→ 仅 1 条、均 200 同一 code
# --------------------------------------------------------------------------- #
def test_a10_concurrent_same_key_single_attempt(
    client, student_token, api_data
):
    from fastapi.testclient import TestClient

    from app.main import app

    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    key = _key()
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=10)
                results.append(
                    _post(
                        thread_client,
                        content.paper_id,
                        payload,
                        key=key,
                        token=student_token,
                    )
                )
        except BaseException as exc:  # noqa: BLE001 - 线程内失败带回主线程
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(results) == 2
    assert all(response.status_code == 200 for response in results)
    codes = {response.json()["data"]["attempt_code"] for response in results}
    assert len(codes) == 1
    assert _db_counts(content.paper_id) == (1, 25, 0)


# --------------------------------------------------------------------------- #
# T06-A11：响应不含答案/解析/正文/逐题/内部 ID
# --------------------------------------------------------------------------- #
def test_a11_response_has_no_protected_fields(client, student_token, api_data):
    content = api_data.build_paper()
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 200, response.text
    text_body = response.text
    for marker in (
        "explanation",
        "question_id",
        "selected_option",
        "correct_option",
        "is_correct",
        "question_text",
        "option_a",
        '"id"',
    ):
        assert marker not in text_body
    assert set(response.json()["data"]) == {
        "attempt_code",
        "exam_paper_id",
        "submitted_at",
        "question_count",
        "correct_count",
        "correct_rate",
        "practice_score",
    }


# --------------------------------------------------------------------------- #
# T06-A12：路由级契约 / 鉴权先于 body
# --------------------------------------------------------------------------- #
def test_a12_path_range_and_body_types(client, student_token, api_data):
    content = api_data.build_paper()
    valid_body = _payload(content.question_ids)

    for bad_path in (0, -1, 2**63):
        response = _post(
            client, bad_path, valid_body, key=_key(), token=student_token
        )
        assert response.status_code == 422, (bad_path, response.text)

    for bad_id in ("1", 1.0, True):
        payload = {
            "loaded_question_ids": [bad_id],
            "answers": [],
        }
        response = _post(
            client, content.paper_id, payload, key=_key(), token=student_token
        )
        assert response.status_code == 422, (bad_id, response.text)


def test_a12_idempotency_key_errors(client, student_token, api_data):
    content = api_data.build_paper()
    payload = _payload(content.question_ids)

    missing = _post(client, content.paper_id, payload, token=student_token)
    assert missing.status_code == 400, missing.text
    assert missing.json()["msg"] == "缺少或非法的提交键 Idempotency-Key"

    for bad_key in ("not-a-uuid", "0" * 64, "0f5c2a1e-9d4b-1f6a-9c77-2b1e8a3d5c40"):
        response = _post(
            client, content.paper_id, payload, key=bad_key, token=student_token
        )
        assert response.status_code == 400, (bad_key, response.text)
        assert response.json()["msg"] == "缺少或非法的提交键 Idempotency-Key"


def test_a12_body_contract_errors(client, student_token, api_data):
    content = api_data.build_paper()

    missing_answers = _post(
        client,
        content.paper_id,
        {"loaded_question_ids": content.question_ids},
        key=_key(),
        token=student_token,
    )
    assert missing_answers.status_code == 422, missing_answers.text
    assert missing_answers.json()["msg"] == "请求参数校验失败"

    empty_loaded = _post(
        client,
        content.paper_id,
        {"loaded_question_ids": [], "answers": []},
        key=_key(),
        token=student_token,
    )
    assert empty_loaded.status_code == 400, empty_loaded.text
    assert empty_loaded.json()["msg"].startswith("提交内容不合法：")


def test_a12_auth_precedes_body_validation(client, api_data):
    content = api_data.build_paper()

    no_token_bad_body = _post(
        client,
        content.paper_id,
        {"loaded_question_ids": [content.question_ids[0]]},
        key=_key(),
    )
    assert no_token_bad_body.status_code == 401, no_token_bad_body.text

    no_token_missing_paper = _post(client, 2**62, _payload([1]), key=_key())
    assert no_token_missing_paper.status_code == 401, no_token_missing_paper.text


# --------------------------------------------------------------------------- #
# T06-A13：T04 移交的 HTTP/标记断言
# --------------------------------------------------------------------------- #
def test_a13_missing_paper_404_with_marker(client, student_token, api_data):
    response = _post(
        client, 2**62, _payload([1]), key=_key(), token=student_token
    )
    assert response.status_code == 404, response.text
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        kinds = session.execute(
            text(
                "SELECT rejection_kind FROM attempt_rejections "
                "WHERE exam_paper_id = :paper"
            ),
            {"paper": 2**62},
        ).scalars().all()
    assert kinds == ["paper_not_accessible"]


def test_a13_audio_missing_404_without_marker(client, student_token, api_data):
    content = api_data.build_paper(write_audio=False)
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 404, response.text
    assert _db_counts(content.paper_id) == (0, 0, 0)


def test_a13_mapping_invalid_404_without_marker(client, student_token, api_data):
    content = api_data.build_paper(
        mapping={"A": "A", "B": "A", "C": "C", "D": "D"}
    )
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 404, response.text
    assert _db_counts(content.paper_id) == (0, 0, 0)


def test_a13_foreign_identity_400_without_marker(client, student_token, api_data):
    first = api_data.build_paper()
    second = api_data.build_paper()
    response = _post(
        client,
        first.paper_id,
        _payload(second.question_ids),
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 400, response.text
    assert response.json()["msg"].startswith("提交内容不合法：")
    assert _db_counts(first.paper_id) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# T06-A14：实现自测（6.3a）——双会话竞争限次；负向对照证明锁的作用
# --------------------------------------------------------------------------- #
def test_a14_limit_race_single_attempt(student_token, api_data, monkeypatch):
    import app.services.attempts as service

    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    barrier = threading.Barrier(2)
    real_lock = service.lock_student_paper
    results = []
    errors = []

    def synced_lock(db, student_id, paper_id):
        barrier.wait(timeout=10)
        return real_lock(db, student_id, paper_id)

    monkeypatch.setattr(service, "lock_student_paper", synced_lock)

    def worker(key):
        try:
            results.append(
                _thread_request(
                    content.paper_id, payload, key=key, token=student_token
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(_key(),)) for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    statuses = sorted(response.status_code for response in results)
    assert statuses == [200, 400]
    limited = next(r for r in results if r.status_code == 400)
    assert limited.json()["msg"] == "本轮同一试卷仅允许提交一次"
    assert _db_counts(content.paper_id) == (1, 25, 0)


def test_a14_without_limit_lock_race_can_duplicate(student_token, api_data, monkeypatch):
    import app.services.attempts as service

    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    barrier = threading.Barrier(2)
    results = []
    errors = []
    real_insert = service.insert_attempt_with_answers

    def _noop_lock(db, student_id, paper_id):
        return None

    def synced_insert(db, attempt, answers):
        result = real_insert(db, attempt, answers)
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(service, "lock_student_paper", _noop_lock)
    monkeypatch.setattr(service, "insert_attempt_with_answers", synced_insert)

    def worker(key):
        try:
            results.append(
                _thread_request(
                    content.paper_id, payload, key=key, token=student_token
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(_key(),)) for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert sorted(response.status_code for response in results) == [200, 200]
    assert _db_counts(content.paper_id)[0] == 2  # 负向对照：缺锁时出现重复


# --------------------------------------------------------------------------- #
# T06-A15：安全日志（注入敏感标记，捕获服务与全局最终日志）
# --------------------------------------------------------------------------- #
def test_a15_logs_and_response_do_not_leak_sensitive_markers(
    client, student_token, api_data, monkeypatch, caplog
):
    import app.services.attempts as service

    content = api_data.build_paper()
    secret = "SECRET_ANSWER_XYZ"
    explanation = "SECRET_EXPLANATION_XYZ"
    body = "SECRET_BODY_XYZ"

    def _leaky(*args, **kwargs):
        raise OperationalError(
            f"INSERT ... {secret} ... {explanation} ... {body}",
            {},
            Exception(f"DETAIL: {secret} {explanation} {body}"),
        )

    monkeypatch.setattr(service, "insert_attempt_with_answers", _leaky)
    with caplog.at_level("WARNING"):
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )

    assert response.status_code == 500, response.text
    assert secret not in response.text
    assert explanation not in response.text
    assert body not in response.text
    assert secret not in caplog.text
    assert explanation not in caplog.text
    assert body not in caplog.text
    assert "stage=" in caplog.text
    assert "student_id=" in caplog.text
    assert "error_type=" in caplog.text
    assert _db_counts(content.paper_id) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# 测试辅助：线程内独立 TestClient
# --------------------------------------------------------------------------- #
def _thread_request(paper_id, payload, *, key, token):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as thread_client:
        return _post(thread_client, paper_id, payload, key=key, token=token)


# --------------------------------------------------------------------------- #
# A9 补充：恢复期重读失败 → 安全 500；A15 补充：rollback/重读失败分支脱敏
# --------------------------------------------------------------------------- #
def test_a9_reread_failure_returns_500(
    client, student_token, api_data, monkeypatch
):
    import app.services.attempts as service

    content = api_data.build_paper()
    real_resolve = service.resolve_existing
    real_insert = service.insert_attempt_with_answers
    state = {"calls": 0}

    def _flaky_resolve(db, student_id, attempt_key, fingerprint):
        state["calls"] += 1
        if state["calls"] == 2:
            raise OperationalError("reread failed", {}, Exception("synthetic"))
        return real_resolve(db, student_id, attempt_key, fingerprint)

    def _fail_insert(db, attempt, answers):
        raise OperationalError("insert failed", {}, Exception("boom"))

    monkeypatch.setattr(service, "resolve_existing", _flaky_resolve)
    monkeypatch.setattr(service, "insert_attempt_with_answers", _fail_insert)

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 500, response.text
    assert response.json()["msg"] == "服务器内部错误"
    assert _db_counts(content.paper_id) == (0, 0, 0)


def test_a15_rollback_failure_logs_safely(
    client, student_token, api_data, monkeypatch, caplog
):
    from sqlalchemy.orm import Session

    import app.services.attempts as service

    content = api_data.build_paper()
    secret = "SECRET_ROLLBACK_XYZ"
    real_rollback = Session.rollback
    state = {"raised": False}

    def _fail_first_rollback(self):
        if not state["raised"]:
            state["raised"] = True
            raise RuntimeError(f"rollback detail {secret}")
        return real_rollback(self)

    def _fail_insert(db, attempt, answers):
        raise OperationalError(f"insert {secret}", {}, Exception(secret))

    monkeypatch.setattr(Session, "rollback", _fail_first_rollback)
    monkeypatch.setattr(service, "insert_attempt_with_answers", _fail_insert)

    with caplog.at_level("WARNING"):
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )

    assert response.status_code == 500, response.text
    assert secret not in response.text
    assert secret not in caplog.text
    assert "stage=" in caplog.text
    assert _db_counts(content.paper_id) == (0, 0, 0)


def test_a15_reread_failure_logs_safely(
    client, student_token, api_data, monkeypatch, caplog
):
    import app.services.attempts as service

    content = api_data.build_paper()
    secret = "SECRET_REREAD_XYZ"
    real_resolve = service.resolve_existing
    state = {"calls": 0}

    def _flaky_resolve(db, student_id, attempt_key, fingerprint):
        state["calls"] += 1
        if state["calls"] == 2:
            raise OperationalError(
                f"reread {secret}", {}, Exception(f"DETAIL {secret}")
            )
        return real_resolve(db, student_id, attempt_key, fingerprint)

    def _fail_insert(db, attempt, answers):
        raise OperationalError("insert failed", {}, Exception("boom"))

    monkeypatch.setattr(service, "resolve_existing", _flaky_resolve)
    monkeypatch.setattr(service, "insert_attempt_with_answers", _fail_insert)

    with caplog.at_level("WARNING"):
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )

    assert response.status_code == 500, response.text
    assert secret not in response.text
    assert secret not in caplog.text
    assert "reread_failure" in caplog.text
    assert "error_type=" in caplog.text
    assert _db_counts(content.paper_id) == (0, 0, 0)
