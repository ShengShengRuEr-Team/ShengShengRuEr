"""T04 准入、完整性、身份/版本与答案结构判定（仓储级测试）。

使用 conftest 的独立 PostgreSQL 测试库（每 session 从空 schema 迁移重建），
不触碰开发库；app.* 在夹具/函数内延迟导入。本文件只做仓储级判定断言，
不写 HTTP / 不写永久标记（由 T06 覆盖）。
"""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

IDENTITY_MAPPING = {"A": "A", "B": "B", "C": "C", "D": "D"}


@pytest.fixture
def db():
    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="module")
def attempt_content():
    import app.repositories.attempt_content as module

    return module


def _make_paper(
    db,
    tmp_path,
    *,
    tag: str | None = None,
    expected_count: int = 25,
    expected_source: bool = True,
    with_audio: bool = True,
    write_audio: bool = True,
    playback_audio: bool = True,
):
    from app.db.models_listening import AudioFile, ExamPaper

    tag = tag or uuid.uuid4().hex[:12]
    audio_path = tmp_path / f"t04_{tag}.m4a"
    audio = AudioFile(
        audio_code=f"T04A_{tag}",
        storage_key=f"t04_{tag}.m4a",
        duration_ms=1000,
        mime_type="audio/mpeg",
        file_hash="a" * 64,
    )
    db.add(audio)
    db.flush()
    paper = ExamPaper(
        exam_paper_code=f"T04_{tag}",
        exam_level="CET4",
        exam_year=2025,
        exam_month=6,
        paper_set=1,
        playback_audio_id=audio.id if (with_audio and playback_audio) else None,
        expected_question_count=expected_count,
        expected_question_count_source={"kind": "test"} if expected_source else None,
    )
    db.add(paper)
    db.flush()
    if write_audio:
        audio_path.write_bytes(b"T04-TEST-AUDIO")
    return SimpleNamespace(
        paper=paper,
        audio=audio,
        settings=SimpleNamespace(audio_storage_path=tmp_path),
        audio_path=audio_path,
        tag=tag,
    )


def _add_batch(
    db,
    paper,
    *,
    tag: str,
    is_current: bool = True,
    count: int = 25,
    check_passed: bool = True,
    visible: bool = True,
    mapping: dict | None = None,
    presentation_nos: list[int] | None = None,
    skip_last_presentation: bool = False,
    passage_type: str = "短篇新闻",
    correct_base: str = "A",
):
    from app.db.models_listening import (
        ContentCheck,
        ImportBatch,
        PaperVisibility,
        Passage,
        Presentation,
        Question,
    )

    batch = ImportBatch(
        exam_paper_id=paper.id,
        audio_id=paper.playback_audio_id,
        batch_code=f"T04B_{tag}",
        status="active",
        is_current=is_current,
    )
    db.add(batch)
    db.flush()
    passage = Passage(
        batch_id=batch.id,
        exam_paper_id=paper.id,
        audio_id=paper.playback_audio_id,
        passage_code=f"T04P_{tag}",
        passage_index=1,
        passage_type=passage_type,
        start_ms=0,
        end_ms=1000,
    )
    db.add(passage)
    db.flush()

    questions = []
    for index in range(1, count + 1):
        question = Question(
            batch_id=batch.id,
            passage_id=passage.id,
            question_code=f"T04Q_{tag}_{index}",
            question_text=f"T04 question {index}",
            option_a=f"q{index} option A",
            option_b=f"q{index} option B",
            option_c=f"q{index} option C",
            option_d=f"q{index} option D",
            correct_option=correct_base,
            explanation_text=f"T04 explanation {index}",
        )
        db.add(question)
        questions.append(question)
    db.flush()

    presentations = []
    limit = count - 1 if skip_last_presentation else count
    for position, question in enumerate(questions[:limit]):
        question_no = (
            presentation_nos[position]
            if presentation_nos is not None
            else position + 1
        )
        presentation = Presentation(
            batch_id=batch.id,
            exam_paper_id=paper.id,
            question_id=question.id,
            question_no=question_no,
            option_letter_mapping=mapping or dict(IDENTITY_MAPPING),
            mapping_source="test",
        )
        db.add(presentation)
        presentations.append(presentation)
    db.flush()

    db.add(
        ContentCheck(
            exam_paper_id=paper.id,
            batch_id=batch.id,
            is_passed=check_passed,
            issues=[],
        )
    )
    db.add(
        PaperVisibility(
            exam_paper_id=paper.id,
            batch_id=batch.id,
            is_visible=visible,
        )
    )
    db.flush()
    return SimpleNamespace(
        batch=batch,
        questions=questions,
        question_ids=[question.id for question in questions],
        presentations=presentations,
    )


