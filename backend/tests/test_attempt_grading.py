"""T05 判分、快照与 249 分练习估分（纯函数表驱动测试）。

不查库、不写库；app.* 在夹具内延迟导入。
"""

import pytest

TYPE_LAYOUT = (("短篇新闻", 7), ("长对话", 8), ("听力篇章", 10))


@pytest.fixture(scope="module")
def g():
    import app.services.grading as module

    return module


def _types(layout=TYPE_LAYOUT):
    return [passage_type for passage_type, count in layout for _ in range(count)]


def _make_questions(
    g,
    *,
    types=None,
    correct_letter="A",
    explanation="解析文本",
    options=None,
):
    type_list = _types() if types is None else list(types)
    questions = []
    for index, passage_type in enumerate(type_list):
        question_no = index + 1
        question_options = options or (
            f"T{question_no}A",
            f"T{question_no}B",
            f"T{question_no}C",
            f"T{question_no}D",
        )
        questions.append(
            g.QuestionSnapshotInput(
                question_no=question_no,
                question_id=1000 + question_no,
                passage_type=passage_type,
                question_text=f"题干 {question_no}",
                options=question_options,
                correct_paper_letter=correct_letter,
                explanation_text=explanation,
            )
        )
    return questions


def _answers(g, questions, selector=lambda question: "A"):
    return [
        g.AnswerInput(
            question_id=question.question_id,
            selected_option=selector(question),
        )
        for question in questions
    ]


def _facts(g, correct_pattern):
    """按 25 题标准分组生成估分事实；correct_pattern 为 25 个布尔值。"""

    types = _types()
    return [
        g.PracticeFact(passage_type=types[index], is_correct=correct_pattern[index])
        for index in range(len(types))
    ]


# --------------------------------------------------------------------------- #
# T05-A1：25 题全对
# --------------------------------------------------------------------------- #
def test_a1_all_correct(g):
    questions = _make_questions(g)
    result = g.grade(questions, _answers(g, questions))

    assert result.question_count == 25
    assert result.correct_count == 25
    assert result.correct_rate == 100
    assert result.practice_score.available is True
    assert result.practice_score.value == 249
    assert all(draft.is_correct for draft in result.answer_drafts)
    assert all(draft.selected_option == "A" for draft in result.answer_drafts)


def test_a1_snapshot_fields_are_self_sufficient(g):
    questions = _make_questions(
        g, types=["短篇新闻"] * 25, explanation="原文不含答案"
    )
    result = g.grade(questions, _answers(g, questions))

    first = result.answer_drafts[0]
    assert first.question_no == 1
    assert first.question_id == questions[0].question_id
    assert first.passage_type == "短篇新闻"
    assert first.question_text == "题干 1"
    assert (first.option_a, first.option_b, first.option_c, first.option_d) == (
        "T1A",
        "T1B",
        "T1C",
        "T1D",
    )
    assert first.correct_option == "A"
    assert first.explanation_text == "原文不含答案"


# --------------------------------------------------------------------------- #
# T05-A2：24/25（错题在听力篇章 → 235；错在新闻 → 按公式 242）
# --------------------------------------------------------------------------- #
def test_a2_wrong_lecture_question_is_96_and_235(g):
    questions = _make_questions(g)
    # 第 25 题属于听力篇章，选错
    result = g.grade(
        questions,
        _answers(g, questions, lambda question: "B" if question.question_no == 25 else "A"),
    )

    assert result.correct_count == 24
    assert result.correct_rate == 96
    assert result.practice_score.available is True
    assert result.practice_score.value == 235

    groups = {
        group["passage_type"]: group
        for group in result.practice_score.score_breakdown["groups"]
    }
    assert groups["短篇新闻"]["correct_count"] == 7
    assert groups["长对话"]["correct_count"] == 8
    assert groups["听力篇章"]["correct_count"] == 9
    assert groups["听力篇章"]["question_count"] == 10


