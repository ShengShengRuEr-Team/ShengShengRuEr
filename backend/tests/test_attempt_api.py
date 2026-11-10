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
        correct_base="A",
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
                    correct_option=correct_base,
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
        correct_base="A",
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
                correct_base=correct_base,
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
    attempt_key = _key()

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
            key=attempt_key,
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
    assert attempt_key not in caplog.text
    assert attempt_key not in response.text
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


# --------------------------------------------------------------------------- #
# T08 矩阵补全用例（M-01/M-03a/M-04/M-06/M-11/M-12a/M-14/M-25/M-27/M-29/
# M-29c/M-33/M-34/M-37/M-38/T08-A8）
# --------------------------------------------------------------------------- #
def _db_scalar(query, params=None):
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        return session.execute(text(query), params or {}).scalar()


def _db_all(query, params):
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        return session.execute(text(query), params).all()


def _update_sql(query, params):
    from app.db.base import SessionLocal

    with SessionLocal() as session:
        session.execute(text(query), params)
        session.commit()


# M-01 / V-01：24/25、错题在听力篇章 → 96 / 235 / breakdown 7/8/10
def test_m01_24_of_25_lecture_wrong_exact_values(client, student_token, api_data):
    content = api_data.build_paper()
    answers = [
        {
            "question_id": qid,
            "selected_option": "B" if index == 24 else "A",
        }
        for index, qid in enumerate(content.question_ids)
    ]
    payload = {
        "loaded_question_ids": content.question_ids,
        "answers": answers,
    }

    response = _post(
        client, content.paper_id, payload, key=_key(), token=student_token
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["question_count"] == 25
    assert data["correct_count"] == 24
    assert data["correct_rate"] == 96
    assert data["practice_score"]["available"] is True
    assert data["practice_score"]["value"] == 235
    assert "非官方成绩" in data["practice_score"]["label"]

    breakdown = _db_scalar(
        "SELECT score_breakdown FROM attempts WHERE exam_paper_id = :paper",
        {"paper": content.paper_id},
    )
    groups = {group["passage_type"]: group for group in breakdown["groups"]}
    assert groups["短篇新闻"]["question_count"] == 7
    assert groups["长对话"]["question_count"] == 8
    assert groups["听力篇章"]["question_count"] == 10
    assert groups["听力篇章"]["correct_count"] == 9
    assert breakdown["rule"] == "cet-listening-249-v1"
    assert _db_counts(content.paper_id) == (1, 25, 0)


# M-03a / V-03：重排题按原卷字母判分，库内快照也是原卷字母
def test_m03a_reordered_options_grade_in_paper_space(client, student_token, api_data):
    mapping = {"A": "B", "B": "A", "C": "C", "D": "D"}
    right = api_data.build_paper(mapping=mapping, correct_base="B")
    wrong = api_data.build_paper(mapping=mapping, correct_base="B")

    right_response = _post(
        client,
        right.paper_id,
        _payload(right.question_ids),
        key=_key(),
        token=student_token,
    )
    wrong_payload = {
        "loaded_question_ids": wrong.question_ids,
        "answers": [
            {"question_id": qid, "selected_option": "B"}
            for qid in wrong.question_ids
        ],
    }
    wrong_response = _post(
        client,
        wrong.paper_id,
        wrong_payload,
        key=_key(),
        token=student_token,
    )

    assert right_response.status_code == 200, right_response.text
    assert right_response.json()["data"]["correct_count"] == 25
    # 题库答案 B 在映射 A<-B 下对应原卷字母 A
    row = _db_all(
        "SELECT a.correct_option, a.selected_option FROM attempt_answers a "
        "JOIN attempts t ON t.id = a.attempt_id "
        "WHERE t.exam_paper_id = :paper LIMIT 1",
        {"paper": right.paper_id},
    )[0]
    assert tuple(row) == ("A", "A")

    assert wrong_response.status_code == 200, wrong_response.text
    assert wrong_response.json()["data"]["correct_count"] == 0
    row = _db_all(
        "SELECT a.correct_option, a.selected_option FROM attempt_answers a "
        "JOIN attempts t ON t.id = a.attempt_id "
        "WHERE t.exam_paper_id = :paper LIMIT 1",
        {"paper": wrong.paper_id},
    )[0]
    assert tuple(row) == ("A", "B")


# M-04 / V-04：非标准卷/题型缺失/类型数量不符 → available=false、value=null
def test_m04_practice_unavailable_reasons(client, student_token, api_data):
    small = api_data.build_paper(expected=1, count=1)
    missing = api_data.build_paper()
    mismatched = api_data.build_paper()
    _update_sql(
        "UPDATE passages SET passage_type = '' WHERE batch_id = :batch",
        {"batch": missing.batch_id},
    )
    _update_sql(
        "UPDATE passages SET passage_type = '短篇新闻' WHERE batch_id = :batch",
        {"batch": mismatched.batch_id},
    )

    cases = (
        (small, "not_standard_25"),
        (missing, "question_type_missing"),
        (mismatched, "type_count_mismatch"),
    )
    for content, reason in cases:
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )
        assert response.status_code == 200, response.text
        practice = response.json()["data"]["practice_score"]
        assert practice["available"] is False
        assert practice["value"] is None
        assert practice["reason"] == reason
        assert practice["max"] == 249
        assert "非官方成绩" in practice["label"]


