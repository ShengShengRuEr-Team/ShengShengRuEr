"""Store review status and preserve legacy hidden answers."""

import sqlalchemy as sa
from alembic import op

revision = "0012_wrong_answer_review_state"
down_revision = "0011_wrong_answer_notebook"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wrong_answer_states",
        sa.Column("answer_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column(
            "learning_status", sa.String(16), server_default="pending", nullable=False
        ),
        sa.Column("is_hidden", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "learning_status IN ('pending', 'mastered')", name="learning_status"
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"], ["attempt_answers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("answer_id"),
    )
    op.execute(
        "INSERT INTO wrong_answer_states (answer_id, is_hidden) "
        "SELECT answer_id, true FROM wrong_answer_dismissals"
    )
    op.drop_table("wrong_answer_dismissals")


def downgrade():
    op.create_table(
        "wrong_answer_dismissals",
        sa.Column("answer_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id"], ["attempt_answers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("answer_id"),
    )
    op.execute(
        "INSERT INTO wrong_answer_dismissals (answer_id) "
        "SELECT answer_id FROM wrong_answer_states WHERE is_hidden"
    )
    op.drop_table("wrong_answer_states")
