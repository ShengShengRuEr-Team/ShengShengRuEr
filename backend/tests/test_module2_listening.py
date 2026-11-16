"""模块二接口、权限与可见性用例（自包含小样例，不依赖真实真题文件）。

在独立测试库上走真实迁移与导入工具，验证：学生可见性三态、字段裁剪、
管理员权限、音频 Range、重复导入幂等。真实 25 题样例由
scripts/acceptance_module2.py 在开发库上另行验收。
"""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_headers

# 注意：本文件**不得**在模块级 import app.* 。
# pytest 的收集阶段会先导入测试模块，而 tests/conftest.py 是在 session 级夹具里
# 才把 DATABASE_URL 指向测试库；若此处提前 import app.db.base，engine 会绑定到
# 开发库，随后夹具的 DROP SCHEMA 就会清掉开发库数据。app.* 一律在夹具/用例内部
# 延迟导入。

PAPER_CODE = "TEST_M2_001"
AUDIO_KEY = "test_m2_audio.m4a"


def _sample_payload(audio_hash: str) -> dict:
    return {
        "meta": {"source_xlsx_sha256": "test"},
        "exam_paper": {
            "_src_id": 1, "exam_paper_code": PAPER_CODE, "exam_level": "CET4",
            "exam_year": 2025, "exam_month": 6, "paper_set": 1,
            "content_scope": "listening", "playback_audio_src_id": 1,
            "expected_question_count": 1,
            "expected_question_count_source": {
                "document": "synthetic-test-paper.txt", "sha256": "0" * 64,
                "locator": "测试夹具独立定义为 1 题；不是实际真题验收记录",
            },
        },
        "audio": {
            "_src_id": 1, "audio_code": "TEST_M2_AUDIO", "storage_provider": "local",
            "storage_key": AUDIO_KEY, "duration_ms": 5000, "format": "m4a",
            "mime_type": "audio/mp4", "file_hash": audio_hash, "is_current": True,
        },
        "content_groups": [
            {"_src_id": 1, "content_group_code": "CG_TEST", "group_name": "测试内容组",
             "exam_level_scope": "CET4", "content_fingerprint": None}
        ],
        "passages": [
            {"_src_id": 10, "passage_code": "TEST_P01", "audio_src_id": 1,
             "passage_index": 1, "passage_type": "短篇新闻", "topic": "测试主题",
             "start_ms": 0, "body_end_ms": 4000, "end_ms": 5000, "speaker_count": 1}
        ],
        "transcript_segments": [
            {"_src_id": 100, "passage_src_id": 10, "segment_index": 1,
             "segment_type": "body", "text": "This is the body.", "speaker_code": "N",
             "start_ms": 0, "end_ms": 2000},
            {"_src_id": 101, "passage_src_id": 10, "segment_index": 2,
             "segment_type": "question", "text": "What is it?", "speaker_code": "Q",
             "start_ms": 2000, "end_ms": 3000},
        ],
        "questions": [
            {"_src_id": 20, "question_code": "TEST_Q01", "passage_src_id": 10,
             "question_segment_src_id": 101, "question_text": "What is it?",
             "option_a": "Alpha", "option_b": "Beta", "option_c": "Gamma",
             "option_d": "Delta", "correct_option": "A",
             "explanation_text": "因为原文如此。", "explanation_source": "测试解析"}
        ],
        "presentations": [
            {"question_src_id": 20, "exam_paper_src_id": 1, "question_no": 1,
             "option_mapping_state": "已知", "mapping_source": "测试映射",
             "option_letter_mapping": {"A": "A", "B": "B", "C": "C", "D": "D"}}
        ],
    }


@pytest.fixture(scope="session")
def module2_paper_id(prepared_database: None, tmp_path_factory) -> int:
    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper
    from app.import_module2 import run_import

    settings = get_settings()
    audio_dir = settings.audio_storage_path
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_bytes = b"MODULE2-TEST-AUDIO-BYTES"
    audio_path = audio_dir / AUDIO_KEY
    audio_path.write_bytes(audio_bytes)
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()

    payload_file = tmp_path_factory.mktemp("m2") / "payload.json"
    payload_file.write_text(
        json.dumps(_sample_payload(audio_hash), ensure_ascii=False), encoding="utf-8"
    )
    result = run_import(payload_file, audio_path)
    assert result["status"] == "imported", result

    with SessionLocal() as db:
        paper = db.query(ExamPaper).filter(ExamPaper.exam_paper_code == PAPER_CODE).one()
        return paper.id