# M-06 / V-07a：换批发生在加载前 → 按新批提交成功，落库 import_batch_id 为新批
def test_m06_new_batch_loaded_before_submit(client, student_token, api_data):
    content = api_data.build_paper_with_old_batch()

    response = _post(
        client,
        content.paper_id,
        _payload(content.new_question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 200, response.text
    assert _db_counts(content.paper_id) == (1, 25, 0)
    batch_id = _db_scalar(
        "SELECT import_batch_id FROM attempts WHERE exam_paper_id = :paper",
        {"paper": content.paper_id},
    )
    assert batch_id == content.batch_id


# M-11/M-30：标注审核/内容完整度状态变化不影响提交准入
def test_m11_annotation_state_change_does_not_affect_access(
    client, student_token, api_data
):
    content = api_data.build_paper()
    _update_sql(
        "UPDATE questions SET review_status = '待审核', content_state = '停用' "
        "WHERE batch_id = :batch",
        {"batch": content.batch_id},
    )
    _update_sql(
        "UPDATE passages SET review_status = '需修改' WHERE batch_id = :batch",
        {"batch": content.batch_id},
    )

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 200, response.text
    assert _db_counts(content.paper_id) == (1, 25, 0)


# M-12a / T08-A6：提交后改题库，attempt_answers 快照不漂移
def test_m12a_snapshot_does_not_drift(client, student_token, api_data):
    content = api_data.build_paper()
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 200, response.text

    snapshot_query = (
        "SELECT a.question_no, a.question_text, a.option_a, a.correct_option, "
        "a.explanation_text, a.selected_option, a.is_correct "
        "FROM attempt_answers a JOIN attempts t ON t.id = a.attempt_id "
        "WHERE t.exam_paper_id = :paper ORDER BY a.question_no"
    )
    before = _db_all(snapshot_query, {"paper": content.paper_id})

    _update_sql(
        "UPDATE questions SET question_text = 'CHANGED', option_a = 'CHANGED', "
        "correct_option = 'D', explanation_text = 'CHANGED' "
        "WHERE batch_id = :batch",
        {"batch": content.batch_id},
    )
    _update_sql(
        "UPDATE presentations SET option_letter_mapping = "
        "'{\"A\":\"B\",\"B\":\"A\",\"C\":\"C\",\"D\":\"D\"}'::jsonb "
        "WHERE batch_id = :batch",
        {"batch": content.batch_id},
    )

    after = _db_all(snapshot_query, {"paper": content.paper_id})
    assert after == before
    assert _db_counts(content.paper_id) == (1, 25, 0)


# M-14 / V-R7：提交时间库内为 UTC，接口返回 ISO 8601 UTC
def test_m14_submitted_at_is_utc(client, student_token, api_data):
    from datetime import datetime, timedelta

    content = api_data.build_paper()
    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 200, response.text
    raw = response.json()["data"]["submitted_at"]
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    assert parsed.utcoffset() == timedelta(0)

    stored = _db_scalar(
        "SELECT submitted_at FROM attempts WHERE exam_paper_id = :paper",
        {"paper": content.paper_id},
    )
    assert stored.tzinfo is not None
    assert stored.utcoffset() == timedelta(0)
    assert abs((stored - parsed).total_seconds()) < 5


# M-25：不存在/重复题目身份 → 400 E07，不落库、无标记
def test_m25_identity_variants(client, student_token, api_data):
    content = api_data.build_paper()

    nonexistent = _post(
        client,
        content.paper_id,
        _payload(
            [*content.question_ids[:-1], 2**62], answered=[]
        ),
        key=_key(),
        token=student_token,
    )
    duplicated = _post(
        client,
        content.paper_id,
        _payload([*content.question_ids, content.question_ids[0]], answered=[]),
        key=_key(),
        token=student_token,
    )

    for response in (nonexistent, duplicated):
        assert response.status_code == 400, response.text
        assert response.json()["msg"].startswith("提交内容不合法：")
    assert _db_counts(content.paper_id) == (0, 0, 0)


# M-27：answers 内同一 question_id 重复 → 400 E07
def test_m27_duplicate_answer_question_id(client, student_token, api_data):
    content = api_data.build_paper()
    payload = {
        "loaded_question_ids": content.question_ids,
        "answers": [
            {"question_id": content.question_ids[0], "selected_option": "A"},
            {"question_id": content.question_ids[0], "selected_option": "B"},
        ],
    }

    response = _post(
        client, content.paper_id, payload, key=_key(), token=student_token
    )

    assert response.status_code == 400, response.text
    assert response.json()["msg"].startswith("提交内容不合法：")
    assert _db_counts(content.paper_id) == (0, 0, 0)


# M-29：内容检查未通过 → 404 + access 标记
def test_m29_content_check_not_passed(client, student_token, api_data):
    content = api_data.build_paper(visible=True, check_passed=False)

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 404, response.text
    assert _db_counts(content.paper_id) == (0, 0, 1)
    assert _marker_kinds(content.paper_id) == ["paper_not_accessible"]


# M-29c：应有 25 题但删除第 25 题及映射、历史检查仍通过 → 404 E14 无标记
def test_m29c_deleted_last_question_api(client, student_token, api_data):
    content = api_data.build_paper(expected=25, count=24)

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 404, response.text
    assert response.json()["msg"] == "资源不存在"
    assert _db_counts(content.paper_id) == (0, 0, 0)


# M-33 / V-23：提交先于下线 → 成功落库（Event 钩子固定时序）
def test_m33_submit_before_visibility_change_succeeds(
    client, student_token, api_data, monkeypatch
):
    import app.services.attempts as service

    content = api_data.build_paper()
    entered = threading.Event()
    release = threading.Event()
    real_lock = service.lock_student_paper
    result = {}

    def _hooked_lock(db, student_id, paper_id):
        entered.set()
        assert release.wait(timeout=10)
        return real_lock(db, student_id, paper_id)

    monkeypatch.setattr(service, "lock_student_paper", _hooked_lock)

    def worker():
        result["response"] = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=10)
    _set_visible(content.paper_id, content.batch_id, False)
    release.set()
    thread.join(timeout=30)

    assert result["response"].status_code == 200, result["response"].text
    assert _db_counts(content.paper_id) == (1, 25, 0)


# M-33 / V-23：下线先于准入 → 404 + access 标记，无 attempt
def test_m33_visibility_change_before_submit_rejects(
    client, student_token, api_data, monkeypatch
):
    import app.services.attempts as service

    content = api_data.build_paper()
    entered = threading.Event()
    release = threading.Event()
    real_access = service.check_submit_access
    result = {}

    def _hooked_access(db, paper_id):
        entered.set()
        assert release.wait(timeout=10)
        return real_access(db, paper_id)

    monkeypatch.setattr(service, "check_submit_access", _hooked_access)

    def worker():
        result["response"] = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=_key(),
            token=student_token,
        )

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=10)
    _set_visible(content.paper_id, content.batch_id, False)
    release.set()
    thread.join(timeout=30)

    assert result["response"].status_code == 404, result["response"].text
    assert _db_counts(content.paper_id) == (0, 0, 1)


