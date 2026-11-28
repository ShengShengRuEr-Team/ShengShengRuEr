"""Join library management and the previously merged wrong-answer notebook.

Keep both deployed migration ancestries and all existing notebook state.
"""

revision = "0015_library_wrong_answers"
down_revision = ("0014_library_provider_ledger", "0013_wrong_answer_state_times")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    raise RuntimeError("Retain financial audit, notebook and library history")
