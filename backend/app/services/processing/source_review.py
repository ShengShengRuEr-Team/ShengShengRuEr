"""Keep local user waivers distinct from actual listening records."""


def listening_review_satisfied(approval, settings):
    if not approval or approval.decision != "approved":
        return False
    review = approval.items.get("listening_review", {})
    if review.get("state") == "waived_by_user":
        return (
            settings.app_env in {"development", "test"}
            and review.get("actual_listening_performed") is False
            and bool(str(review.get("reference", "")).strip())
            and review.get("source_artifact_hash") == approval.artifact_hash
            and not approval.items.get("listening_items")
        )
    return bool(approval.items.get("listening_items"))
