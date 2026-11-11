"""T03 幂等仓储集成测试：查键、短路、拒绝标记、限次计数、指纹与锁键。

使用 conftest 提供的独立 PostgreSQL 测试库（每 session 从空 schema 迁移重建），
不触碰开发库；app.* 在夹具/函数内延迟导入。
"""

import ast
import hashlib
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def keys():
    import app.repositories.attempt_keys as module

    return module


@pytest.fixture
def db():
    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def scenario():
    """独立试卷/批次；测试结束后清理本夹具范围内已提交的数据。"""

    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper, ImportBatch

    tag = uuid.uuid4().hex[:12]
    with SessionLocal() as session:
        student_id = session.execute(
            text("SELECT id FROM users WHERE username = :name"),
            {"name": "student"},
        ).scalar_one()
        paper = ExamPaper(
            exam_paper_code=f"T03_{tag}",
            exam_level="CET4",
            exam_year=2025,
            exam_month=6,
            paper_set=1,
        )
        session.add(paper)
        session.flush()
        batch = ImportBatch(
            exam_paper_id=paper.id,
            batch_code=f"T03_B_{tag}",
            status="active",
            is_current=True,
        )
        session.add(batch)
        session.commit()
        ids = (student_id, paper.id, batch.id)

    yield ids

    with SessionLocal() as session:
        session.execute(
            text(
                "DELETE FROM attempt_answers WHERE attempt_id IN "
                "(SELECT id FROM attempts WHERE exam_paper_id = :paper)"
            ),
            {"paper": ids[1]},
        )
        session.execute(
            text("DELETE FROM attempts WHERE exam_paper_id = :paper"),
            {"paper": ids[1]},
        )
        session.execute(
            text("DELETE FROM attempt_rejections WHERE exam_paper_id = :paper"),
            {"paper": ids[1]},
        )
        session.execute(
            text("DELETE FROM import_batches WHERE id = :batch"),
            {"batch": ids[2]},
        )
        session.execute(
            text("DELETE FROM exam_papers WHERE id = :paper"),
            {"paper": ids[1]},
        )
        session.commit()


def _new_attempt(
    student_id: int,
    paper_id: int,
    batch_id: int,
    *,
    attempt_key: str,
    fingerprint: str,
    attempt_code: str | None = None,
):
    from app.db.models_attempt import Attempt

    return Attempt(
        attempt_code=attempt_code or uuid.uuid4().hex,
        student_id=student_id,
        exam_paper_id=paper_id,
        import_batch_id=batch_id,
        attempt_key=attempt_key,
        request_fingerprint=fingerprint,
        question_count=2,
        correct_count=0,
        correct_rate=0,
        practice_score=None,
        score_breakdown={"available": False, "rule": "t03-test", "reason": "test"},
    )


def _new_answers():
    from app.db.models_attempt import AttemptAnswer

    answers = []
    for question_no, question_id in ((1, 101), (2, 102)):
        answers.append(
            AttemptAnswer(
                question_no=question_no,
                question_id=question_id,
                passage_type="conversation",
                question_text=f"T03 question {question_no}",
                option_a="A text",
                option_b="B text",
                option_c="C text",
                option_d="D text",
                correct_option="A",
                selected_option=None,
                is_correct=False,
                explanation_text="",
            )
        )
    return answers


def _payload(loaded, answers):
    from app.schemas_attempts import AttemptSubmitIn

    return AttemptSubmitIn.model_validate(
        {"loaded_question_ids": loaded, "answers": answers}
    )