def test_repeat_import_is_idempotent(module2_paper_id: int) -> None:
    from sqlalchemy import func, select

    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import ImportBatch, Question
    from app.import_module2 import run_import

    settings = get_settings()
    audio_path = settings.audio_storage_path / AUDIO_KEY
    audio_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    import tempfile, pathlib

    with tempfile.TemporaryDirectory() as tmp:
        payload_file = pathlib.Path(tmp) / "payload.json"
        payload_file.write_text(
            json.dumps(_sample_payload(audio_hash), ensure_ascii=False), encoding="utf-8"
        )
        result = run_import(payload_file, audio_path)
    assert result["status"] == "noop", result

    with SessionLocal() as db:
        batches = db.scalars(
            select(func.count()).select_from(ImportBatch).where(
                ImportBatch.exam_paper_id == module2_paper_id
            )
        ).one()
        questions = db.scalars(
            select(func.count()).select_from(Question).join(
                ImportBatch, ImportBatch.id == Question.batch_id
            ).where(ImportBatch.exam_paper_id == module2_paper_id)
        ).one()
    assert batches == 1
    assert questions == 1


def test_student_hidden_before_confirm(client: TestClient, student_token: str, module2_paper_id: int) -> None:
    listing = client.get("/api/v1/listening-papers", headers=auth_headers(student_token))
    assert listing.status_code == 200
    ids = [item["exam_paper_id"] for item in listing.json()["data"]["items"]]
    assert module2_paper_id not in ids

    detail = client.get(
        f"/api/v1/listening-papers/{module2_paper_id}", headers=auth_headers(student_token)
    )
    assert detail.status_code == 404


