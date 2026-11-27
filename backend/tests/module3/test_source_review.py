from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "environment", ["development", "test", "production", "staging"]
)
def test_waiver_stays_local_and_bound_to_source(environment):
    from app.services.processing.source_review import listening_review_satisfied

    approval = SimpleNamespace(
        decision="approved",
        artifact_hash="a" * 64,
        items={
            "listening_items": [],
            "listening_review": {
                "state": "waived_by_user",
                "reference": "Synthetic explicit authorization",
                "actual_listening_performed": False,
                "source_artifact_hash": "a" * 64,
            },
        },
    )
    settings = SimpleNamespace(app_env=environment)
    assert listening_review_satisfied(approval, settings) is (
        environment in {"development", "test"}
    )
    approval.items["listening_review"]["source_artifact_hash"] = "b" * 64
    assert not listening_review_satisfied(approval, settings)
    approval.items["listening_review"]["source_artifact_hash"] = "a" * 64
    approval.items["listening_review"]["reference"] = ""
    assert not listening_review_satisfied(approval, settings)