# --------------------------------------------------------------------------- #
# T03-A1：同键同内容 → REPLAY_SUCCESS，返回原 attempt_code
# --------------------------------------------------------------------------- #
def test_a1_replay_success_returns_original_code(keys, db, scenario):
    student_id, paper_id, batch_id = scenario
    attempt = _new_attempt(
        student_id,
        paper_id,
        batch_id,
        attempt_key="a1-key",
        fingerprint="a" * 64,
    )
    keys.insert_attempt_with_answers(db, attempt, _new_answers())
    db.commit()
    original_code = attempt.attempt_code

    outcome = keys.resolve_existing(db, student_id, "a1-key", "a" * 64)

    assert outcome.status is keys.ResolveStatus.REPLAY_SUCCESS
    assert outcome.attempt is not None
    assert outcome.attempt.attempt_code == original_code
    assert outcome.rejection is None


# --------------------------------------------------------------------------- #
# T03-A2：同键不同指纹 → KEY_CONFLICT，不新增、不留标记
# --------------------------------------------------------------------------- #
def test_a2_key_conflict_does_not_write(keys, db, scenario):
    student_id, paper_id, batch_id = scenario
    _attempt = _new_attempt(
        student_id,
        paper_id,
        batch_id,
        attempt_key="a2-key",
        fingerprint="b" * 64,
    )
    keys.insert_attempt_with_answers(db, _attempt, _new_answers())
    db.commit()

    outcome = keys.resolve_existing(db, student_id, "a2-key", "c" * 64)

    assert outcome.status is keys.ResolveStatus.KEY_CONFLICT
    assert outcome.rejection is None
    assert keys.count_success_attempts(db, student_id, paper_id) == 1
    assert keys.get_rejection_by_key(db, student_id, "a2-key") is None


# --------------------------------------------------------------------------- #
# T03-A3：不存在的键 → NONE
# --------------------------------------------------------------------------- #
def test_a3_unknown_key_returns_none(keys, db, scenario):
    student_id, _paper_id, _batch_id = scenario

    outcome = keys.resolve_existing(db, student_id, "never-used-key", "d" * 64)

    assert outcome.status is keys.ResolveStatus.NONE
    assert outcome.attempt is None
    assert outcome.rejection is None


# --------------------------------------------------------------------------- #
# T03-A4：写拒绝标记后同键重试 → REJECTED，标记数不增、无 attempt
# --------------------------------------------------------------------------- #
def test_a4_rejection_is_permanent_and_single(keys, db, scenario):
    student_id, paper_id, _batch_id = scenario

    first = keys.insert_rejection(
        db,
        student_id=student_id,
        exam_paper_id=paper_id,
        attempt_key="a4-key",
        request_fingerprint="e" * 64,
        rejection_kind=keys.REJECTION_KIND_PAPER_NOT_ACCESSIBLE,
        detail={"reason": "test"},
    )
    db.commit()
    second = keys.insert_rejection(
        db,
        student_id=student_id,
        exam_paper_id=paper_id,
        attempt_key="a4-key",
        request_fingerprint="f" * 64,
        rejection_kind=keys.REJECTION_KIND_CONTENT_VERSION_MISMATCH,
    )
    db.commit()

    assert first.id == second.id
    assert (
        second.rejection_kind == keys.REJECTION_KIND_PAPER_NOT_ACCESSIBLE
    )

    outcome = keys.resolve_existing(db, student_id, "a4-key", "0" * 64)
    assert outcome.status is keys.ResolveStatus.REJECTED
    assert outcome.rejection is not None
    assert outcome.rejection.id == first.id
    assert (
        outcome.rejection.rejection_kind
        == keys.REJECTION_KIND_PAPER_NOT_ACCESSIBLE
    )
    assert keys.count_success_attempts(db, student_id, paper_id) == 0
    total_markers = db.execute(
        text(
            "SELECT count(*) FROM attempt_rejections "
            "WHERE student_id = :student AND attempt_key = :key"
        ),
        {"student": student_id, "key": "a4-key"},
    ).scalar_one()
    assert total_markers == 1


