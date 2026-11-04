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
            select(func.count()).select_from(Question)
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
