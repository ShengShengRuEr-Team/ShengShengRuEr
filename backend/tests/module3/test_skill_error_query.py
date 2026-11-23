"""API contract tests for the read-only skill/error query."""

# The imported pipeline fixture is requested by name in test signatures.
# ruff: noqa: F811

from __future__ import annotations

import pytest

from tests.conftest import auth_headers
from tests.module3.test_workflow_pipeline import (  # noqa: F401
    complete_to_review,
    pipeline,
    synthetic_review_publish,
)

BASE = "/api/v1/admin/skill-error-query"


@pytest.fixture(autouse=True)
def ensure_artifact_parent(monkeypatch):
    import hashlib
    from pathlib import Path

    from app.module3 import contracts, workflow_worker

    def atomic_json(root, key, payload):
        path = Path(root) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = contracts.canonical_bytes(payload)
        path.write_bytes(blob)
        return hashlib.sha256(blob).hexdigest(), len(blob)

    monkeypatch.setattr(contracts, "atomic_json", atomic_json)
    monkeypatch.setattr(workflow_worker, "atomic_json", atomic_json)


def _published(client, c):
    artifacts = c["context"]["settings"].m3_path("m3_artifacts_dir")
    workflow_dir = artifacts / str(c["id"])
    for stage in (
        "workflow-start",
        "workflow-align",
        "workflow-source",
        "workflow-sample",
        "workflow-review",
        "workflow-publish",
    ):
        (workflow_dir / stage).mkdir(parents=True, exist_ok=True)
    complete_to_review(c)
    synthetic_review_publish(client, c)
    return c["detail"]()


def test_dictionary_and_questions_contract(
    client, admin_token, student_token, pipeline
):
    _published(client, pipeline)
    headers = auth_headers(admin_token)
    response = client.get(f"{BASE}/dictionary", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["skills"]) == 39
    assert len(data["error_causes"]) == 22
    assert data["scope_version"]
    skill_node = next(
        node
        for node in data["skills"]
        if node["level"] == 3 and node["question_count"] and node["code"]
    )
    skill_code = skill_node["code"]

    response = client.get(
        f"{BASE}/questions",
        params={"subject_type": "skill", "subject_code": skill_code, "limit": 20},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert page["question_count"] >= 1
    assert page["primary_question_count"] >= 1
    item = page["items"][0]
    assert item["annotation_status"] == "approved"
    assert item["annotation_status_label"] == "正式审核通过"
    assert item["paper"]["exam_paper_code"]

    question_id = item["question_id"]
    response = client.get(
        f"{BASE}/questions/{question_id}",
        headers=headers,
        params={"expected_scope_version": page["scope_version"]},
    )
    assert response.status_code == 200, response.text
    detail_data = response.json()["data"]
    assert detail_data["question"]["id"] == question_id
    assert detail_data["answer_state"] == "available"
    assert detail_data["correct_option"]["base_letter"] in {"A", "B", "C", "D"}
    correct_letters = {
        detail_data["correct_option"]["display_letter"],
        detail_data["correct_option"]["base_letter"],
    }
    for option in detail_data["error_options"]:
        assert option["base_letter"] not in correct_letters
    assert detail_data["personal_error"]["state"] == "not_in_scope"

    parent_code = skill_node["parent_code"]
    assert parent_code
    response = client.get(
        f"{BASE}/questions",
        params={
            "subject_type": "skill_category",
            "subject_code": parent_code,
            "limit": 20,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["matched_leaves"]

    # A stale scope token must not be silently accepted.
    response = client.get(
        f"{BASE}/questions",
        params={
            "subject_type": "skill",
            "subject_code": skill_code,
            "expected_scope_version": "0" * 64,
        },
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "SCOPE_CHANGED"

    # Pagination without the first-page token is rejected.
    response = client.get(
        f"{BASE}/questions",
        params={
            "subject_type": "skill",
            "subject_code": skill_code,
            "cursor": 20,
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "SCOPE_REQUIRED"

    # Student and anonymous callers never receive query data.
    response = client.get(f"{BASE}/dictionary", headers=auth_headers(student_token))
    assert response.status_code == 403
    response = client.get(f"{BASE}/dictionary")
    assert response.status_code == 401

    response = client.get(f"{BASE}/questions/999999999", headers=headers)
    assert response.status_code == 404


def test_invalid_subject_and_role(client, admin_token, pipeline):
    _published(client, pipeline)
    headers = auth_headers(admin_token)
    response = client.get(
        f"{BASE}/questions",
        params={"subject_type": "skill", "subject_code": "K5"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_SUBJECT"
    response = client.get(
        f"{BASE}/questions",
        params={
            "subject_type": "error_cause",
            "subject_code": "E4.3",
            "role": "primary",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_SUBJECT"
