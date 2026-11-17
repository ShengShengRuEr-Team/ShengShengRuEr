"""Populate a disposable module-two schema for migration preservation checks."""

import argparse
import hashlib
import json
import os
import wave
from pathlib import Path
from uuid import uuid4

from sqlalchemy import MetaData, create_engine, insert, text
from sqlalchemy.engine import make_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", action="store_true")
    args = parser.parse_args()
    url = make_url(os.environ["DATABASE_URL"])
    if not (
        url.database.startswith("m3_verify_") and url.database.endswith("_migration")
    ):
        raise RuntimeError("Fixture is restricted to disposable verification databases")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            revisions = set(
                connection.scalars(text("SELECT version_num FROM alembic_version"))
            )
        allowed = {"0004_expected_count_source"}
        if args.source:
            allowed |= {"0005_attempt_system", "0006_module3_invariants"}
        if not revisions or not revisions <= allowed:
            raise RuntimeError("Fixture requires the module-two migration revision")
        from app.seed import seed

        seed()
        audio_dir = Path(os.environ["AUDIO_STORAGE_DIR"])
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio = audio_dir / "legacy.wav"
        with wave.open(str(audio), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"\0\0" * 48000)
        metadata = MetaData()
        metadata.reflect(engine)
        with engine.begin() as connection:

            def add(table, **values):
                target = metadata.tables[table]
                return connection.scalar(
                    insert(target).values(**values).returning(target.c.id)
                )

            audio_id = add(
                "audio_files",
                audio_code="MIGRATION_AUDIO",
                storage_key=audio.name,
                duration_ms=3000,
                format="wav",
                mime_type="audio/wav",
                file_hash=hashlib.sha256(audio.read_bytes()).hexdigest(),
            )
            paper = add(
                "exam_papers",
                exam_paper_code="MIGRATION_PAPER",
                exam_level="CET4",
                exam_year=2025,
                exam_month=6,
                paper_set=1,
                playback_audio_id=audio_id,
                expected_question_count=1,
                expected_question_count_source={
                    "document": "synthetic",
                    "sha256": "0" * 64,
                    "locator": "One test question",
                },
            )
            batch = add(
                "import_batches",
                exam_paper_id=paper,
                audio_id=audio_id,
                batch_code="MIGRATION_BATCH",
                status="active",
                is_current=True,
            )
            add("content_groups", batch_id=batch, content_group_code="G1")
            passage = add(
                "passages",
                batch_id=batch,
                exam_paper_id=paper,
                audio_id=audio_id,
                passage_code="P1",
                passage_index=1,
                start_ms=0,
                body_end_ms=2000,
                end_ms=3000,
            )
            for index, kind, content, start, end in (
                (1, "body", "Alpha is correct.", 0, 2000),
                (2, "question", "Which is correct?", 2000, 3000),
            ):
                segment = add(
                    "transcript_segments",
                    batch_id=batch,
                    passage_id=passage,
                    segment_index=index,
                    segment_type=kind,
                    text=content,
                    start_ms=start,
                    end_ms=end,
                )
            question = add(
                "questions",
                batch_id=batch,
                passage_id=passage,
                question_segment_id=segment,
                question_code="Q1",
                question_text="Which is correct?",
                option_a="Alpha",
                option_b="Beta",
                option_c="Gamma",
                option_d="Delta",
                correct_option="A",
                explanation_text="Alpha is correct.",
            )
            add(
                "presentations",
                batch_id=batch,
                exam_paper_id=paper,
                question_id=question,
                question_no=1,
                option_mapping_state="已知",
                option_letter_mapping={letter: letter for letter in "ABCD"},
            )
            add(
                "content_checks",
                exam_paper_id=paper,
                batch_id=batch,
                is_passed=True,
                issues=[],
            )
            if args.source and "attempts" in metadata.tables:
                student = connection.scalar(
                    text("SELECT id FROM users WHERE username='student'")
                )
                attempt = add(
                    "attempts",
                    attempt_code=str(uuid4()),
                    student_id=student,
                    exam_paper_id=paper,
                    import_batch_id=batch,
                    attempt_key=str(uuid4()),
                    request_fingerprint="f" * 64,
                    question_count=1,
                    correct_count=1,
                    correct_rate=100,
                    score_breakdown={"synthetic": True},
                )
                add(
                    "attempt_answers",
                    attempt_id=attempt,
                    question_no=1,
                    question_id=question,
                    question_text="Which is correct?",
                    option_a="Alpha",
                    option_b="Beta",
                    option_c="Gamma",
                    option_d="Delta",
                    correct_option="A",
                    selected_option="A",
                    is_correct=True,
                    explanation_text="Synthetic preservation fixture",
                )
            if args.source and "error_question_relations" in metadata.tables:
                snapshot = add(
                    "dictionary_snapshots",
                    schema_sha256="d" * 64,
                    data_sha256="e" * 64,
                    version="synthetic-legacy",
                    payload={},
                    id_mapping={},
                )
                cause = add(
                    "error_causes",
                    snapshot_id=snapshot,
                    error_cause_code="SYNTHETIC",
                    display_code="SYNTHETIC",
                    cause_level=3,
                    cause_name="Synthetic",
                    definition="Migration fixture only",
                    maturity="test",
                    status="启用",
                    collector="verification",
                    review_status="待审核",
                )
                evidence = add(
                    "evidence_items",
                    batch_id=batch,
                    passage_id=passage,
                    start_ms=0,
                    end_ms=2000,
                    evidence_text="Alpha is correct.",
                    evidence_type="正文",
                    source="synthetic",
                    review_status="待审核",
                )
                owner = add(
                    "error_question_relations",
                    batch_id=batch,
                    relation_kind="QUESTION_ERROR_CANDIDATE",
                    relation_code="LEGACY_NULL_OPTION",
                    revision_no=1,
                    is_current=True,
                    question_id=question,
                    error_cause_id=cause,
                    option_letter=None,
                    collector="verification",
                    review_status="待审核",
                )
                add(
                    "error_question_relations",
                    batch_id=batch,
                    relation_kind="CANDIDATE_EVIDENCE",
                    relation_code="LEGACY_CHILD",
                    revision_no=1,
                    is_current=True,
                    owner_relation_id=owner,
                    evidence_id=evidence,
                    sort_order=1,
                    collector="verification",
                    review_status="待审核",
                )
        (args.output / "legacy-fixture.json").write_text(
            json.dumps({"source": "synthetic", "questions": 1, "segments": 2}),
            encoding="utf-8",
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
