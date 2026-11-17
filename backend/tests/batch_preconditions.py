"""Obtain the actual batch identity for version-bound administrator commands."""


def current_batch_id(paper_id):
    from app.db.base import SessionLocal
    from app.repositories.listening import get_current_batch

    with SessionLocal() as db:
        batch = get_current_batch(db, paper_id)
        assert batch is not None
        return batch.id
