"""exam_papers.expected_question_count

Revision ID: 0003_exam_paper_expected_count
Revises: 0002_module2_listening_papers
Create Date: 2026-11-04

验收报告 F02：完整题量检查只比较「题目数 == 映射数」，末尾整题一起缺失时仍能通过。
新增 expected_question_count 记录该套选定原卷的应有题量，首次导入时固定，
后续批次对照校验。字段可空，已有数据需在下次导入或人工补录时填充。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_exam_paper_expected_count"
down_revision: str | None = "0002_module2_listening_papers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exam_papers",
        sa.Column("expected_question_count", sa.Integer(), nullable=True),
    )
    # 对已有数据按当前批次的题量回填，避免降级再升级后检查报「未记录应有题量」。
    op.execute(
        """
        UPDATE exam_papers p
        SET expected_question_count = sub.cnt
        FROM (
            SELECT b.exam_paper_id, COUNT(q.id) AS cnt
            FROM import_batches b
            JOIN questions q ON q.batch_id = b.id
            WHERE b.is_current IS TRUE AND b.status = 'active'
            GROUP BY b.exam_paper_id
        ) AS sub
        WHERE p.id = sub.exam_paper_id AND p.expected_question_count IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("exam_papers", "expected_question_count")
