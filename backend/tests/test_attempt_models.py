"""T01 数据模型与 Alembic 迁移的库内证据。

测试库由 ``tests/conftest.py`` 每次从空 schema 迁移到 head 后建立，因此本文件
同时覆盖 T01-A2（三表、列、约束、索引与开发文档 2.3 一致）与 T01-A5（约束实际
生效）。app.* 一律延迟导入：conftest 在夹具内把 engine 绑定到测试库，模块级
导入会让 engine 提前绑定开发库（见 conftest 的安全护栏）。
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# 各表列：(列名, information_schema.data_type, is_nullable, 最大长度)
ATTEMPTS_COLUMNS = [
    ("id", "bigint", "NO", None),
    ("attempt_code", "character varying", "NO", 36),
    ("student_id", "bigint", "NO", None),
    ("exam_paper_id", "bigint", "NO", None),
    ("import_batch_id", "bigint", "NO", None),
    ("attempt_key", "character varying", "NO", 64),
    ("request_fingerprint", "character varying", "NO", 64),
    ("submitted_at", "timestamp with time zone", "NO", None),
    ("question_count", "integer", "NO", None),
    ("correct_count", "integer", "NO", None),
    ("correct_rate", "smallint", "NO", None),
    ("practice_score", "smallint", "YES", None),
    ("score_breakdown", "jsonb", "NO", None),
]

ATTEMPT_ANSWERS_COLUMNS = [
    ("id", "bigint", "NO", None),
    ("attempt_id", "bigint", "NO", None),
    ("question_no", "integer", "NO", None),
    ("question_id", "bigint", "NO", None),
    ("passage_type", "character varying", "NO", 32),
    ("question_text", "text", "NO", None),
    ("option_a", "text", "NO", None),
    ("option_b", "text", "NO", None),
    ("option_c", "text", "NO", None),
    ("option_d", "text", "NO", None),
    ("correct_option", "character varying", "NO", 1),
    ("selected_option", "character varying", "YES", 1),
    ("is_correct", "boolean", "NO", None),
    ("explanation_text", "text", "NO", None),
]

ATTEMPT_REJECTIONS_COLUMNS = [
    ("id", "bigint", "NO", None),
    ("student_id", "bigint", "NO", None),
    ("exam_paper_id", "bigint", "NO", None),
    ("attempt_key", "character varying", "NO", 64),
    ("request_fingerprint", "character varying", "NO", 64),
    ("rejection_kind", "character varying", "NO", 32),
    ("detail", "jsonb", "YES", None),
    ("created_at", "timestamp with time zone", "NO", None),
]

# 约束全名（数据库侧）：conname -> contype（p/u/f/c）
EXPECTED_CONSTRAINTS = {
    "attempts": {
        "pk_attempts": "p",
        "uq_attempts_attempt_code": "u",
        "uq_attempts_student_attempt_key": "u",
        "fk_attempts_student_id_users": "f",
        "fk_attempts_exam_paper_id_exam_papers": "f",
        "fk_attempts_import_batch_id_import_batches": "f",
        "ck_attempts_question_count_positive": "c",
        "ck_attempts_correct_count_range": "c",
        "ck_attempts_correct_rate_range": "c",
        "ck_attempts_practice_score_range": "c",
    },
    "attempt_answers": {
        "pk_attempt_answers": "p",
        "uq_attempt_answers_attempt_question_no": "u",
        "uq_attempt_answers_attempt_question_id": "u",
        "fk_attempt_answers_attempt_id_attempts": "f",
        "ck_attempt_answers_correctness": "c",
        "ck_attempt_answers_question_id_positive": "c",
        "ck_attempt_answers_question_no_positive": "c",
        "ck_attempt_answers_correct_option_domain": "c",
        "ck_attempt_answers_selected_option_domain": "c",
    },
    "attempt_rejections": {
        "pk_attempt_rejections": "p",
        "uq_attempt_rejections_student_attempt_key": "u",
        "fk_attempt_rejections_student_id_users": "f",
        "ck_attempt_rejections_rejection_kind_domain": "c",
    },
}

# 外键删除动作：fk 名 -> confdeltype（r=RESTRICT，c=CASCADE）
EXPECTED_FK_DELETE_RULES = {
    "fk_attempts_student_id_users": "r",
    "fk_attempts_exam_paper_id_exam_papers": "r",
    "fk_attempts_import_batch_id_import_batches": "r",
    "fk_attempt_answers_attempt_id_attempts": "c",
    "fk_attempt_rejections_student_id_users": "r",
}

EXPECTED_INDEXES = {
    "attempts": {
        "pk_attempts",
        "uq_attempts_attempt_code",
        "uq_attempts_student_attempt_key",
        "ix_attempts_student_paper",
        "ix_attempts_paper",
        "ix_attempts_submitted_at",
    },
    "attempt_answers": {
        "pk_attempt_answers",
        "uq_attempt_answers_attempt_question_no",
        "uq_attempt_answers_attempt_question_id",
        "ix_attempt_answers_attempt",
    },
    "attempt_rejections": {
        "pk_attempt_rejections",
        "uq_attempt_rejections_student_attempt_key",
    },
}

MODULE1_TABLES = {"users", "roles", "user_roles", "token_revocations"}
MODULE2_TABLES = {
    "audio_files",
    "exam_papers",
    "import_batches",
    "content_groups",
    "passages",
    "transcript_segments",
    "questions",
    "presentations",
    "content_checks",
    "paper_visibility",
    "visibility_audit_logs",
}


@pytest.fixture
def db():
    """独立会话；结束时回滚，测试不提交任何写入。"""

    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _columns(db, table: str) -> list[tuple]:
    rows = db.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"table": table},
    ).all()
    return [tuple(row) for row in rows]


def _parents(db) -> tuple[int, int, int]:
    """用种子学生 + 新建试卷/批次作为 attempts 的外键父记录。"""

    from app.db.models_listening import ExamPaper, ImportBatch

    tag = uuid.uuid4().hex[:12]
    student_id = db.execute(
        text("SELECT id FROM users WHERE username = 'student'")
    ).scalar_one()
    paper = ExamPaper(
        exam_paper_code=f"T01_{tag}",
        exam_level="CET4",
        exam_year=2025,
        exam_month=6,
        paper_set=1,
    )
    db.add(paper)
    db.flush()
    batch = ImportBatch(
        exam_paper_id=paper.id,
        batch_code=f"T01_B_{tag}",
        status="active",
        is_current=True,
    )
    db.add(batch)
    db.flush()
    return student_id, paper.id, batch.id


def _attempt(db, *, attempt_key=None, **overrides):
    from app.db.models_attempt import Attempt

    student_id, paper_id, batch_id = _parents(db)
    values = {
        "attempt_code": uuid.uuid4().hex,
        "student_id": student_id,
        "exam_paper_id": paper_id,
        "import_batch_id": batch_id,
        "attempt_key": attempt_key or uuid.uuid4().hex,
        "request_fingerprint": "f" * 64,
        "question_count": 1,
        "correct_count": 0,
        "correct_rate": 0,
        "practice_score": None,
        "score_breakdown": {
            "available": False,
            "rule": "t01-test",
            "reason": "test",
            "groups": {},
        },
    }
    values.update(overrides)
    attempt = Attempt(**values)
    db.add(attempt)
    db.flush()
    return attempt


def _answer(db, attempt, **overrides):
    from app.db.models_attempt import AttemptAnswer

    values = {
        "attempt_id": attempt.id,
        "question_no": 1,
        "question_id": 101,
        "passage_type": "conversation",
        "question_text": "T01 question",
        "option_a": "A text",
        "option_b": "B text",
        "option_c": "C text",
        "option_d": "D text",
        "correct_option": "A",
        "selected_option": None,
        "is_correct": False,
        "explanation_text": "",
    }
    values.update(overrides)
    answer = AttemptAnswer(**values)
    db.add(answer)
    db.flush()
    return answer


# ---------------------------------------------------------------------------
# T01-A2：结构（表 / 列 / 约束 / 索引）与既有表共存
# ---------------------------------------------------------------------------


def test_a2_tables_exist_and_existing_tables_untouched(db):
    rows = db.execute(
        text(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
    ).scalars()
    names = set(rows)
    assert {"attempts", "attempt_answers", "attempt_rejections"} <= names
    assert MODULE1_TABLES <= names
    assert MODULE2_TABLES <= names
    assert len(MODULE2_TABLES) == 11


def test_a2_alembic_version_is_0005(db):
    version = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0005_attempt_system"


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("attempts", ATTEMPTS_COLUMNS),
        ("attempt_answers", ATTEMPT_ANSWERS_COLUMNS),
        ("attempt_rejections", ATTEMPT_REJECTIONS_COLUMNS),
    ],
)
def test_a2_columns_match_contract(db, table, expected):
    assert _columns(db, table) == expected


@pytest.mark.parametrize(("table", "expected"), EXPECTED_CONSTRAINTS.items())
def test_a2_constraint_names_and_types(db, table, expected):
    rows = db.execute(
        text(
            """
            SELECT c.conname, c.contype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = :table
              AND c.contype IN ('p', 'u', 'f', 'c')
            """
        ),
        {"table": table},
    ).all()
    actual = {name: kind for name, kind in rows}
    assert actual == expected


def test_a2_foreign_key_delete_rules(db):
    rows = db.execute(
        text(
            """
            SELECT c.conname, c.confdeltype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND c.contype = 'f'
              AND t.relname IN ('attempts', 'attempt_answers', 'attempt_rejections')
            ORDER BY c.conname
            """
        )
    ).all()
    assert {name: action for name, action in rows} == EXPECTED_FK_DELETE_RULES


def test_a2_attempt_rejections_exam_paper_has_no_foreign_key(db):
    fk_columns = db.execute(
        text(
            """
            SELECT a.attname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN unnest(c.conkey) AS k(attnum) ON true
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
            WHERE n.nspname = 'public' AND t.relname = 'attempt_rejections'
              AND c.contype = 'f'
            """
        )
    ).scalars()
    assert "exam_paper_id" not in set(fk_columns)


@pytest.mark.parametrize(("table", "expected"), EXPECTED_INDEXES.items())
def test_a2_index_names(db, table, expected):
    names = set(
        db.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = :table
                """
            ),
            {"table": table},
        ).scalars()
    )
    assert names == expected


