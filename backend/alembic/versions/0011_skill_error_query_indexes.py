"""Add read indexes for the skill/error query API.

Revision ID: 0011_skill_error_query_indexes
Revises: 0010_m3_distractor_coverage
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_skill_error_query_indexes"
down_revision = "0010_m3_distractor_coverage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sq_skill_question_scope",
        "skill_question_relations",
        ["skill_id", "batch_id"],
        unique=False,
        postgresql_where=sa.text(
            "is_current AND relation_kind = 'QUESTION_SKILL'"
        ),
    )
    op.create_index(
        "ix_sq_error_question_scope",
        "error_question_relations",
        ["error_cause_id", "batch_id"],
        unique=False,
        postgresql_where=sa.text(
            "is_current AND relation_kind = 'QUESTION_ERROR_CANDIDATE'"
        ),
    )
    op.create_index(
        "ix_sq_skill_owner",
        "skill_question_relations",
        ["owner_relation_id"],
        unique=False,
        postgresql_where=sa.text(
            "is_current AND relation_kind = 'SKILL_EVIDENCE'"
        ),
    )
    op.create_index(
        "ix_sq_error_owner",
        "error_question_relations",
        ["owner_relation_id"],
        unique=False,
        postgresql_where=sa.text(
            "is_current AND relation_kind = 'CANDIDATE_EVIDENCE'"
        ),
    )
    op.create_index(
        "ix_sq_presentation_question",
        "presentations",
        ["question_id", "batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_sq_answer_evidence",
        "other_relations",
        ["question_id", "batch_id"],
        unique=False,
        postgresql_where=sa.text(
            "is_current AND relation_kind = 'ANSWER_EVIDENCE'"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_sq_answer_evidence", table_name="other_relations")
    op.drop_index("ix_sq_presentation_question", table_name="presentations")
    op.drop_index("ix_sq_error_owner", table_name="error_question_relations")
    op.drop_index("ix_sq_skill_owner", table_name="skill_question_relations")
    op.drop_index("ix_sq_error_question_scope", table_name="error_question_relations")
    op.drop_index("ix_sq_skill_question_scope", table_name="skill_question_relations")
