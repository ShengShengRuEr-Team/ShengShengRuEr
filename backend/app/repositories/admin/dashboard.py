"""首页汇总查询：单条 CTE SQL 计算全部卡片，禁止逐卷查询。

口径见需求 §10.1：
- paper_count：exam_papers 按主键计数（同卷多批次不重复）；
- 待确认/失败：当前唯一 active 批次的最新内容检查与最新可见性；
- 学生计数：student 角色且不含 admin 角色，按用户去重；
- 7 天提交：attempts.submitted_at ∈ [window_start, window_end)。
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

DASHBOARD_SQL = text(
    """
WITH current_batch AS (
    SELECT id
    FROM import_batches
    WHERE is_current IS TRUE AND status = 'active'
    ORDER BY id DESC
    LIMIT 1
),
latest_check AS (
    SELECT DISTINCT ON (exam_paper_id) exam_paper_id, is_passed
    FROM content_checks
    WHERE batch_id = (SELECT id FROM current_batch)
    ORDER BY exam_paper_id, checked_at DESC, id DESC
),
latest_visibility AS (
    SELECT DISTINCT ON (exam_paper_id) exam_paper_id, is_visible
    FROM paper_visibility
    WHERE batch_id = (SELECT id FROM current_batch)
    ORDER BY exam_paper_id, updated_at DESC, id DESC
),
student_users AS (
    SELECT u.id, u.status
    FROM users u
    JOIN user_roles ur ON ur.user_id = u.id
    JOIN roles r ON r.id = ur.role_id AND r.role_key = 'student'
    WHERE NOT EXISTS (
        SELECT 1
        FROM user_roles ur2
        JOIN roles r2 ON r2.id = ur2.role_id
        WHERE ur2.user_id = u.id AND r2.role_key = 'admin'
    )
)
SELECT
    (SELECT count(*) FROM exam_papers) AS paper_count,
    (
        SELECT count(*)
        FROM latest_check c
        LEFT JOIN latest_visibility v USING (exam_paper_id)
        WHERE c.is_passed IS TRUE
          AND (v.is_visible IS NULL OR v.is_visible IS FALSE)
    ) AS awaiting_visibility_count,
    (
        SELECT count(*) FROM latest_check WHERE is_passed IS FALSE
    ) AS failed_check_count,
    (
        SELECT count(DISTINCT id) FROM student_users WHERE status = 'active'
    ) AS active_student_count,
    (
        SELECT count(DISTINCT id) FROM student_users WHERE status = 'disabled'
    ) AS disabled_student_count,
    (
        SELECT count(*)
        FROM attempts
        WHERE submitted_at >= :window_start
          AND submitted_at < :window_end
    ) AS successful_attempts_7d
"""
)

CARD_KEYS = (
    "paper_count",
    "awaiting_visibility_count",
    "failed_check_count",
    "active_student_count",
    "disabled_student_count",
    "successful_attempts_7d",
)


def compute_cards(
    connection: Connection,
    *,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, int]:
    row = connection.execute(
        DASHBOARD_SQL,
        {"window_start": window_start, "window_end": window_end},
    ).mappings().one()
    return {key: int(row[key] or 0) for key in CARD_KEYS}