def test_confirm_then_student_sees(
    client: TestClient, admin_token: str, student_token: str, module2_paper_id: int
) -> None:
    confirm = client.post(
        f"/api/v1/admin/listening-papers/{module2_paper_id}/visibility",
        json={"action": "confirm", "reason": "测试确认"},
        headers=auth_headers(admin_token),
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["data"]["is_visible"] is True

    detail = client.get(
        f"/api/v1/listening-papers/{module2_paper_id}", headers=auth_headers(student_token)
    )
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["exam_paper_code"] == PAPER_CODE
    assert data["passages"][0]["questions"][0]["question_no"] == 1


def test_student_response_excludes_restricted_fields(
    client: TestClient, admin_token: str, student_token: str, module2_paper_id: int
) -> None:
    client.post(
        f"/api/v1/admin/listening-papers/{module2_paper_id}/visibility",
        json={"action": "confirm", "reason": ""},
        headers=auth_headers(admin_token),
    )
    detail = client.get(
        f"/api/v1/listening-papers/{module2_paper_id}", headers=auth_headers(student_token)
    )
    raw = detail.text
    for forbidden_field in ("correct_option", "explanation_text", "explanation_source", "segments"):
        assert forbidden_field not in raw
    question = detail.json()["data"]["passages"][0]["questions"][0]
    assert question["question_text"] == "What is it?"
    assert [o["label"] for o in question["options"]] == ["A", "B", "C", "D"]


def test_student_cannot_call_admin_endpoints(client: TestClient, student_token: str, module2_paper_id: int) -> None:
    for method, url in (
        ("get", f"/api/v1/admin/listening-papers/{module2_paper_id}/companion"),
        ("get", f"/api/v1/admin/listening-papers/{module2_paper_id}/checks"),
    ):
        response = getattr(client, method)(url, headers=auth_headers(student_token))
        assert response.status_code == 403, url
    response = client.post(
        f"/api/v1/admin/listening-papers/{module2_paper_id}/visibility",
        json={"action": "confirm", "reason": ""},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 403


def test_audio_range_and_cancel_blocks_student(
    client: TestClient, admin_token: str, student_token: str, module2_paper_id: int
) -> None:
    client.post(
        f"/api/v1/admin/listening-papers/{module2_paper_id}/visibility",
        json={"action": "confirm", "reason": ""},
        headers=auth_headers(admin_token),
    )
    audio = client.get(
        f"/api/v1/listening-papers/{module2_paper_id}/audio",
        headers={**auth_headers(student_token), "Range": "bytes=0-3"},
    )
    assert audio.status_code == 206
    assert audio.headers["Accept-Ranges"] == "bytes"
    assert audio.headers["Content-Range"].startswith("bytes 0-3/")

    cancel = client.post(
        f"/api/v1/admin/listening-papers/{module2_paper_id}/visibility",
        json={"action": "cancel", "reason": "测试取消"},
        headers=auth_headers(admin_token),
    )
    assert cancel.status_code == 200
    assert cancel.json()["data"]["is_visible"] is False

    denied = client.get(
        f"/api/v1/listening-papers/{module2_paper_id}/audio", headers=auth_headers(student_token)
    )
    assert denied.status_code == 404


def test_admin_companion_has_answers(
    client: TestClient, admin_token: str, module2_paper_id: int
) -> None:
    response = client.get(
        f"/api/v1/admin/listening-papers/{module2_paper_id}/companion",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    question = data["passages"][0]["questions"][0]
    assert question["correct_option"] == "A"
    assert question["explanation_text"]
    assert data["passages"][0]["segments"]


# --------------------------------------------------------------------------- #
# 验收报告 F01–F05 回归用例
# --------------------------------------------------------------------------- #
def _load_paper_batch(db, paper_id: int):
    from sqlalchemy import select

    from app.db.models_listening import ImportBatch

    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.exam_paper_id == paper_id, ImportBatch.is_current.is_(True)
        )
    )
    return batch


def test_missing_questions_against_expected_count(module2_paper_id: int) -> None:
    """F02：只比较题目数与映射数，末尾整题一起缺失仍能通过；必须对照应有题量。"""
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper
    from app.services.content_check import evaluate

    with SessionLocal() as db:
        paper = db.get(ExamPaper, module2_paper_id)
        batch = _load_paper_batch(db, paper.id)
        assert paper.expected_question_count == 1, "样例导入时应固定应有题量"

        # 模拟「应有 2 题、实际只有 1 题」
        paper.expected_question_count = 2
        db.commit()
        try:
            issues = evaluate(db, paper, batch, get_settings().audio_storage_path)
            kinds = [i["kind"] for i in issues]
            assert "question_count_mismatch" in kinds, kinds
            assert any("应有题量(2)" in i["message"] for i in issues if i["kind"] == "question_count_mismatch")
        finally:
            paper.expected_question_count = 1
            db.commit()


def test_invalid_option_mapping_blocks_confirm(
    client: TestClient, admin_token: str, module2_paper_id: int
) -> None:
    """F03：映射值为非法字母时必须报错并拒绝确认可见。"""
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper, Presentation
    from app.services.content_check import evaluate

    with SessionLocal() as db:
        paper = db.get(ExamPaper, module2_paper_id)
        batch = _load_paper_batch(db, paper.id)
        presentation = db.scalar(select(Presentation).where(Presentation.batch_id == batch.id))
        original = presentation.option_letter_mapping
        presentation.option_letter_mapping = {"A": "Z", "B": "B", "C": "C", "D": "D"}
        db.commit()
        try:
            issues = evaluate(db, paper, batch, get_settings().audio_storage_path)
            assert any(i["kind"] == "option_mapping_invalid" for i in issues), issues

            response = client.post(
                f"/api/v1/admin/listening-papers/{module2_paper_id}/visibility",
                json={"action": "confirm", "reason": ""},
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 400, response.text
            assert "选项映射" in response.json()["msg"]
        finally:
            presentation.option_letter_mapping = original
            db.commit()


def test_admin_answer_follows_option_mapping(
    client: TestClient, admin_token: str, module2_paper_id: int
) -> None:
    """F04：选项重排后，管理员看到的答案字母必须是本套展示下的字母。"""
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_listening import Presentation

    with SessionLocal() as db:
        batch = _load_paper_batch(db, module2_paper_id)
        presentation = db.scalar(select(Presentation).where(Presentation.batch_id == batch.id))
        original = presentation.option_letter_mapping
        # 原答案 A；把 A→B、B→A 交换，正确文字将出现在 B
        presentation.option_letter_mapping = {"A": "B", "B": "A", "C": "C", "D": "D"}
        db.commit()
        try:
            response = client.get(
                f"/api/v1/admin/listening-papers/{module2_paper_id}/companion",
                headers=auth_headers(admin_token),
            )
            assert response.status_code == 200, response.text
            question = response.json()["data"]["passages"][0]["questions"][0]
            assert question["correct_option"] == "B", question
            assert question["correct_option_base"] == "A", question
            assert [o["text"] for o in question["options"]][1] == "Alpha"
        finally:
            presentation.option_letter_mapping = original
            db.commit()


def test_audio_code_conflict_is_rejected(module2_paper_id: int, tmp_path) -> None:
    """F05：同一 audio_code 换文件时不能静默复用旧记录。"""
    import hashlib
    import json

    from app.db.base import SessionLocal
    from app.db.models_listening import AudioFile
    from app.import_module2 import run_import

    with SessionLocal() as db:
        from sqlalchemy import select

        audio = db.scalar(select(AudioFile).where(AudioFile.audio_code == "TEST_M2_AUDIO"))
        existing_code = audio.audio_code

    new_bytes = b"MODULE2-DIFFERENT-AUDIO-BYTES"
    new_audio = tmp_path / "other.m4a"
    new_audio.write_bytes(new_bytes)

    payload = _sample_payload(hashlib.sha256(new_bytes).hexdigest())
    payload["audio"]["audio_code"] = existing_code  # 复用编码，但内容不同
    payload["audio"]["storage_key"] = "another-version.m4a"
    payload["audio"]["duration_ms"] = 1417046
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    try:
        run_import(payload_file, new_audio)
    except ValueError as exc:
        assert "音频编码" in str(exc), exc
    else:  # pragma: no cover - 修复前会静默成功
        raise AssertionError("同一 audio_code 的不同文件不应导入成功")


def test_failed_import_keeps_existing_audio(module2_paper_id: int, tmp_path) -> None:
    """F01：导入中途失败时，旧批次引用的音频文件必须原样保留。"""
    import hashlib
    import json

    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import AudioFile
    from app.import_module2 import run_import

    settings = get_settings()
    with SessionLocal() as db:
        audio = db.scalar(select(AudioFile).where(AudioFile.audio_code == "TEST_M2_AUDIO"))
        key = audio.storage_key
        original_hash = audio.file_hash

    target = settings.audio_storage_path / key
    assert target.is_file()
    before = hashlib.sha256(target.read_bytes()).hexdigest()

    # 同 storage_key、不同内容、不同 audio_code（绕开 F05），并在末尾制造写入失败
    new_bytes = b"MODULE2-REPLACEMENT-AUDIO-BYTES"
    new_audio = tmp_path / "replacement.m4a"
    new_audio.write_bytes(new_bytes)
    payload = _sample_payload(hashlib.sha256(new_bytes).hexdigest())
    payload["audio"]["audio_code"] = "TEST_M2_AUDIO_REPLACEMENT"
    payload["questions"][0]["passage_src_id"] = 999  # 不存在的篇章 -> 事务中途失败
    payload_file = tmp_path / "bad.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    try:
        run_import(payload_file, new_audio)
    except Exception:  # noqa: BLE001 - 预期失败
        pass
    else:  # pragma: no cover
        raise AssertionError("该材料应当导入失败")

    after = hashlib.sha256(target.read_bytes()).hexdigest()
    assert after == before == original_hash, "失败导入不得替换旧音频"
    leftovers = list(settings.audio_storage_path.glob(".incoming-*"))
    assert leftovers == [], f"临时文件未清理：{leftovers}"
