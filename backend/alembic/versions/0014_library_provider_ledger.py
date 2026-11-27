"""Add provider-specific original currency and stable budget ownership."""

from alembic import op
from sqlalchemy import text

revision = "0014_library_provider_ledger"
down_revision = "0013_library_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE processing_llm_attempts
      ADD COLUMN provider varchar(32) NOT NULL DEFAULT 'deepseek',
      ADD COLUMN official_endpoint_id varchar(64),
      ADD COLUMN price_version varchar(64),
      ADD COLUMN currency varchar(8) NOT NULL DEFAULT 'USD',
      ADD COLUMN original_reserved numeric(18,10), ADD COLUMN original_charged numeric(18,10),
      ADD COLUMN exchange_rate jsonb, ADD COLUMN provider_manifest jsonb, ADD COLUMN usage_detail jsonb,
      ADD COLUMN budget_scope_id varchar(64) NOT NULL DEFAULT 'module3-stage-v1',
      ADD COLUMN paper_budget_key varchar(64)""")
    # Frozen historical prices and requests remain untouched. Ownership is derived
    # only where the task contains a complete natural identity.
    import hashlib
    import json

    connection = op.get_bind()
    rows = connection.execute(
        text(
            "SELECT a.id,t.request FROM processing_llm_attempts a JOIN processing_tasks t ON t.id=a.task_id"
        )
    ).all()
    for identity, request in rows:
        paper = request.get("exam_paper", {})
        names = ("exam_level", "exam_year", "exam_month", "paper_set")
        if all(paper.get(k) is not None for k in names):
            payload = {**{k: paper[k] for k in names}, "content_scope": "listening"}
            digest = hashlib.sha256(
                json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            connection.execute(
                text(
                    "UPDATE processing_llm_attempts SET paper_budget_key=:key WHERE id=:id"
                ),
                {"key": digest, "id": identity},
            )
    op.execute(
        "CREATE INDEX ix_llm_stable_paper_budget ON processing_llm_attempts(budget_scope_id,paper_budget_key)"
    )


def downgrade():
    raise RuntimeError("Retain financial audit columns when rolling back the app")
