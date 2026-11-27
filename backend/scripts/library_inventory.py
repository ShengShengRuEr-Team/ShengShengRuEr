"""Read-only pre-migration inventory; never merges identities or changes results."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from app.db.base import engine

    queries = {
        "migration_heads": (
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        ),
        "paper_identity_conflicts": """
            SELECT exam_level,exam_year,exam_month,
            paper_set,content_scope,
            array_agg(id ORDER BY id) AS exam_paper_ids FROM exam_papers
            GROUP BY exam_level,exam_year,exam_month,paper_set,content_scope
            HAVING count(*)>1""",
        "workflow_paper_conflicts": """SELECT exam_paper_id,
            array_agg(id::text) AS workflow_ids
            FROM processing_workflows WHERE exam_paper_id IS NOT NULL
            GROUP BY exam_paper_id HAVING count(*)>1""",
        "legacy_execution_states": """SELECT processing_state,count(*) AS count
            FROM processing_workflows
            GROUP BY processing_state ORDER BY processing_state""",
        "historical_budget": """SELECT billing_status,count(*) AS count,
            sum(coalesce(charged_usd,reserved_usd)) AS committed_usd
            FROM processing_llm_attempts
            GROUP BY billing_status ORDER BY billing_status""",
        "unresolved_budget_identity": """SELECT a.id,a.run_key,t.id AS task_id
            FROM processing_llm_attempts a
            LEFT JOIN processing_tasks t ON t.id=a.task_id
            WHERE t.request->'exam_paper'->>'exam_level' IS NULL
            OR t.request->'exam_paper'->>'exam_year' IS NULL
            OR t.request->'exam_paper'->>'exam_month' IS NULL
            OR t.request->'exam_paper'->>'paper_set' IS NULL""",
    }
    report = {
        "observed_at": datetime.now(UTC).isoformat(),
        "mode": "read_only",
        "business_data_changed": False,
    }
    with engine.connect() as connection:
        connection.execute(
            text("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        for key, query in queries.items():
            report[key] = [
                dict(row) for row in connection.execute(text(query)).mappings()
            ]
        connection.rollback()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"Read-only inventory written to {args.output}")


if __name__ == "__main__":
    main()
