"""Synthetic technical fixtures and real PostgreSQL, separate from acceptance."""

import copy
import hashlib
import uuid
import wave

import pytest


@pytest.fixture
def context(client, admin_token, tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.module3.contracts import file_hash
    from app.services.processing.validation import CONFIG_DIR, load_dictionary

    settings = get_settings()
    for key, value in (
        ("m3_materials_dir", str(tmp_path)),
        ("m3_artifacts_dir", str(tmp_path / "artifacts")),
        ("audio_storage_dir", str(tmp_path / "audio")),
    ):
        monkeypatch.setattr(settings, key, value)
    code = "M3_TEST_" + uuid.uuid4().hex[:12]
    paper = tmp_path / (code + "-paper.pdf")
    paper.write_bytes(b"%PDF-1.4\n% synthetic independent one-question source\n")
    answer = tmp_path / (code + "-answer.pdf")
    answer.write_bytes(b"%PDF-1.4\n% synthetic answer A: the body says Alpha\n")
    audio = tmp_path / (code + "-audio.wav")
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 48000)
    headers = {"Authorization": "Bearer " + admin_token}
    materials = []
    for kind, path in (
        ("paper_text", paper),
        ("answer_explanation", answer),
        ("audio", audio),
    ):
        request = {
            "exam_paper_code": code,
            "source_kind": kind,
            "storage_key": path.name,
            "expected_sha256": file_hash(path),
            "source_locator": "synthetic fixture; independent 1-question definition",
        }
        response = client.post("/api/v1/admin/materials", json=request, headers=headers)
        assert response.status_code == 201, response.text
        materials.append(response.json()["data"])
    request = {
        "exam_paper": {
            "exam_paper_code": code,
            "exam_level": "CET4",
            "exam_year": 2025,
            "exam_month": 6,
            "paper_set": 1,
        },
        "material_ids": [r["id"] for r in materials],
        "document_mode": "text",
        "text_source": "asr",  # Synthetic legacy-route tests supply no real text.
        "expected_question_count": 1,
        "expected_question_count_source": {
            "document": paper.name,
            "sha256": file_hash(paper),
            "locator": "synthetic source independently defines question 1",
        },
        "expected_question_ranges": [{"section": "synthetic", "start": 1, "end": 1}],
        "dictionary_snapshot_sha256": file_hash(CONFIG_DIR / "dictionary-schema.json"),
        "profile_version": "M3-WIN64-1.1.0",
    }
    response = client.post(
        "/api/v1/admin/processing-tasks", json=request, headers=headers
    )
    assert response.status_code == 202, response.text
    task_id = response.json()["data"]["id"]
    skill = next(
        r["skill_code"]
        for t in load_dictionary()["tables"]
        if t["name"] == "skill"
        for r in t["rows"]
        if r["skill_level"] == 3 and r["status"] == "启用"
    )
    payload = {
        "schema_version": "m3.v1",
        "exam_paper": request["exam_paper"],
        "audio": {
            "audio_code": "A_" + code,
            "file_hash": file_hash(audio),
            "duration_ms": 3000,
            "format": "wav",
            "mime_type": "audio/wav",
            "collector": "synthetic fixture",
        },
        "content_groups": [
            {
                "_src_id": "g:1",
                "content_group_code": "G1",
                "group_name": "synthetic",
                "status": "启用",
            }
        ],
        "passages": [
            {
                "_src_id": "p:1",
                "passage_code": "P1",
                "passage_index": 1,
                "start_ms": 0,
                "body_end_ms": 2000,
                "end_ms": 3000,
            }
        ],
        "transcript_segments": [
            {
                "_src_id": "s:1",
                "passage_src_id": "p:1",
                "segment_index": 1,
                "text": "The answer is Alpha.",
                "segment_type": "body",
                "start_ms": 0,
                "end_ms": 1800,
                "alignment_status": "aligned",
            },
            {
                "_src_id": "s:2",
                "passage_src_id": "p:1",
                "segment_index": 2,
                "text": "What is the answer?",
                "segment_type": "question",
                "start_ms": 2000,
                "end_ms": 2900,
                "alignment_status": "aligned",
            },
        ],
        "questions": [
            {
                "_src_id": "q:1",
                "question_code": "Q1",
                "passage_src_id": "p:1",
                "question_segment_src_id": "s:2",
                "question_index": 1,
                "question_text": "What is the answer?",
                "option_a": "Alpha",
                "option_b": "Beta",
                "option_c": "Gamma",
                "option_d": "Delta",
                "correct_option": "A",
                "explanation_text": "The body explicitly states Alpha.",
                "explanation_source": "answer.pdf p1",
                "source_refs": [
                    {"material_id": materials[1]["id"], "locator": {"page": 1}}
                ],
            }
        ],
        "presentations": [
            {
                "_src_id": "pr:1",
                "question_src_id": "q:1",
                "question_no": 1,
                "option_mapping_state": "已知",
                "option_letter_mapping": dict(zip("ABCD", "ABCD", strict=True)),
            }
        ],
        "evidences": [
            {
                "_src_id": "ev:1",
                "passage_src_id": "p:1",
                "segment_src_ids": ["s:1"],
                "evidence_text": "The answer is Alpha.",
                "evidence_type": "正文",
                "source": "synthetic",
                "collector": "synthetic",
            }
        ],
        "skill_question_relations": [
            {
                "_src_id": "qs:1",
                "relation_code": "QS1",
                "relation_kind": "QUESTION_SKILL",
                "question_src_id": "q:1",
                "skill_code": skill,
                "role": "PRIMARY",
                "collector": "synthetic",
                "attributes_json": {
                    "annotation_reason": "Synthetic fixture checks evidence ownership"
                },
            },
            {
                "_src_id": "se:1",
                "relation_code": "SE1",
                "relation_kind": "SKILL_EVIDENCE",
                "owner_relation_src_id": "qs:1",
                "evidence_src_id": "ev:1",
                "sort_order": 1,
                "collector": "synthetic",
            },
        ],
        "other_relations": [
            {
                "_src_id": "ae:1",
                "relation_code": "AE1",
                "relation_kind": "ANSWER_EVIDENCE",
                "question_src_id": "q:1",
                "evidence_src_id": "ev:1",
                "sort_order": 1,
                "collector": "synthetic",
            }
        ],
        "error_question_relations": [],
        "language_items": [],
    }
    return {
        "task_id": task_id,
        "headers": headers,
        "payload": payload,
        "request": request,
        "materials": materials,
        "audio": audio,
        "settings": settings,
        "paper": paper,
        "clone": lambda: copy.deepcopy(payload),
        "audio_hash": hashlib.sha256(audio.read_bytes()).hexdigest(),
    }


@pytest.fixture
def persisted(context):
    from uuid import UUID

    from app.db.base import SessionLocal
    from app.services.processing import tasks
    from app.services.processing.persistence import persist_result

    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(context["task_id"]), lock=True)
        task.state = "pending"
        db.commit()
        # Claim this task explicitly so unrelated fixture jobs remain independent.
        task = tasks.get_task(db, task.id, lock=True)
        task.state, task.lease_token = "running", UUID(int=uuid.uuid4().int)
        from datetime import timedelta

        task.expires_at = tasks.utcnow() + timedelta(seconds=120)
        db.flush()
        tasks.store_draft(db, task, context["payload"], view="auto_draft")
        batch = persist_result(
            db,
            task.id,
            task.lease_token,
            context["payload"],
            context["audio"],
            context["settings"],
        )
        assert batch is not None, task.issues
        db.commit()
        context.update(
            batch_id=batch.id, paper_id=task.exam_paper_id, result_hash=task.result_hash
        )
    return context
