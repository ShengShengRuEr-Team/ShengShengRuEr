"""Persist notebook removals independently of graded answers."""

import sqlalchemy as sa
from alembic import op

revision = "0011_wrong_answer_notebook"
down_revision = "0010_m3_distractor_coverage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wrong_answer_dismissals",
        sa.Column("answer_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id"], ["attempt_answers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("answer_id"),
    )


def downgrade():
    op.drop_table("wrong_answer_dismissals")