# --------------------------------------------------------------------------- #
# T03-A5：同键并发只产生 1 条 attempt；双方得到同一结果
# --------------------------------------------------------------------------- #
def test_a5_concurrent_same_key_yields_single_attempt(keys, scenario):
    from app.db.base import SessionLocal

    student_id, paper_id, batch_id = scenario
    attempt_key = f"a5-{uuid.uuid4().hex[:10]}"
    fingerprint = "1" * 64
    barrier = threading.Barrier(2)
    results: dict[str, tuple[str, str | None]] = {}
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        with SessionLocal() as session:
            try:
                barrier.wait(timeout=10)
                keys.lock_attempt_key(session, student_id, attempt_key)
                outcome = keys.resolve_existing(
                    session, student_id, attempt_key, fingerprint
                )
                if outcome.status is keys.ResolveStatus.NONE:
                    attempt = _new_attempt(
                        student_id,
                        paper_id,
                        batch_id,
                        attempt_key=attempt_key,
                        fingerprint=fingerprint,
                    )
                    keys.insert_attempt_with_answers(
                        session, attempt, _new_answers()
                    )
                    session.commit()
                    results[name] = (
                        keys.ResolveStatus.NONE.value,
                        attempt.attempt_code,
                    )
                else:
                    results[name] = (
                        outcome.status.value,
                        outcome.attempt.attempt_code
                        if outcome.attempt is not None
                        else None,
                    )
                    session.rollback()
            except BaseException as exc:  # noqa: BLE001 - 线程内失败需带回主线程
                errors.append(exc)
                session.rollback()

    threads = [
        threading.Thread(target=worker, args=(f"worker-{index}",))
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    codes = {code for _status, code in results.values()}
    assert len(codes) == 1
    statuses = sorted(status for status, _code in results.values())
    assert statuses == [
        keys.ResolveStatus.NONE.value,
        keys.ResolveStatus.REPLAY_SUCCESS.value,
    ]

    with SessionLocal() as session:
        total = session.execute(
            text(
                "SELECT count(*) FROM attempts WHERE student_id = :student "
                "AND attempt_key = :key"
            ),
            {"student": student_id, "key": attempt_key},
        ).scalar_one()
        assert total == 1


def test_a5_integrity_conflict_rollback_then_replay(keys, db, scenario):
    student_id, paper_id, batch_id = scenario
    attempt_key = f"a5b-{uuid.uuid4().hex[:10]}"
    fingerprint = "2" * 64

    winner = _new_attempt(
        student_id,
        paper_id,
        batch_id,
        attempt_key=attempt_key,
        fingerprint=fingerprint,
    )
    keys.insert_attempt_with_answers(db, winner, _new_answers())
    db.commit()
    original_code = winner.attempt_code

    loser = _new_attempt(
        student_id,
        paper_id,
        batch_id,
        attempt_key=attempt_key,
        fingerprint=fingerprint,
    )
    with pytest.raises(IntegrityError):
        keys.insert_attempt_with_answers(db, loser, _new_answers())
    db.rollback()

    # 结束失败事务后，新事务内取键锁并重读，得到同一回放结果。
    keys.lock_attempt_key(db, student_id, attempt_key)
    outcome = keys.resolve_existing(db, student_id, attempt_key, fingerprint)
    db.rollback()

    assert outcome.status is keys.ResolveStatus.REPLAY_SUCCESS
    assert outcome.attempt is not None
    assert outcome.attempt.attempt_code == original_code
    assert keys.count_success_attempts(db, student_id, paper_id) == 1


def test_a5_student_paper_lock_runs(keys, db, scenario):
    student_id, paper_id, _batch_id = scenario

    keys.lock_attempt_key(db, student_id, "lock-key")
    keys.lock_student_paper(db, student_id, paper_id)
    assert keys.count_success_attempts(db, student_id, paper_id) == 0
    db.rollback()


# --------------------------------------------------------------------------- #
# T03-A6：指纹规范化
# --------------------------------------------------------------------------- #
def test_a6_fingerprint_is_order_insensitive(keys, scenario):
    _student_id, paper_id, _batch_id = scenario
    first = _payload(
        [103, 101, 102],
        [
            {"question_id": 103, "selected_option": "C"},
            {"question_id": 101, "selected_option": "A"},
        ],
    )
    second = _payload(
        [101, 102, 103],
        [
            {"question_id": 101, "selected_option": "A"},
            {"question_id": 103, "selected_option": "C"},
        ],
    )

    fingerprint = keys.build_request_fingerprint(paper_id, first)

    assert fingerprint == keys.build_request_fingerprint(paper_id, second)
    assert len(fingerprint) == 64
    assert int(fingerprint, 16) >= 0


def test_a6_fingerprint_differs_on_content_or_paper(keys, scenario):
    _student_id, paper_id, _batch_id = scenario
    base = _payload(
        [101, 102],
        [{"question_id": 101, "selected_option": "A"}],
    )
    other_letter = _payload(
        [101, 102],
        [{"question_id": 101, "selected_option": "B"}],
    )
    other_loaded = _payload(
        [101, 103],
        [{"question_id": 101, "selected_option": "A"}],
    )

    fingerprint = keys.build_request_fingerprint(paper_id, base)

    assert fingerprint != keys.build_request_fingerprint(paper_id, other_letter)
    assert fingerprint != keys.build_request_fingerprint(paper_id, other_loaded)
    assert fingerprint != keys.build_request_fingerprint(paper_id + 1, base)


def test_a6_fingerprint_empty_answers(keys, scenario):
    _student_id, paper_id, _batch_id = scenario
    empty = _payload([], [])

    fingerprint = keys.build_request_fingerprint(paper_id, empty)

    assert len(fingerprint) == 64
    assert fingerprint == keys.build_request_fingerprint(paper_id, _payload([], []))


# --------------------------------------------------------------------------- #
# T03-A7：锁键算法固定、跨进程一致、不使用 hash()/hashtext()
# --------------------------------------------------------------------------- #
def test_a7_lock_objid_formula_and_text(keys):
    lock_text = keys.attempt_key_lock_text(7, "0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40")
    expected = int.from_bytes(
        hashlib.sha256(lock_text.encode("utf-8")).digest()[:4],
        "big",
        signed=True,
    )

    assert lock_text == "attempt-key:7:0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40"
    assert (
        keys.attempt_limit_lock_text(7, 3) == "attempt-limit:7:3"
    )
    assert keys.lock_objid(lock_text) == expected
    assert -(2**31) <= expected < 2**31
    assert keys.lock_objid(lock_text) == keys.lock_objid(lock_text)


def test_a7_lock_objid_matches_independent_process(keys, tmp_path):
    lock_text = "attempt-key:42:0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40"
    expected = keys.lock_objid(lock_text)
    result_file = tmp_path / "objid.txt"
    stderr_file = tmp_path / "stderr.txt"
    script = (
        "import sys\n"
        "from app.repositories.attempt_keys import lock_objid\n"
        "with open(sys.argv[1], 'w', encoding='utf-8') as handle:\n"
        "    handle.write(str(lock_objid(sys.argv[2])))\n"
    )

    with result_file.open("w", encoding="utf-8") as stdout, (
        stderr_file.open("w", encoding="utf-8")
    ) as stderr:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(result_file), lock_text],
            cwd=str(BACKEND_DIR),
            stdout=stdout,
            stderr=stderr,
        )

    assert completed.returncode == 0, stderr_file.read_text(encoding="utf-8")
    assert result_file.read_text(encoding="utf-8").strip() == str(expected)


def test_a7_no_builtin_hash_or_hashtext(keys):
    source = Path(keys.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    builtin_hash_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "hash"
    ]
    hashtext_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "hashtext"
    ]

    assert builtin_hash_calls == []
    assert hashtext_calls == []
    assert "hashlib.sha256(" in source
    assert "pg_advisory_xact_lock" in source