def test_a2_attempts_lookup_index_column_order(db):
    indexdef = db.execute(
        text(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = 'ix_attempts_student_paper'
            """
        )
    ).scalar_one()
    assert "(student_id, exam_paper_id)" in indexdef


def test_a6_model_metadata_names_match_database(db):
    """模型侧约束/索引名（命名约定展开后）与迁移落库名一致。"""

    from app.db import models_attempt  # noqa: F401 - 注册模型到 metadata
    from app.db.base import Base

    for table_name, expected in EXPECTED_CONSTRAINTS.items():
        table = Base.metadata.tables[table_name]
        model_constraints = {c.name for c in table.constraints if c.name}
        assert model_constraints == set(expected), table_name

        db_constraints = set(
            db.execute(
                text(
                    """
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON t.oid = c.conrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    WHERE n.nspname = 'public' AND t.relname = :table
                      AND c.contype IN ('p', 'u', 'f', 'c')
                    """
                ),
                {"table": table_name},
            ).scalars()
        )
        assert model_constraints == db_constraints, table_name

        model_indexes = {i.name for i in table.indexes}
        constraint_indexes = {
            name for name, kind in expected.items() if kind in ("p", "u")
        }
        assert model_indexes == EXPECTED_INDEXES[table_name] - constraint_indexes


# ---------------------------------------------------------------------------
# T01-A5：约束实际生效（真实 INSERT 触发数据库拒绝）
# ---------------------------------------------------------------------------


def test_a5_valid_row_is_accepted(db):
    attempt = _attempt(db)
    assert attempt.id is not None
    answer = _answer(db, attempt)
    assert answer.id is not None


def test_a5_duplicate_student_attempt_key_is_rejected(db):
    _attempt(db, attempt_key="same-key")
    with pytest.raises(IntegrityError) as excinfo:
        _attempt(db, attempt_key="same-key")
    assert "uq_attempts_student_attempt_key" in str(excinfo.value)


def test_a5_duplicate_attempt_code_is_rejected(db):
    code = uuid.uuid4().hex
    _attempt(db, attempt_code=code)
    with pytest.raises(IntegrityError) as excinfo:
        _attempt(db, attempt_code=code)
    assert "uq_attempts_attempt_code" in str(excinfo.value)


def test_a5_question_count_positive_is_enforced(db):
    with pytest.raises(IntegrityError) as excinfo:
        _attempt(db, question_count=0, correct_count=0, correct_rate=0)
    assert "ck_attempts_question_count_positive" in str(excinfo.value)


def test_a5_correct_count_range_is_enforced(db):
    with pytest.raises(IntegrityError) as excinfo:
        _attempt(db, question_count=1, correct_count=2, correct_rate=100)
    assert "ck_attempts_correct_count_range" in str(excinfo.value)


def test_a5_correct_rate_range_is_enforced(db):
    with pytest.raises(IntegrityError) as excinfo:
        _attempt(db, correct_rate=101)
    assert "ck_attempts_correct_rate_range" in str(excinfo.value)


def test_a5_practice_score_range_is_enforced(db):
    with pytest.raises(IntegrityError) as excinfo:
        _attempt(db, practice_score=250)
    assert "ck_attempts_practice_score_range" in str(excinfo.value)


def test_a5_correctness_check_rejects_unanswered_marked_correct(db):
    attempt = _attempt(db)
    with pytest.raises(IntegrityError) as excinfo:
        _answer(db, attempt, selected_option=None, is_correct=True)
    assert "ck_attempt_answers_correctness" in str(excinfo.value)


def test_a5_correctness_check_rejects_mismatched_letter(db):
    attempt = _attempt(db)
    with pytest.raises(IntegrityError) as excinfo:
        _answer(db, attempt, selected_option="B", is_correct=True)
    assert "ck_attempt_answers_correctness" in str(excinfo.value)


def test_a5_duplicate_question_no_is_rejected(db):
    attempt = _attempt(db)
    _answer(db, attempt, question_no=1, question_id=101)
    with pytest.raises(IntegrityError) as excinfo:
        _answer(db, attempt, question_no=1, question_id=102)
    assert "uq_attempt_answers_attempt_question_no" in str(excinfo.value)


def test_a5_duplicate_question_id_is_rejected(db):
    attempt = _attempt(db)
    _answer(db, attempt, question_no=1, question_id=101)
    with pytest.raises(IntegrityError) as excinfo:
        _answer(db, attempt, question_no=2, question_id=101)
    assert "uq_attempt_answers_attempt_question_id" in str(excinfo.value)


def test_a5_invalid_letters_are_rejected(db):
    attempt = _attempt(db)
    with pytest.raises(IntegrityError) as excinfo:
        _answer(db, attempt, correct_option="E")
    assert "ck_attempt_answers_correct_option_domain" in str(excinfo.value)


def test_a5_action_letter_space_is_original_paper_only(db):
    attempt = _attempt(db)
    with pytest.raises(IntegrityError) as excinfo:
        _answer(db, attempt, selected_option="a", is_correct=False)
    assert "ck_attempt_answers_selected_option_domain" in str(excinfo.value)


def test_a5_rejection_marker_rules(db):
    from app.db.models_attempt import AttemptRejection

    student_id = db.execute(
        text("SELECT id FROM users WHERE username = 'student'")
    ).scalar_one()
    marker = AttemptRejection(
        student_id=student_id,
        # 允许不存在的试卷 id：无外键，AS-07 的“试卷不存在”也能落标记。
        exam_paper_id=9223372036854775807,
        attempt_key="reject-key",
        request_fingerprint="f" * 64,
        rejection_kind="paper_not_accessible",
    )
    db.add(marker)
    db.flush()
    assert marker.id is not None

    with pytest.raises(IntegrityError) as excinfo:
        db.add(
            AttemptRejection(
                student_id=student_id,
                exam_paper_id=9223372036854775807,
                attempt_key="reject-key",
                request_fingerprint="f" * 64,
                rejection_kind="content_version_mismatch",
            )
        )
        db.flush()
    assert "uq_attempt_rejections_student_attempt_key" in str(excinfo.value)


def test_a5_rejection_kind_domain_is_enforced(db):
    from app.db.models_attempt import AttemptRejection

    student_id = db.execute(
        text("SELECT id FROM users WHERE username = 'student'")
    ).scalar_one()
    db.add(
        AttemptRejection(
            student_id=student_id,
            exam_paper_id=1,
            attempt_key="bad-kind",
            request_fingerprint="f" * 64,
            rejection_kind="other",
        )
    )
    with pytest.raises(IntegrityError) as excinfo:
        db.flush()
    assert "ck_attempt_rejections_rejection_kind_domain" in str(excinfo.value)


def test_a5_attempts_fk_restrict_blocks_student_delete(db):
    attempt = _attempt(db)
    with pytest.raises(IntegrityError) as excinfo:
        db.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": attempt.student_id},
        )
    assert "fk_attempts_student_id_users" in str(excinfo.value)


def test_a5_attempts_fk_restrict_blocks_batch_delete(db):
    attempt = _attempt(db)
    with pytest.raises(IntegrityError) as excinfo:
        db.execute(
            text("DELETE FROM import_batches WHERE id = :id"),
            {"id": attempt.import_batch_id},
        )
    assert "fk_attempts_import_batch_id_import_batches" in str(excinfo.value)


def test_a5_answers_cascade_with_attempt(db):
    attempt = _attempt(db)
    _answer(db, attempt)
    attempt_id = attempt.id
    db.execute(text("DELETE FROM attempts WHERE id = :id"), {"id": attempt_id})
    remaining = db.execute(
        text("SELECT count(*) FROM attempt_answers WHERE attempt_id = :id"),
        {"id": attempt_id},
    ).scalar_one()
    assert remaining == 0