def test_a2_wrong_news_question_recomputed_by_formula(g):
    questions = _make_questions(g)
    result = g.grade(
        questions,
        _answers(g, questions, lambda question: "B" if question.question_no == 1 else "A"),
    )

    assert result.correct_count == 24
    assert result.correct_rate == 96
    # 新闻 6/7、长对话 8/8、篇章 10/10：34*249/35 = 241.886 -> half-up 242
    assert result.practice_score.value == 242


# --------------------------------------------------------------------------- #
# T05-A3：部分作答 / 空 answers
# --------------------------------------------------------------------------- #
def test_a3_partial_answers_unanswered_counted_wrong(g):
    questions = _make_questions(g)
    answered = [
        g.AnswerInput(question_id=question.question_id, selected_option="A")
        for question in questions[:5]
    ]
    result = g.grade(questions, answered)

    assert result.correct_count == 5
    assert result.correct_rate == 20
    assert result.practice_score.value == 36  # 新闻 5/7 -> 35.571 -> 36
    unanswered = result.answer_drafts[5:]
    assert all(draft.selected_option is None for draft in unanswered)
    assert all(draft.is_correct is False for draft in unanswered)


def test_a3_empty_answers_is_zero(g):
    questions = _make_questions(g)
    result = g.grade(questions, [])

    assert result.correct_count == 0
    assert result.correct_rate == 0
    assert result.practice_score.available is True
    assert result.practice_score.value == 0
    assert all(draft.selected_option is None for draft in result.answer_drafts)
    assert all(draft.is_correct is False for draft in result.answer_drafts)


def test_a3_question_count_uses_submitted_paper_size(g):
    questions = _make_questions(g)
    result = g.grade(questions[:25], [])

    assert result.question_count == 25
    assert result.correct_rate == 0


# --------------------------------------------------------------------------- #
# T05-A4：重排题（原卷字母空间）
# --------------------------------------------------------------------------- #
def test_a4_reordered_options_use_paper_letters(g):
    types = _types()
    reordered = ("B 文字", "A 文字", "C 文字", "D 文字")
    questions = _make_questions(
        g, types=types, correct_letter="B", options=reordered
    )
    questions[0] = g.QuestionSnapshotInput(
        question_no=1,
        question_id=questions[0].question_id,
        passage_type=questions[0].passage_type,
        question_text=questions[0].question_text,
        options=("TB", "TA", "TC", "TD"),
        correct_paper_letter="B",
        explanation_text="",
    )

    correct = g.grade(
        questions,
        _answers(g, questions, lambda question: "B" if question.question_no == 1 else "A"),
    )
    wrong_letter = g.grade(
        questions,
        _answers(g, questions, lambda question: "A" if question.question_no == 1 else "A"),
    )

    assert correct.answer_drafts[0].is_correct is True
    assert correct.answer_drafts[0].correct_option == "B"
    assert correct.answer_drafts[0].option_a == "TB"
    assert wrong_letter.answer_drafts[0].is_correct is False


# --------------------------------------------------------------------------- #
# T05-A5：空解析原样快照
# --------------------------------------------------------------------------- #
def test_a5_empty_explanation_kept_as_empty_string(g):
    questions = _make_questions(g, explanation="")
    result = g.grade(questions, _answers(g, questions))

    assert all(draft.explanation_text == "" for draft in result.answer_drafts)
    assert result.correct_rate == 100
    assert result.practice_score.value == 249


# --------------------------------------------------------------------------- #
# T05-A6：估分不可用原因（固定顺序）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("types", "expected_reason"),
    [
        (_types()[:24], "not_standard_25"),
        (_types()[:-1] + [""], "question_type_missing"),
        (_types()[:-1] + ["讲话"], "unknown_type"),
        (
            ["短篇新闻"] * 8 + ["长对话"] * 7 + ["听力篇章"] * 10,
            "type_count_mismatch",
        ),
    ],
)
def test_a6_reason_codes(g, types, expected_reason):
    questions = _make_questions(g, types=types)
    result = g.grade(questions, _answers(g, questions))

    assert result.practice_score.available is False
    assert result.practice_score.value is None
    assert result.practice_score.reason == expected_reason
    assert result.practice_score.max == 249
    assert result.practice_score.label == "练习估分，非官方成绩"
    breakdown = result.practice_score.score_breakdown
    assert breakdown["rule"] == g.CET_LISTENING_249_V1
    assert breakdown["available"] is False
    assert breakdown["reason"] == expected_reason


