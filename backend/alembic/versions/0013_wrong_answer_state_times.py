"""Track real review-state changes and normalize pending review times."""

import sqlalchemy as sa
from alembic import op

revision = "0013_wrong_answer_state_times"
down_revision = "0012_wrong_answer_review_state"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "wrong_answer_states",
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "UPDATE wrong_answer_states "
        "SET updated_at = GREATEST(created_at, reviewed_at), "
        "reviewed_at = CASE WHEN learning_status = 'mastered' THEN reviewed_at END"
    )
    op.alter_column(
        "wrong_answer_states",
        "updated_at",
        nullable=False,
        server_default=sa.func.now(),
    )


def downgrade():
    op.drop_column("wrong_answer_states", "updated_at")
