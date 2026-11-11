"""为应有题量保留原卷核对依据，并使旧的自动推导基准失效。

Revision ID: 0004_expected_count_source
Revises: 0003_exam_paper_expected_count

0003 按当前题数回填的值无法独立证明完整性。保留历史迁移，升级时清空
这些无来源基准，并追加失败检查；账号、业务内容、可见操作历史均保留。
补录原卷依据后仍须重新确认，不能用旧检查结果直接恢复学生访问。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_expected_count_source"
down_revision = "0003_exam_paper_expected_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exam_papers", sa.Column("expected_question_count_source", JSONB(), nullable=True)
    )
    op.execute("UPDATE exam_papers SET expected_question_count = NULL")
    op.execute(
        """
        INSERT INTO content_checks (exam_paper_id, batch_id, is_passed, issues, checked_at)
        SELECT b.exam_paper_id, b.id, FALSE,
               '[{"kind":"expected_count_missing","message":"升级后须补录原卷题量及来源，并重新确认可见"}]'::jsonb,
               GREATEST(CURRENT_TIMESTAMP, COALESCE(
                   (SELECT MAX(c.checked_at) + INTERVAL '1 microsecond'
                    FROM content_checks c WHERE c.batch_id = b.id), CURRENT_TIMESTAMP))
        FROM import_batches b WHERE b.status = 'active'
        """
    )


def downgrade() -> None:
    # 不恢复无可信来源的历史基准，也不复活旧的通过结论。
    op.drop_column("exam_papers", "expected_question_count_source")