def test_a6_reason_priority_missing_before_unknown_and_count(g):
    types = _types()[:-2] + ["讲话", ""]
    facts = [
        g.PracticeFact(passage_type=passage_type, is_correct=True)
        for passage_type in types
    ]

    result = g.estimate_practice_score(facts)

    assert result.reason == "question_type_missing"


def test_a6_reason_priority_unknown_before_count_mismatch(g):
    types = ["短篇新闻"] * 8 + ["长对话"] * 7 + ["听力篇章"] * 9 + ["讲话"]
    facts = [
        g.PracticeFact(passage_type=passage_type, is_correct=True)
        for passage_type in types
    ]

    result = g.estimate_practice_score(facts)

    assert result.reason == "unknown_type"


# --------------------------------------------------------------------------- #
# T05-A7：整数 half-up 舍入（无 float / 银行家舍入）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("correct_count", "question_count", "expected"),
    [
        (1, 3, 33),
        (2, 3, 67),
        (1, 8, 13),  # 12.5% -> 13（Python round(12.5) 会得 12）
        (0, 25, 0),
        (25, 25, 100),
        (24, 25, 96),
    ],
)
def test_a7_correct_rate_half_up(g, correct_count, question_count, expected):
    result = g.correct_rate(correct_count, question_count)

    assert result == expected
    assert isinstance(result, int)


def test_a7_estimate_half_up_examples(g):
    all_correct = _facts(g, [True] * 25)
    all_wrong = _facts(g, [False] * 25)

    assert g.estimate_practice_score(all_correct).value == 249
    assert g.estimate_practice_score(all_wrong).value == 0

    # 文档示例：新闻 5/7、长对话 6/8、篇章 8/10 -> 192.086 -> 192
    pattern = [False] * 25
    for index in (0, 1, 2, 3, 4):  # 短篇新闻答对 5 题
        pattern[index] = True
    for index in range(7, 13):  # 长对话答对 6 题
        pattern[index] = True
    for index in range(15, 23):  # 听力篇章答对 8 题
        pattern[index] = True
    assert g.estimate_practice_score(_facts(g, pattern)).value == 192


# --------------------------------------------------------------------------- #
# T05-A8：正确率与估分分开输出、不得互替
# --------------------------------------------------------------------------- #
def test_a8_rate_and_practice_score_are_separate(g):
    questions = _make_questions(g)
    result = g.grade(
        questions,
        _answers(g, questions, lambda question: "B" if question.question_no == 25 else "A"),
    )

    assert result.correct_rate == 96
    assert result.practice_score.value == 235
    assert result.correct_rate != result.practice_score.value
    assert result.practice_score.label == "练习估分，非官方成绩"
    assert result.practice_score.reason is None


# --------------------------------------------------------------------------- #
# 数据一致性 / 输入防护
# --------------------------------------------------------------------------- #
def test_empty_question_set_is_data_error(g):
    with pytest.raises(g.GradingDataError):
        g.grade([], [])


def test_duplicate_answer_is_data_error(g):
    questions = _make_questions(g)
    answers = [
        g.AnswerInput(question_id=questions[0].question_id, selected_option="A"),
        g.AnswerInput(question_id=questions[0].question_id, selected_option="B"),
    ]
    with pytest.raises(g.GradingDataError):
        g.grade(questions, answers)


def test_answer_outside_question_set_is_data_error(g):
    questions = _make_questions(g)
    with pytest.raises(g.GradingDataError):
        g.grade(questions, [g.AnswerInput(question_id=2**62, selected_option="A")])


def test_correct_rate_out_of_range_is_data_error(g):
    with pytest.raises(g.GradingDataError):
        g.correct_rate(26, 25)
    with pytest.raises(g.GradingDataError):
        g.correct_rate(0, 0)