def _make_content(db, tmp_path, **overrides):
    paper_scope = _make_paper(
        db,
        tmp_path,
        tag=overrides.pop("tag", None),
        expected_count=overrides.pop("expected_count", 25),
        expected_source=overrides.pop("expected_source", True),
        write_audio=overrides.pop("write_audio", True),
        playback_audio=overrides.pop("playback_audio", True),
    )
    content = _add_batch(db, paper_scope.paper, tag=paper_scope.tag, **overrides)
    return SimpleNamespace(
        paper=paper_scope.paper,
        audio=paper_scope.audio,
        settings=paper_scope.settings,
        audio_path=paper_scope.audio_path,
        tag=paper_scope.tag,
        batch=content.batch,
        questions=content.questions,
        question_ids=content.question_ids,
    )


def _answers(question_ids, letter: str = "A"):
    from app.schemas_attempts import AttemptAnswerIn

    return [
        AttemptAnswerIn(question_id=qid, selected_option=letter)
        for qid in question_ids
    ]


# --------------------------------------------------------------------------- #
# T04-A1：可访问 + 完整 loaded set + 合法 answers → ok，且固定 batch_id
# --------------------------------------------------------------------------- #
def test_a1_accessible_complete_loaded_is_ok(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)

    visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )
    assert visible is True
    assert paper is not None and paper.id == content.paper.id
    assert batch is not None and batch.id == content.batch.id

    questions = attempt_content.load_current_paper_questions(
        db, paper.id, batch.id
    )
    current_ids = [item.question_id for item in questions]
    outcome = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, current_ids, batch_id=batch.id
    )
    assert outcome.status is attempt_content.IdentityStatus.OK
    assert (
        attempt_content.validate_answers(
            current_ids, current_ids, _answers(current_ids)
        ).ok
        is True
    )
    attempt_content.check_paper_integrity(db, paper, batch, content.settings)


def test_a1_loaded_snapshot_fields_are_paper_space(db, tmp_path, attempt_content):
    content = _make_content(
        db,
        tmp_path,
        mapping={"A": "B", "B": "A", "C": "C", "D": "D"},
        correct_base="B",
    )
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )
    questions = attempt_content.load_current_paper_questions(db, paper.id, batch.id)

    first = questions[0]
    assert first.question_no == 1
    assert first.correct_paper_letter == "A"
    # 原卷 A 位展示的是题库 B 位文本（映射 A->B）
    assert first.options[0] == "q1 option B"
    assert first.options[1] == "q1 option A"
    assert first.passage_type == "短篇新闻"


# --------------------------------------------------------------------------- #
# T04-A2 / A2b：取消可见 / 不存在试卷 → visible=False
# --------------------------------------------------------------------------- #
def test_a2_invisible_paper_is_not_accessible(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path, visible=False)

    visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    assert visible is False
    assert paper is not None
    assert batch is not None


def test_a2b_missing_paper_is_not_accessible(db, tmp_path, attempt_content):
    visible, paper, batch = attempt_content.check_submit_access(db, 2**62)

    assert visible is False
    assert paper is None
    assert batch is None


def test_a2_check_not_passed_is_not_accessible(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path, check_passed=False)

    visible, _paper, _batch = attempt_content.check_submit_access(
        db, content.paper.id
    )
    assert visible is False


# --------------------------------------------------------------------------- #
# T04-A3：可访问 + 旧批次题目身份 → version_mismatch
# --------------------------------------------------------------------------- #
def test_a3_old_batch_identity_is_version_mismatch(db, tmp_path, attempt_content):
    paper_scope = _make_paper(db, tmp_path)
    old = _add_batch(db, paper_scope.paper, tag=f"{paper_scope.tag}_old", is_current=False)
    new = _add_batch(db, paper_scope.paper, tag=f"{paper_scope.tag}_new", is_current=True)

    visible, paper, batch = attempt_content.check_submit_access(
        db, paper_scope.paper.id
    )
    assert visible is True and batch.id == new.batch.id

    current_ids = [
        item.question_id
        for item in attempt_content.load_current_paper_questions(
            db, paper.id, batch.id
        )
    ]
    outcome = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, old.question_ids, batch_id=batch.id
    )

    assert outcome.status is attempt_content.IdentityStatus.VERSION_MISMATCH
    assert set(outcome.old_batch_ids) == set(old.question_ids)


