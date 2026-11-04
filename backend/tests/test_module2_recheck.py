"""复验报告 F01/F02 的边界回归，连接夹具创建的真实 PostgreSQL。"""

import copy
import hashlib
import json
import uuid

import pytest

from tests.conftest import auth_headers
from tests.test_module2_listening import _sample_payload


def _import(tmp_path, payload, audio):
    from app.import_module2 import run_import

    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run_import(path, audio)


def _fresh(tmp_path):
    tag = uuid.uuid4().hex[:12]
    audio = tmp_path / "input.m4a"
    audio.write_bytes(tag.encode())
    payload = _sample_payload(hashlib.sha256(audio.read_bytes()).hexdigest())
    payload["exam_paper"]["exam_paper_code"] = f"RECHECK_{tag}"
    payload["audio"].update(audio_code=f"RECHECK_AUDIO_{tag}", storage_key=f"{tag}.m4a")
    return payload, audio


def _paper_id(payload):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper

    with SessionLocal() as db:
        return db.scalar(select(ExamPaper.id).where(
            ExamPaper.exam_paper_code == payload["exam_paper"]["exam_paper_code"]
        ))


def _state(pid):
    from sqlalchemy import func, select

    from app.db import models_listening as m
    from app.db.base import SessionLocal
    from app.repositories.listening import get_current_batch, get_visibility

    with SessionLocal() as db:
        batch = get_current_batch(db, pid)
        visible = get_visibility(db, batch.id)
        counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                  for model in (m.ExamPaper, m.AudioFile, m.ImportBatch, m.Passage,
                                m.TranscriptSegment, m.Question, m.Presentation)}
        return batch.id, bool(visible and visible.is_visible), counts


@pytest.mark.parametrize("failure", ["mid_write", "commit"])
@pytest.mark.parametrize("existing_version", [True, False])
def test_failed_import_owns_only_new_files(
    prepared_database, client, admin_token, student_token, tmp_path, monkeypatch,
    failure, existing_version,
):
    """已有后缀版本 + 中途/提交失败；新文件提交失败只清除本次文件。"""
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.import_module2 import sha256_file

    payload, audio = _fresh(tmp_path)
    first = _import(tmp_path, payload, audio)
    second = copy.deepcopy(payload)
    replacement = tmp_path / "replacement.m4a"
    replacement.write_bytes(audio.read_bytes() + b"-version-B")
    second["audio"]["audio_code"] += "_B"
    second["audio"]["file_hash"] = sha256_file(replacement)
    if existing_version:
        result = _import(tmp_path, second, replacement)
        key = result["audio"]["storage_key"]
        assert key != payload["audio"]["storage_key"]
        current_audio = replacement
    else:
        key = first["audio"]["storage_key"]
        current_audio = audio
    pid = _paper_id(payload)
    endpoint = f"/api/v1/admin/listening-papers/{pid}/visibility"
    assert client.post(endpoint, json={"action": "confirm"},
                       headers=auth_headers(admin_token)).status_code == 200
    before = _state(pid)
    audio_dir = get_settings().audio_storage_path
    files_before = {p.name: sha256_file(p) for p in audio_dir.iterdir() if p.is_file()}
    bad = copy.deepcopy(second)
    bad["questions"][0]["explanation_text"] += "Different manifest"
    if failure == "mid_write":
        bad["questions"][0]["passage_src_id"] = 999
        expected_error = KeyError
    else:
        expected_error = RuntimeError
    with monkeypatch.context() as patch:
        if failure == "commit":
            def fail_commit(self):
                raise RuntimeError("injected commit failure")
            patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(expected_error):
            _import(tmp_path, bad, replacement)
    assert _state(pid) == before
    assert {p.name: sha256_file(p) for p in audio_dir.iterdir() if p.is_file()} == files_before
    assert sha256_file(audio_dir / key) == sha256_file(current_audio)
    response = client.get(f"/api/v1/listening-papers/{pid}/audio",
                          headers=auth_headers(student_token))
    assert response.status_code == 200
    assert response.content == current_audio.read_bytes()


