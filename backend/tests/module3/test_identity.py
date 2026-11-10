"""Result identity must cover content while ignoring temporary naming and ordering."""


def test_a24_result_hash_ignores_temporary_ids_and_entity_order(context):
    from app.module3.contracts import result_hash

    original = context["clone"]()
    renamed = context["clone"]()
    mapping = {
        row["_src_id"]: "new:" + row["_src_id"]
        for rows in renamed.values()
        if isinstance(rows, list)
        for row in rows
        if isinstance(row, dict) and "_src_id" in row
    }
    for rows in renamed.values():
        if not isinstance(rows, list):
            continue
        rows.reverse()
        for row in rows:
            for key, value in list(row.items()):
                if key == "_src_id" or key.endswith("_src_id"):
                    row[key] = mapping.get(value, value)
                if key.endswith("_src_ids"):
                    row[key] = [mapping.get(v, v) for v in value]
    assert result_hash(original) == result_hash(renamed)
    renamed["questions"][0]["option_a"] = "Changed answer text"
    assert result_hash(original) != result_hash(renamed)


def test_a33_incomplete_review_rejected(persisted, client):
    c = persisted
    response = client.post(
        f"/api/v1/admin/processing-tasks/{c['task_id']}/reviews",
        headers=c["headers"],
        json={
            "result_hash": c["result_hash"],
            "scope": "content",
            "decision": "approved",
            "items": [{"reference": "generic incomplete record"}],
            "evidence_refs": ["synthetic"],
            "note": "Synthetic incomplete review rejection",
        },
    )
    assert response.status_code == 422


def test_a32_automatic_draft_database_immutable(persisted):
    from uuid import UUID

    import pytest
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError

    from app.db.base import SessionLocal
    from app.db.models_processing import ProcessingDraft

    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                update(ProcessingDraft)
                .where(
                    ProcessingDraft.task_id == UUID(persisted["task_id"]),
                    ProcessingDraft.view == "auto_draft",
                )
                .values(payload={"attempted": "overwrite"})
            )
        db.rollback()
