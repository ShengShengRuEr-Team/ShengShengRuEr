"""Bootstrap uses a private transactional schema, never the business tables."""

from uuid import uuid4

import pytest


@pytest.fixture
def dictionary_database(prepared_database, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from sqlalchemy.schema import CreateSchema

    from app import initialize_dictionary, seed
    from app import main as _main  # noqa: F401
    from app.db.base import Base, engine

    schema = "dictionary_seed_" + uuid4().hex
    with engine.connect().execution_options(
        schema_translate_map={None: schema}
    ) as conn:
        transaction = conn.begin()
        try:
            conn.execute(CreateSchema(schema))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(conn)

            def sessions():
                return Session(bind=conn, join_transaction_mode="create_savepoint")

            monkeypatch.setattr(initialize_dictionary, "SessionLocal", sessions)
            monkeypatch.setattr(seed, "SessionLocal", sessions)
            yield sessions
        finally:
            transaction.rollback()


def test_missing_dictionary_becomes_readable_with_empty_formal_scope(
    dictionary_database,
):
    from app.initialize_dictionary import initialize_dictionary
    from app.services.skill_error_query.dictionary import build_dictionary
    from app.services.skill_error_query.scope import read_scope

    result = initialize_dictionary()
    assert result["created"] is True
    assert result["skills"] > 0 and result["error_causes"] > 0
    with dictionary_database() as db:
        scope = read_scope(db)
        value = build_dictionary(db, scope)
        assert value.skills and value.error_causes
        assert scope.batch_ids == ()
        assert all(not s.question_count for s in value.skills)


def test_existing_dictionary_is_not_reimported_or_changed(
    dictionary_database, monkeypatch
):
    from app import initialize_dictionary as initializer
    from app.db.models_processing import DictionarySnapshot

    first = initializer.initialize_dictionary()
    with dictionary_database() as db:
        snapshot = db.get(DictionarySnapshot, first["snapshot_id"])
        snapshot.version = "existing-version-must-be-retained"
        original_payload = snapshot.payload
        db.commit()

    def no_reimport(db):
        raise AssertionError("Existing snapshots must not be replaced")

    monkeypatch.setattr(initializer, "ensure_dictionary", no_reimport)
    second = initializer.initialize_dictionary()
    assert second["created"] is False
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["version"] == "existing-version-must-be-retained"
    with dictionary_database() as db:
        assert (
            db.get(DictionarySnapshot, first["snapshot_id"]).payload == original_payload
        )


def test_failed_import_rolls_back_all_dictionary_rows(dictionary_database, monkeypatch):
    from sqlalchemy import func, select

    from app import initialize_dictionary as initializer
    from app.db.models_annotations import Skill
    from app.db.models_processing import DictionarySnapshot

    original = initializer.ensure_dictionary

    def fail_after_insert(db):
        original(db)
        raise RuntimeError("Synthetic import failure")

    monkeypatch.setattr(initializer, "ensure_dictionary", fail_after_insert)
    with pytest.raises(RuntimeError, match="Synthetic import failure"):
        initializer.initialize_dictionary()
    with dictionary_database() as db:
        assert db.scalar(select(func.count()).select_from(DictionarySnapshot)) == 0
        assert db.scalar(select(func.count()).select_from(Skill)) == 0


def test_startup_seed_initializes_dictionary_and_preserves_existing_account(
    dictionary_database,
):
    from sqlalchemy import select

    from app import seed
    from app.db.models import User

    seed.main()
    with dictionary_database() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        original_password = admin.password_hash
        admin.nickname = "Existing account"
        db.commit()
    seed.main()
    with dictionary_database() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin.nickname == "Existing account"
        assert admin.password_hash == original_password
