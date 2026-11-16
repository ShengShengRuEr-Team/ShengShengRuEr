"""Continuation commands against disposable PostgreSQL, never paid inference."""

import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

BASE = "/api/v1/admin/processing-workflows"


def create_payload():
    value = uuid4().int
    return {
        "exam_level": "CET4",
        "exam_year": 2030 + value % 100,
        "exam_month": 1 + (value // 100) % 12,
        "paper_set": 1 + (value // 1200) % 100,
        "document_mode": "text",
        "listening_pages": {"paper": [1, 2], "answer": [3]},
    }


@pytest.fixture
def workflow(client, admin_token):
    headers = {
        "Authorization": "Bearer " + admin_token,
        "Idempotency-Key": str(uuid4()),
    }
    payload = create_payload()
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return headers, payload, response.json()["data"]


def revision_payload(created):
    return {
        "expected_workflow_version": created["result"]["row_version"],
        "expected_revision_id": created["revision_id"],
        "reason": "Synthetic material correction; no model invocation",
        "document_mode": "text",
        "listening_pages": {"paper": [1], "answer": [3]},
    }


def test_create_response_loss_and_replay_after_revision_change(client, workflow):
    headers, original, created = workflow
    new_headers = {**headers, "Idempotency-Key": str(uuid4())}
    revision = revision_payload(created)
    url = f"{BASE}/{created['workflow_id']}/revisions"
    response = client.post(url, headers=new_headers, json=revision)
    assert response.status_code == 201, response.text
    child = response.json()["data"]
    # Replaying the unchanged old request succeeds after row_version advanced.
    replay = client.post(url, headers=new_headers, json=revision)
    assert replay.json()["data"] == child
    replay_create = client.post(BASE, headers=headers, json=original)
    assert replay_create.json()["data"] == created
    lookup = client.get(
        BASE + "/operations/by-key",
        headers=headers,
        params={"action": "create", "idempotency_key": headers["Idempotency-Key"]},
    )
    assert lookup.status_code == 200
    assert lookup.json()["data"]["operation_id"] == created["operation_id"]
    detail = client.get(f"{BASE}/{created['workflow_id']}", headers=headers).json()[
        "data"
    ]
    assert detail["row_version"] == 2
    assert detail["revision_id"] == child["revision_id"]
    assert detail["content_review_state"] == detail["error_review_state"] == "not_ready"


def test_same_key_different_request_and_unaccepted_stale_request(client, workflow):
    headers, original, created = workflow
    changed = {**original, "document_mode": "scan"}
    response = client.post(BASE, headers=headers, json=changed)
    assert response.status_code == 409
    assert response.json()["data"] is None
    assert response.json()["error_code"] == "IDEMPOTENCY_CONFLICT"
    url = f"{BASE}/{created['workflow_id']}/revisions"
    revision = revision_payload(created)
    assert client.post(url, headers=headers, json=revision).status_code == 201
    response = client.post(
        url, headers={**headers, "Idempotency-Key": str(uuid4())}, json=revision
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "VERSION_CONFLICT"


def test_parallel_same_key_creates_only_one_command_and_workflow(client, admin_token):
    from app.db.base import SessionLocal
    from app.db.models_processing_workflows import ProcessingWorkflowCommand

    payload = create_payload()
    headers = {
        "Authorization": "Bearer " + admin_token,
        "Idempotency-Key": str(uuid4()),
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(BASE, headers=headers, json=payload), range(4)
            )
        )
    assert [r.status_code for r in responses] == [201] * 4
    operations = {r.json()["data"]["operation_id"] for r in responses}
    assert len(operations) == 1
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProcessingWorkflowCommand)
                .where(
                    ProcessingWorkflowCommand.idempotency_key
                    == UUID(headers["Idempotency-Key"])
                )
            )
            == 1
        )


def test_parallel_distinct_keys_cannot_duplicate_natural_identity(client, admin_token):
    payload = create_payload()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    BASE,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + admin_token,
                        "Idempotency-Key": str(uuid4()),
                    },
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in responses) == [201, 409]


def test_operation_lookup_is_scoped_to_authenticated_admin(
    client, workflow, student_token
):
    from app.db.base import SessionLocal
    from app.db.models import User
    from app.services.processing.workflows import command_by_key

    headers, _, created = workflow
    with SessionLocal() as db:
        student_id = db.scalar(select(User.id).where(User.username == "student"))
        # A different user cannot find another administrator's key, even internally.
        assert (
            command_by_key(db, student_id, "create", UUID(headers["Idempotency-Key"]))
            is None
        )
    lookup = BASE + "/operations/by-key"
    params = {"action": "create", "idempotency_key": headers["Idempotency-Key"]}
    assert client.get(lookup, params=params).status_code == 401
    assert (
        client.get(
            lookup,
            params=params,
            headers={
                "Authorization": "Bearer " + student_token,
            },
        ).status_code
        == 403
    )
    missing = client.get(
        lookup, headers=headers, params={**params, "idempotency_key": str(uuid4())}
    )
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "OPERATION_NOT_FOUND"
    assert (
        client.get(
            f"{BASE}/{created['workflow_id']}/operations/{created['operation_id']}",
            headers=headers,
        ).status_code
        == 200
    )