# M-34 / V-08：提交前故障不落半成品；同键重试可成功且仅一条、无标记
def test_m34_pre_commit_failure_retry_succeeds(
    client, student_token, api_data, monkeypatch
):
    import app.services.attempts as service

    content = api_data.build_paper()
    payload = _payload(content.question_ids)
    key = _key()
    real_insert = service.insert_attempt_with_answers
    state = {"calls": 0}

    def _flaky_insert(db, attempt, answers):
        state["calls"] += 1
        if state["calls"] <= 2:  # 首次请求 + 服务内一次恢复重试均失败
            raise OperationalError("insert failed", {}, Exception("boom"))
        return real_insert(db, attempt, answers)

    monkeypatch.setattr(service, "insert_attempt_with_answers", _flaky_insert)
    first = _post(client, content.paper_id, payload, key=key, token=student_token)
    assert first.status_code == 500, first.text
    assert _db_counts(content.paper_id) == (0, 0, 0)

    second = _post(client, content.paper_id, payload, key=key, token=student_token)
    assert second.status_code == 200, second.text
    assert _db_counts(content.paper_id) == (1, 25, 0)


# M-37 / V-05：loaded 为当前批次真子集 → 400 E07
def test_m37_subset_loaded_incomplete(client, student_token, api_data):
    content = api_data.build_paper()

    response = _post(
        client,
        content.paper_id,
        _payload(content.question_ids[:-1], answered=[]),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 400, response.text
    assert response.json()["msg"].startswith("提交内容不合法：")
    assert _db_counts(content.paper_id) == (0, 0, 0)


# M-38：loaded 顺序打乱但集合一致 → 允许
def test_m38_shuffled_loaded_allowed(client, student_token, api_data):
    content = api_data.build_paper()

    response = _post(
        client,
        content.paper_id,
        _payload(list(reversed(content.question_ids))),
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 200, response.text
    assert _db_counts(content.paper_id) == (1, 25, 0)


# T08-A8：attempts 与 attempt_rejections 不得存在同一 (student,key)
def test_t08_a8_no_cross_table_same_key(client, student_token, api_data):
    success_paper = api_data.build_paper()
    rejected_paper = api_data.build_paper()
    success_key = _key()
    rejected_key = _key()

    success = _post(
        client,
        success_paper.paper_id,
        _payload(success_paper.question_ids),
        key=success_key,
        token=student_token,
    )
    assert success.status_code == 200, success.text

    _set_visible(rejected_paper.paper_id, rejected_paper.batch_id, False)
    rejected = _post(
        client,
        rejected_paper.paper_id,
        _payload(rejected_paper.question_ids),
        key=rejected_key,
        token=student_token,
    )
    assert rejected.status_code == 404, rejected.text
    assert _db_counts(rejected_paper.paper_id)[2] == 1

    same_key_rows = _db_scalar(
        "SELECT count(*) FROM attempts a "
        "JOIN attempt_rejections r ON r.student_id = a.student_id "
        "AND r.attempt_key = a.attempt_key"
    )
    assert same_key_rows == 0
    assert (
        _db_scalar(
            "SELECT count(*) FROM attempt_rejections WHERE attempt_key = :key",
            {"key": success_key},
        )
        == 0
    )
    assert (
        _db_scalar(
            "SELECT count(*) FROM attempts WHERE attempt_key = :key",
            {"key": rejected_key},
        )
        == 0
    )


# --------------------------------------------------------------------------- #
# T06 回修：6a 空 loaded 前置判空（先于 6b 准入，不写永久标记）
# --------------------------------------------------------------------------- #
def test_t06_empty_loaded_inaccessible_returns_e07_without_marker(
    client, student_token, api_data
):
    invisible = api_data.build_paper(visible=False)
    empty_payload = {"loaded_question_ids": [], "answers": []}
    invisible_key = _key()
    nonexistent_key = _key()

    invisible_response = _post(
        client,
        invisible.paper_id,
        empty_payload,
        key=invisible_key,
        token=student_token,
    )
    nonexistent_response = _post(
        client, 2**62, empty_payload, key=nonexistent_key, token=student_token
    )

    for response in (invisible_response, nonexistent_response):
        assert response.status_code == 400, response.text
        assert response.json()["msg"] == "提交内容不合法：整卷题目集合不能为空"
    assert _db_counts(invisible.paper_id) == (0, 0, 0)
    for attempt_key in (invisible_key, nonexistent_key):
        assert (
            _db_scalar(
                "SELECT count(*) FROM attempt_rejections WHERE attempt_key = :key",
                {"key": attempt_key},
            )
            == 0
        )
        assert (
            _db_scalar(
                "SELECT count(*) FROM attempts WHERE attempt_key = :key",
                {"key": attempt_key},
            )
            == 0
        )


def test_t06_empty_loaded_accessible_returns_e07_without_marker(
    client, student_token, api_data
):
    content = api_data.build_paper()

    response = _post(
        client,
        content.paper_id,
        {"loaded_question_ids": [], "answers": []},
        key=_key(),
        token=student_token,
    )

    assert response.status_code == 400, response.text
    assert response.json()["msg"] == "提交内容不合法：整卷题目集合不能为空"
    assert _db_counts(content.paper_id) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# T06-A15 回修：commit 分支注入 SECRET 标记；完整 Idempotency-Key 不落日志
# --------------------------------------------------------------------------- #
def test_t06_a15_commit_failure_logs_are_safe(
    client, student_token, api_data, monkeypatch, caplog
):
    from sqlalchemy.orm import Session

    content = api_data.build_paper()
    attempt_key = _key()
    secret = "SECRET_COMMIT_XYZ"
    real_commit = Session.commit

    def _leaky_commit(self):
        raise OperationalError(
            f"COMMIT {secret}", {}, Exception(f"DETAIL {secret}")
        )

    monkeypatch.setattr(Session, "commit", _leaky_commit)
    with caplog.at_level("WARNING"):
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=attempt_key,
            token=student_token,
        )
    monkeypatch.setattr(Session, "commit", real_commit)

    assert response.status_code == 500, response.text
    assert response.json()["msg"] == "服务器内部错误"
    assert secret not in response.text
    assert secret not in caplog.text
    assert attempt_key not in response.text
    assert attempt_key not in caplog.text
    assert "stage=" in caplog.text
    assert "error_type=" in caplog.text
    assert _db_counts(content.paper_id) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# T08 回修：M-24 HTTP 集成矩阵（路径/JSON 类型/缺失 answers → 422）
# --------------------------------------------------------------------------- #
def test_m24_http_validation_matrix(client, student_token, api_data):
    content = api_data.build_paper()
    valid_payload = _payload(content.question_ids)

    for bad_path in (0, -1, 2**63):
        response = _post(
            client, bad_path, valid_payload, key=_key(), token=student_token
        )
        assert response.status_code == 422, (bad_path, response.text)
        assert response.json()["msg"] == "请求参数校验失败"

    for bad_json_id in ("1", 1.0, True):
        payload = {"loaded_question_ids": [bad_json_id], "answers": []}
        response = _post(
            client,
            content.paper_id,
            payload,
            key=_key(),
            token=student_token,
        )
        assert response.status_code == 422, (bad_json_id, response.text)
        assert response.json()["msg"] == "请求参数校验失败"

    missing_answers = {"loaded_question_ids": content.question_ids}
    response = _post(
        client,
        content.paper_id,
        missing_answers,
        key=_key(),
        token=student_token,
    )
    assert response.status_code == 422, response.text
    assert response.json()["msg"] == "请求参数校验失败"
    assert _db_counts(content.paper_id) == (0, 0, 0)

    # selected_option 只接受大写 A–D：E/a → 422，且 422 不落库
    retry_key = _key()
    for bad_letter in ("E", "a"):
        bad_payload = {
            "loaded_question_ids": content.question_ids,
            "answers": [
                {
                    "question_id": content.question_ids[0],
                    "selected_option": bad_letter,
                }
            ],
        }
        bad_response = _post(
            client,
            content.paper_id,
            bad_payload,
            key=retry_key,
            token=student_token,
        )
        assert bad_response.status_code == 422, (bad_letter, bad_response.text)
        assert bad_response.json()["msg"] == "请求参数校验失败"
    assert _db_counts(content.paper_id) == (0, 0, 0)

    # 修正请求后用同一 Idempotency-Key 重试 → 200（422 未进入业务、未落库）
    fixed_response = _post(
        client,
        content.paper_id,
        valid_payload,
        key=retry_key,
        token=student_token,
    )
    assert fixed_response.status_code == 200, fixed_response.text
    assert _db_counts(content.paper_id) == (1, 25, 0)


# --------------------------------------------------------------------------- #
# T06 复审回修：Session.flush 分支日志注入（仓储 insert 内部 flush 失败）
# --------------------------------------------------------------------------- #
def test_t06_a15_flush_failure_logs_are_safe(
    client, student_token, api_data, monkeypatch, caplog
):
    from sqlalchemy.orm import Session

    content = api_data.build_paper()
    attempt_key = _key()
    secret = "SECRET_FLUSH_XYZ"
    real_flush = Session.flush

    def _leaky_flush(self, *args, **kwargs):
        raise OperationalError(
            f"FLUSH {secret}", {}, Exception(f"DETAIL {secret}")
        )

    monkeypatch.setattr(Session, "flush", _leaky_flush)
    with caplog.at_level("WARNING"):
        response = _post(
            client,
            content.paper_id,
            _payload(content.question_ids),
            key=attempt_key,
            token=student_token,
        )
    monkeypatch.setattr(Session, "flush", real_flush)

    assert response.status_code == 500, response.text
    assert response.json() == {
        "code": 500,
        "msg": "服务器内部错误",
        "data": None,
    }
    assert secret not in response.text
    assert secret not in caplog.text
    assert attempt_key not in response.text
    assert attempt_key not in caplog.text
    assert "stage=" in caplog.text
    assert "error_type=" in caplog.text
    assert _db_counts(content.paper_id) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# T08 复审回修：M-12 提交成功后取消可见，只读 SQL 断言记录仍在
# --------------------------------------------------------------------------- #
def test_m12_records_survive_visibility_cancel(client, student_token, api_data):
    content = api_data.build_paper()
    payload = _payload(content.question_ids)

    submitted = _post(
        client, content.paper_id, payload, key=_key(), token=student_token
    )
    assert submitted.status_code == 200, submitted.text
    attempt_code = submitted.json()["data"]["attempt_code"]
    assert _db_counts(content.paper_id) == (1, 25, 0)

    _set_visible(content.paper_id, content.batch_id, False)

    attempts = _db_scalar(
        "SELECT count(*) FROM attempts WHERE exam_paper_id = :paper",
        {"paper": content.paper_id},
    )
    answers = _db_scalar(
        "SELECT count(*) FROM attempt_answers a "
        "JOIN attempts t ON t.id = a.attempt_id "
        "WHERE t.exam_paper_id = :paper",
        {"paper": content.paper_id},
    )
    stored_code = _db_scalar(
        "SELECT attempt_code FROM attempts WHERE exam_paper_id = :paper",
        {"paper": content.paper_id},
    )
    assert attempts == 1
    assert answers == 25
    assert stored_code == attempt_code