def test_partial_copy_failure_removes_temp_only(prepared_database, tmp_path, monkeypatch):
    from app import import_module2 as importer
    from app.core.config import get_settings

    payload, audio = _fresh(tmp_path)
    audio_dir = get_settings().audio_storage_path
    before = set(audio_dir.iterdir())

    def partial_copy(source, destination):
        destination.write_bytes(b"partial")
        raise OSError("injected copy failure")

    monkeypatch.setattr(importer.shutil, "copyfile", partial_copy)
    with pytest.raises(OSError, match="injected copy failure"):
        _import(tmp_path, payload, audio)
    assert set(audio_dir.iterdir()) == before
    assert _paper_id(payload) is None


def test_version_hash_prefix_collision_never_overwrites(tmp_path, prepared_database):
    from app.import_module2 import _resolve_audio_target, sha256_file

    original = tmp_path / "audio.m4a"
    original.write_bytes(b"A")
    digest = hashlib.sha256(b"B").hexdigest()
    version = tmp_path / f"audio-{digest[:8]}.m4a"
    version.write_bytes(b"unrelated-existing-file")
    target, needs_write = _resolve_audio_target(tmp_path, original.name, digest)
    assert target.name == f"audio-{digest}.m4a" and needs_write
    assert version.read_bytes() == b"unrelated-existing-file"
    version.write_bytes(b"B")
    assert _resolve_audio_target(tmp_path, original.name, sha256_file(version)) == (version, False)


def test_fresh_import_without_count_cannot_self_validate(
    prepared_database, client, admin_token, student_token, tmp_path,
):
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper

    payload, audio = _fresh(tmp_path)
    payload["exam_paper"].pop("expected_question_count")
    payload["exam_paper"].pop("expected_question_count_source")
    _import(tmp_path, payload, audio)
    pid = _paper_id(payload)
    with SessionLocal() as db:
        paper = db.get(ExamPaper, pid)
        assert paper.expected_question_count is None
        assert paper.expected_question_count_source is None
    _assert_hidden(client, pid, admin_token, student_token, "expected_count_missing")
    # 相同材料幂等重导也不得按实际题数补出基准。
    assert _import(tmp_path, payload, audio)["status"] == "noop"
    _assert_hidden(client, pid, admin_token, student_token, "expected_count_missing")


def _assert_hidden(client, pid, admin_token, student_token, issue):
    confirm = client.post(f"/api/v1/admin/listening-papers/{pid}/visibility",
                          json={"action": "confirm"}, headers=auth_headers(admin_token))
    assert confirm.status_code == 400
    checks = client.get(f"/api/v1/admin/listening-papers/{pid}/checks",
                        headers=auth_headers(admin_token)).json()["data"]
    assert any(item["kind"] == issue for item in checks["issues"])
    for suffix in ("", "/audio"):
        assert client.get(f"/api/v1/listening-papers/{pid}{suffix}",
                          headers=auth_headers(student_token)).status_code == 404
    listing = client.get("/api/v1/listening-papers", headers=auth_headers(student_token))
    assert pid not in {p["exam_paper_id"] for p in listing.json()["data"]["items"]}


def test_fresh_missing_question_uses_independent_count(
    prepared_database, client, admin_token, student_token, tmp_path,
):
    payload, audio = _fresh(tmp_path)
    payload["exam_paper"]["expected_question_count"] = 2
    _import(tmp_path, payload, audio)
    _assert_hidden(client, _paper_id(payload), admin_token, student_token,
                   "question_count_mismatch")


@pytest.mark.parametrize("value", [None, {}, {"document": "paper.pdf"}])
def test_declared_count_requires_source(prepared_database, tmp_path, value):
    payload, audio = _fresh(tmp_path)
    payload["exam_paper"]["expected_question_count_source"] = value
    with pytest.raises(ValueError, match="原卷核对依据"):
        _import(tmp_path, payload, audio)
    assert _paper_id(payload) is None