def test_strict_commands_and_read_only_gets(client, workflow):
    from app.db.base import SessionLocal
    from app.db.models_processing_workflows import ProcessingWorkflowEvent

    headers, original, created = workflow
    for patch in (
        {"created_by": 1},
        {"row_version": 1},
        {"exam_year": True},
        {"listening_pages": {"paper": [2, 1]}},
        {"listening_pages": {"paper": ["1"]}},
    ):
        assert (
            client.post(
                BASE,
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={**original, **patch},
            ).status_code
            == 422
        )
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(ProcessingWorkflowEvent))
    for _ in range(3):
        response = client.get(f"{BASE}/{created['workflow_id']}", headers=headers)
        assert response.status_code == 200
        detail = response.json()["data"]
        assert detail["row_version"] == 1
        assert [r["state"] for r in detail["materials"]] == ["missing"] * 3
        assert detail["current_batch_id"] is None and not detail["is_student_visible"]
        assert not detail["allowed_actions"][1]["enabled"]
    with SessionLocal() as db:
        assert (
            db.scalar(select(func.count()).select_from(ProcessingWorkflowEvent))
            == before
        )


def test_cursor_pagination_and_invalid_cursor(client, workflow):
    headers, _, created = workflow
    assert (
        client.get(BASE, headers=headers, params={"cursor": "invalid"}).status_code
        == 422
    )
    page = client.get(BASE, headers=headers, params={"limit": 1}).json()["data"]
    assert len(page["items"]) == 1
    if page["next_cursor"]:
        following = client.get(
            BASE,
            headers=headers,
            params={
                "limit": 1,
                "cursor": page["next_cursor"],
            },
        ).json()["data"]
        assert page["items"][0]["workflow_id"] != following["items"][0]["workflow_id"]
    revisions = client.get(
        f"{BASE}/{created['workflow_id']}/revisions", headers=headers
    ).json()["data"]
    assert revisions["items"][0]["revision_id"] == created["revision_id"]


def test_current_revision_cannot_belong_to_another_workflow(client, workflow):
    from app.db.base import SessionLocal

    headers, _, created = workflow
    other = client.post(
        BASE,
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=create_payload(),
    ).json()["data"]
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "UPDATE processing_workflows SET current_revision_id = :revision "
                    "WHERE id = :workflow"
                ),
                {"revision": other["revision_id"], "workflow": created["workflow_id"]},
            )
        db.rollback()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE processing_workflow_commands SET request_hash = repeat('0',64) "
        "WHERE id = :id",
        "DELETE FROM processing_workflow_commands WHERE id = :id",
        "UPDATE processing_workflow_events SET detail = '{}' WHERE command_id = :id",
        "UPDATE processing_workflow_revisions SET rules_manifest = '{}' "
        "WHERE id = :revision",
    ],
)
def test_database_preserves_accepted_request_and_audit_identity(workflow, statement):
    from app.db.base import SessionLocal

    created = workflow[2]
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                text(statement),
                {"id": created["operation_id"], "revision": created["revision_id"]},
            )
        db.rollback()


def test_revision_material_and_final_freeze_is_immutable(workflow):
    from app.db.base import SessionLocal

    created = workflow[2]
    with SessionLocal() as db:
        db.execute(
            text(
                "UPDATE processing_workflow_revisions "
                "SET materials_frozen_at=now(), materials_hash=repeat('a',64), "
                "final_frozen_at=now(), final_result_hash=repeat('b',64) WHERE id=:id"
            ),
            {"id": created["revision_id"]},
        )
        db.commit()
        for assignment in (
            "materials_manifest=jsonb_build_object('x',1)",
            "final_result_hash=repeat('c',64)",
        ):
            with pytest.raises(DBAPIError):
                db.execute(
                    text(
                        "UPDATE processing_workflow_revisions "
                        f"SET {assignment} WHERE id=:id"
                    ),
                    {"id": created["revision_id"]},
                )
            db.rollback()