# --------------------------------------------------------------------------- #
# T04-A4：可访问 + 他卷/不存在题目身份 → invalid_identity
# --------------------------------------------------------------------------- #
def test_a4_foreign_paper_identity_is_invalid(db, tmp_path, attempt_content):
    first = _make_content(db, tmp_path)
    second = _make_content(db, tmp_path)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, first.paper.id
    )
    current_ids = [
        item.question_id
        for item in attempt_content.load_current_paper_questions(
            db, paper.id, batch.id
        )
    ]

    outcome = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, second.question_ids, batch_id=batch.id
    )

    assert outcome.status is attempt_content.IdentityStatus.INVALID_IDENTITY
    assert set(outcome.foreign_ids) == set(second.question_ids)


def test_a4_nonexistent_identity_is_invalid(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )
    current_ids = [
        item.question_id
        for item in attempt_content.load_current_paper_questions(
            db, paper.id, batch.id
        )
    ]

    outcome = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, [2**62], batch_id=batch.id
    )

    assert outcome.status is attempt_content.IdentityStatus.INVALID_IDENTITY
    assert outcome.foreign_ids == (2**62,)


# --------------------------------------------------------------------------- #
# T04-A5：真子集 → incomplete；完全一致但乱序 → ok
# --------------------------------------------------------------------------- #
def test_a5_subset_is_incomplete_and_shuffled_full_set_is_ok(
    db, tmp_path, attempt_content
):
    content = _make_content(db, tmp_path)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )
    current_ids = [
        item.question_id
        for item in attempt_content.load_current_paper_questions(
            db, paper.id, batch.id
        )
    ]

    subset = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, current_ids[:-1], batch_id=batch.id
    )
    shuffled = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, list(reversed(current_ids)), batch_id=batch.id
    )

    assert subset.status is attempt_content.IdentityStatus.INCOMPLETE
    assert shuffled.status is attempt_content.IdentityStatus.OK