def test_v2_sample_dependency_scope_and_fixed_vectors():
    from app.module3.annotation_identity import (
        materials_hash,
        request_hash,
        result_hash,
        sample_dependency_hash,
    )

    assert request_hash("create", None, {"a": 1, "b": 2}) == (
        "8bc26c0615dc65ab4c8ab5e9ba99171015171bc4a7320eba95940c60d0671607"
    )
    assert (
        materials_hash(
            [
                {"kind": "paper", "sha256": "a" * 64, "pages": [1]},
            ],
            "text",
        )
        == "a3d486753129b32f3b12afa62fdf6643fb2ce84fb0a11c97adcb855b443a2253"
    )
    assert (
        result_hash(
            {"questions": [], "passages": [], "transcript_segments": []},
            {
                "error_rule_version": "m3.option-errors.v1",
            },
        )
        == "f42961e762034f4336f7f757671aaaa686104741e40fc8fe481cff2d8ee8f175"
    )

    assert request_hash("create", None, {"b": 2, "a": 1}) == request_hash(
        "create", None, {"a": 1, "b": 2}
    )
    assert request_hash(
        "create", None, {"expected_workflow_version": 1}
    ) != request_hash("create", None, {"expected_workflow_version": 2})
    source = {
        "questions": [
            {"_src_id": f"q{i}", "passage_src_id": f"p{i}", "option_a": "A"}
            for i in range(1, 13)
        ],
        "passages": [{"_src_id": f"p{i}", "title": "Source"} for i in range(1, 13)],
        "transcript_segments": [
            {
                "_src_id": f"s{i}",
                "passage_src_id": f"p{i}",
                "segment_index": 1,
                "text": "Body",
                "start_ms": 0,
                "end_ms": 1000,
            }
            for i in range(1, 13)
        ],
    }
    original = sample_dependency_hash(source, {"prompt": "v6"})
    unrelated = copy.deepcopy(source)
    unrelated["questions"][11]["option_a"] = "New twelfth answer"
    assert sample_dependency_hash(unrelated, {"prompt": "v6"}) == original
    affected = copy.deepcopy(source)
    affected["questions"][0]["option_a"] = "New first answer"
    assert sample_dependency_hash(affected, {"prompt": "v6"}) != original
    assert sample_dependency_hash(source, {"prompt": "v7"}) != original
    affected = copy.deepcopy(source)
    affected["source_refs"] = [{"src_id": "s1", "locator": {"page": 2}}]
    assert sample_dependency_hash(affected, {"prompt": "v6"}) != original


def test_v2_hash_keeps_legacy_separate_and_covers_rules(context):
    from app.module3.annotation_identity import result_hash
    from app.module3.contracts import result_hash as legacy_hash

    payload = context["clone"]()
    manifest = {"error_rule_version": "m3.option-errors.v1"}
    identity = result_hash(payload, manifest)
    assert identity != legacy_hash(payload)
    assert identity != result_hash(payload, {**manifest, "dictionary": "changed"})
    payload["review_session"] = {"operator": "reviewer", "row_version": 2}
    assert result_hash(payload, manifest) == identity


def test_operation_queries_do_not_cross_administrator_namespace(client, workflow):
    from app.db.base import SessionLocal
    from app.db.models import Role, User, UserRole
    from tests.conftest import login

    headers, _, created = workflow
    username = "workflow_admin_" + uuid4().hex[:12]
    with SessionLocal() as db:
        original = db.scalar(select(User).where(User.username == "admin"))
        user = User(
            username=username,
            password_hash=original.password_hash,
            nickname="Synthetic second admin",
            status="active",
        )
        db.add(user)
        db.flush()
        role_id = db.scalar(select(Role.id).where(Role.role_key == "admin"))
        db.add(UserRole(user_id=user.id, role_id=role_id))
        db.commit()
    second_headers = {"Authorization": "Bearer " + login(client, username, "admin123")}
    response = client.get(
        BASE + "/operations/by-key",
        headers=second_headers,
        params={
            "action": "create",
            "idempotency_key": headers["Idempotency-Key"],
        },
    )
    assert response.status_code == 404
    response = client.get(
        f"{BASE}/{created['workflow_id']}/operations/{created['operation_id']}",
        headers=second_headers,
    )
    assert response.status_code == 404


def test_duplicate_old_paper_codes_require_identity_resolution(client, admin_token):
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper

    payload = create_payload()
    identity = {
        k: v for k, v in payload.items() if k.startswith("exam_") or k == "paper_set"
    }
    with SessionLocal() as db:
        papers = [
            ExamPaper(exam_paper_code="CONFLICT_" + uuid4().hex[:12], **identity)
            for _ in range(2)
        ]
        db.add_all(papers)
        db.commit()
        paper_ids = sorted(p.id for p in papers)
    response = client.post(
        BASE,
        json=payload,
        headers={
            "Authorization": "Bearer " + admin_token,
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "PAPER_IDENTITY_CONFLICT"
    assert response.json()["context"]["exam_paper_ids"] == paper_ids


def test_review_session_must_reference_frozen_result(workflow):
    from app.db.base import SessionLocal
    from app.db.models_processing_workflows import ProcessingReviewSession

    with SessionLocal() as db:
        db.add(
            ProcessingReviewSession(
                id=uuid4(),
                revision_id=UUID(workflow[2]["revision_id"]),
                result_hash="f" * 64,
            )
        )
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()


def test_openapi_contains_strict_workflow_request_and_response_contracts(client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    for name in (
        "WorkflowCreate",
        "RevisionCreate",
        "WorkflowDetailDto",
        "WorkflowMaterialDto",
        "OperationDto",
    ):
        assert schemas[name]["additionalProperties"] is False
    properties = schemas["WorkflowDetailDto"]["properties"]
    assert {
        "row_version",
        "revision_id",
        "materials",
        "allowed_actions",
        "usage",
    } <= properties.keys()
    assert "execution_token" not in schemas["OperationDto"]["properties"]