# --------------------------------------------------------------------------- #
# T04-A6：重复 question_id、答案含集合外 ID → 参数错误
# --------------------------------------------------------------------------- #
def test_a6_duplicate_loaded_identity_rejected(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    current_ids = content.question_ids

    result = attempt_content.validate_answers(
        [*current_ids, current_ids[0]], current_ids, []
    )

    assert result.ok is False
    assert result.reason == attempt_content.ANSWER_REASON_DUPLICATE_LOADED


def test_a6_duplicate_answer_identity_rejected(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    current_ids = content.question_ids
    answers = _answers([current_ids[0], current_ids[0]])

    result = attempt_content.validate_answers(current_ids, current_ids, answers)

    assert result.ok is False
    assert result.reason == attempt_content.ANSWER_REASON_DUPLICATE_ANSWER
    assert result.offending_ids == (current_ids[0],)


def test_a6_answer_outside_loaded_set_rejected(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    current_ids = content.question_ids
    answers = _answers([2**62])

    result = attempt_content.validate_answers(current_ids, current_ids, answers)

    assert result.ok is False
    assert result.reason == attempt_content.ANSWER_REASON_NOT_IN_LOADED
    assert result.offending_ids == (2**62,)


def test_a6_answer_not_in_current_batch_rejected(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    current_ids = content.question_ids
    old_identity = 2**62 - 1
    loaded_with_old = [*current_ids, old_identity]

    result = attempt_content.validate_answers(
        loaded_with_old, current_ids, _answers([old_identity])
    )

    assert result.ok is False
    assert result.reason == attempt_content.ANSWER_REASON_NOT_IN_CURRENT
    assert result.offending_ids == (old_identity,)


# --------------------------------------------------------------------------- #
# T04-A7：换批发生在加载前（看到新批）→ 按新批 ok
# --------------------------------------------------------------------------- #
def test_a7_new_batch_loaded_before_submit_is_ok(db, tmp_path, attempt_content):
    paper_scope = _make_paper(db, tmp_path)
    _add_batch(db, paper_scope.paper, tag=f"{paper_scope.tag}_old", is_current=False)
    new = _add_batch(db, paper_scope.paper, tag=f"{paper_scope.tag}_new", is_current=True)

    visible, paper, batch = attempt_content.check_submit_access(
        db, paper_scope.paper.id
    )
    assert visible is True and batch.id == new.batch.id

    current_ids = [
        item.question_id
        for item in attempt_content.load_current_paper_questions(
            db, paper.id, batch.id
        )
    ]
    outcome = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, current_ids, batch_id=batch.id
    )

    assert outcome.status is attempt_content.IdentityStatus.OK
    assert set(current_ids) == set(new.question_ids)


# --------------------------------------------------------------------------- #
# T04-A8：混合身份（旧批次 + 他卷）→ 版本优先
# --------------------------------------------------------------------------- #
def test_a8_mixed_identity_prefers_version_mismatch(db, tmp_path, attempt_content):
    paper_scope = _make_paper(db, tmp_path)
    old = _add_batch(db, paper_scope.paper, tag=f"{paper_scope.tag}_old", is_current=False)
    new = _add_batch(db, paper_scope.paper, tag=f"{paper_scope.tag}_new", is_current=True)
    other = _make_content(db, tmp_path)

    _visible, paper, batch = attempt_content.check_submit_access(
        db, paper_scope.paper.id
    )
    current_ids = [
        item.question_id
        for item in attempt_content.load_current_paper_questions(
            db, paper.id, batch.id
        )
    ]
    loaded = [old.question_ids[0], other.question_ids[0], *current_ids]

    outcome = attempt_content.classify_loaded_ids(
        db, paper.id, current_ids, loaded, batch_id=batch.id
    )

    assert outcome.status is attempt_content.IdentityStatus.VERSION_MISMATCH
    assert outcome.old_batch_ids == (old.question_ids[0],)


# --------------------------------------------------------------------------- #
# T04-A9：音频缺失/不可读 → PaperUnavailable(audio_unavailable)
# --------------------------------------------------------------------------- #
def test_a9_missing_audio_file_is_unavailable(db, tmp_path, attempt_content):
    content = _make_content(
        db, tmp_path, count=25, write_audio=False
    )
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == attempt_content.PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE


def test_a9_unreadable_audio_file_is_unavailable(
    db, tmp_path, attempt_content, monkeypatch
):
    content = _make_content(db, tmp_path)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    def _deny_open(self, *args, **kwargs):
        raise PermissionError("denied for test")

    monkeypatch.setattr(Path, "open", _deny_open)
    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == attempt_content.PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE


def test_a9_missing_audio_binding_is_unavailable(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path, playback_audio=False)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == attempt_content.PAPER_UNAVAILABLE_AUDIO_UNAVAILABLE


# --------------------------------------------------------------------------- #
# T04-A10：应有 25 题但删除第 25 题及映射、历史检查仍通过 → PaperUnavailable
# --------------------------------------------------------------------------- #
def test_a10_deleted_last_question_is_not_treated_as_complete(
    db, tmp_path, attempt_content
):
    content = _make_content(
        db,
        tmp_path,
        expected_count=25,
        count=24,
        check_passed=True,
        visible=True,
    )
    visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )
    assert visible is True  # 历史检查/可见性仍通过

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == (
        attempt_content.PAPER_UNAVAILABLE_QUESTION_COUNT_MISMATCH
    )


# --------------------------------------------------------------------------- #
# 完整性补充：题号覆盖 / 映射缺失 / presentation 缺失 / 应有题量来源
# --------------------------------------------------------------------------- #
def test_integrity_question_no_coverage_hole(db, tmp_path, attempt_content):
    content = _make_content(
        db,
        tmp_path,
        count=25,
        presentation_nos=list(range(1, 25)) + [26],
    )
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == (
        attempt_content.PAPER_UNAVAILABLE_QUESTION_NO_COVERAGE
    )


def test_integrity_missing_presentation(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path, skip_last_presentation=True)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == (
        attempt_content.PAPER_UNAVAILABLE_PRESENTATION_MISMATCH
    )


def test_integrity_invalid_option_mapping(db, tmp_path, attempt_content):
    content = _make_content(
        db,
        tmp_path,
        mapping={"A": "A", "B": "A", "C": "C", "D": "D"},
    )
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == (
        attempt_content.PAPER_UNAVAILABLE_OPTION_MAPPING_INVALID
    )


def test_integrity_missing_expected_count_source(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path, expected_source=False)
    _visible, paper, batch = attempt_content.check_submit_access(
        db, content.paper.id
    )

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.check_paper_integrity(db, paper, batch, content.settings)

    assert excinfo.value.reason == (
        attempt_content.PAPER_UNAVAILABLE_EXPECTED_COUNT_MISSING
    )


def test_load_questions_requires_matching_paper(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    other = _make_content(db, tmp_path)

    with pytest.raises(attempt_content.PaperUnavailable) as excinfo:
        attempt_content.load_current_paper_questions(
            db, other.paper.id, content.batch.id
        )

    assert excinfo.value.reason == (
        attempt_content.PAPER_UNAVAILABLE_PRESENTATION_MISMATCH
    )


def test_classify_fail_closed_without_batch_id(db, tmp_path, attempt_content):
    content = _make_content(db, tmp_path)
    current_ids = content.question_ids

    outcome = attempt_content.classify_loaded_ids(
        db, content.paper.id, [], current_ids
    )

    assert outcome.status is attempt_content.IdentityStatus.INVALID_IDENTITY
