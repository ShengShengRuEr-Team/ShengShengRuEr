"""作答判分、逐题快照与 249 分练习估分（T05）。

纯函数模块：不查库、不写库、不读文件、不返回 HTTP、不写永久拒绝标记。
输入由 T04 严格换算到**原卷字母空间**后提供（``PaperQuestion``），本模块
不做映射换算，只做逐题判分、快照 draft、汇总、整数 half-up 正确率与
``Fraction`` 精确估分；结果由 T06 写入 ``attempts`` / ``attempt_answers``。

口径来源：开发文档 2.5.3/2.5.4、需求 BR-13–17 与 7.2 S-1–S-9、D4。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from app.schemas_attempts import PRACTICE_SCORE_LABEL, PRACTICE_SCORE_MAX

# 练习估分规则版本（写入 score_breakdown，回放不重新计算）。
CET_LISTENING_249_V1 = "cet-listening-249-v1"

STANDARD_QUESTION_COUNT = 25
TOTAL_WEIGHT = 35

# 估分不可用原因（reason 判定顺序固定，REV-05）。
REASON_NOT_STANDARD_25 = "not_standard_25"
REASON_QUESTION_TYPE_MISSING = "question_type_missing"
REASON_UNKNOWN_TYPE = "unknown_type"
REASON_TYPE_COUNT_MISMATCH = "type_count_mismatch"


class GradingDataError(Exception):
    """判分/估分输入内部不一致（非 HTTP；T06 转 500，不输出错误数值）。"""


@dataclass(frozen=True, slots=True)
class TypeGroupRule:
    """官方听力题型分组：题库篇章类型 -> 标准题量 + 权重（合计 35）。"""

    passage_type: str
    question_count: int
    weight: int


TYPE_GROUPS = (
    TypeGroupRule("短篇新闻", 7, 7),
    TypeGroupRule("长对话", 8, 8),
    TypeGroupRule("听力篇章", 10, 20),
)
GROUP_BY_TYPE = {group.passage_type: group for group in TYPE_GROUPS}


# --------------------------------------------------------------------------- #
# 纯输入结构（T06 负责从 T04 PaperQuestion / T02 AttemptAnswerIn 适配）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class QuestionSnapshotInput:
    """判分输入：已换算到原卷字母空间、选项已按原卷 A–D 顺序排列。"""

    question_no: int
    question_id: int
    passage_type: str
    question_text: str
    options: tuple[str, str, str, str]
    correct_paper_letter: str
    explanation_text: str


@dataclass(frozen=True, slots=True)
class AnswerInput:
    """学生作答：``selected_option=None`` 表示未作答。"""

    question_id: int
    selected_option: str | None = None


@dataclass(frozen=True, slots=True)
class PracticeFact:
    """估分事实：一题的题型与正误。"""

    passage_type: str
    is_correct: bool


# --------------------------------------------------------------------------- #
# 输出结构
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AttemptAnswerDraft:
    """逐题快照结果（对应 T01 ``attempt_answers`` 列，供 T06 落库）。"""

    question_no: int
    question_id: int
    passage_type: str
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    selected_option: str | None
    is_correct: bool
    explanation_text: str


@dataclass(frozen=True, slots=True)
class PracticeScoreResult:
    """练习估分结果；不可用时 ``value=None``（不输出 0 分）。"""

    available: bool
    value: int | None
    max: int
    label: str
    reason: str | None
    score_breakdown: dict


@dataclass(frozen=True, slots=True)
class GradeResult:
    """判分汇总 + 逐题快照 + 估分；正确率与估分分开输出、不得互替。"""

    answer_drafts: tuple[AttemptAnswerDraft, ...]
    question_count: int
    correct_count: int
    correct_rate: int
    practice_score: PracticeScoreResult


# --------------------------------------------------------------------------- #
# 正确率：整数 half-up（非负，禁止 float / 银行家舍入）
# --------------------------------------------------------------------------- #
def correct_rate(correct_count: int, question_count: int) -> int:
    """``(2*c*100 + q) // (2*q)`` 的整数 half-up；1/8 → 13（不是 12）。"""

    if question_count <= 0:
        raise GradingDataError("question_count_must_be_positive")
    if not 0 <= correct_count <= question_count:
        raise GradingDataError("correct_count_out_of_range")
    return (2 * correct_count * 100 + question_count) // (2 * question_count)


# --------------------------------------------------------------------------- #
# 249 分练习估分
# --------------------------------------------------------------------------- #
def _breakdown(
    facts: Sequence[PracticeFact], *, available: bool, reason: str | None
) -> dict:
    groups = []
    for group in TYPE_GROUPS:
        group_facts = [
            fact for fact in facts if fact.passage_type == group.passage_type
        ]
        groups.append(
            {
                "passage_type": group.passage_type,
                "question_count": len(group_facts),
                "correct_count": sum(1 for fact in group_facts if fact.is_correct),
                "weight": group.weight,
            }
        )
    return {
        "rule": CET_LISTENING_249_V1,
        "total": PRACTICE_SCORE_MAX,
        "groups": groups,
        "available": available,
        "reason": reason,
    }


def _unavailable(facts: Sequence[PracticeFact], reason: str) -> PracticeScoreResult:
    return PracticeScoreResult(
        available=False,
        value=None,
        max=PRACTICE_SCORE_MAX,
        label=PRACTICE_SCORE_LABEL,
        reason=reason,
        score_breakdown=_breakdown(facts, available=False, reason=reason),
    )


def estimate_practice_score(
    facts: Sequence[PracticeFact],
) -> PracticeScoreResult:
    """按题型占比折算 0–249 练习估分；reason 顺序固定（REV-05）。

    不可用原因优先级：``not_standard_25`` → ``question_type_missing`` →
    ``unknown_type`` → ``type_count_mismatch``；不可用时 ``available=false``、
    ``value=None``，但 ``rule``/``reason`` 始终保留在 ``score_breakdown``。
    """

    fact_list = list(facts)

    if len(fact_list) != STANDARD_QUESTION_COUNT:
        return _unavailable(fact_list, REASON_NOT_STANDARD_25)

    if any(not fact.passage_type for fact in fact_list):
        return _unavailable(fact_list, REASON_QUESTION_TYPE_MISSING)

    if any(fact.passage_type not in GROUP_BY_TYPE for fact in fact_list):
        return _unavailable(fact_list, REASON_UNKNOWN_TYPE)

    counts = {group.passage_type: 0 for group in TYPE_GROUPS}
    corrects = {group.passage_type: 0 for group in TYPE_GROUPS}
    for fact in fact_list:
        counts[fact.passage_type] += 1
        if fact.is_correct:
            corrects[fact.passage_type] += 1

    if any(
        counts[group.passage_type] != group.question_count for group in TYPE_GROUPS
    ):
        return _unavailable(fact_list, REASON_TYPE_COUNT_MISMATCH)

    # 数据一致性：每组正确数不超过题量，且总正确数 = 各组正确数之和。
    total_correct = sum(1 for fact in fact_list if fact.is_correct)
    if total_correct != sum(corrects.values()):
        raise GradingDataError("practice_score_inconsistent")
    if any(
        corrects[group.passage_type] > counts[group.passage_type]
        for group in TYPE_GROUPS
    ):
        raise GradingDataError("practice_score_inconsistent")

    raw = Fraction(0)
    for group in TYPE_GROUPS:
        raw += (
            Fraction(corrects[group.passage_type], group.question_count)
            * Fraction(group.weight, TOTAL_WEIGHT)
            * PRACTICE_SCORE_MAX
        )
    # 非负数 half-up：floor(raw + 1/2) = (2*num + den) // (2*den)
    value = (2 * raw.numerator + raw.denominator) // (2 * raw.denominator)

    return PracticeScoreResult(
        available=True,
        value=value,
        max=PRACTICE_SCORE_MAX,
        label=PRACTICE_SCORE_LABEL,
        reason=None,
        score_breakdown=_breakdown(fact_list, available=True, reason=None),
    )


# --------------------------------------------------------------------------- #
# 逐题判分 + 快照 + 汇总（原卷字母空间）
# --------------------------------------------------------------------------- #
def _validate_inputs(
    questions: list[QuestionSnapshotInput], answers: list[AnswerInput]
) -> None:
    if not questions:
        raise GradingDataError("empty_question_set")
    question_nos = [question.question_no for question in questions]
    if len(set(question_nos)) != len(question_nos):
        raise GradingDataError("duplicate_question_no")
    question_ids = [question.question_id for question in questions]
    if len(set(question_ids)) != len(question_ids):
        raise GradingDataError("duplicate_question_id")
    answer_ids = [answer.question_id for answer in answers]
    if len(set(answer_ids)) != len(answer_ids):
        raise GradingDataError("duplicate_answer_question_id")
    question_id_set = set(question_ids)
    if any(answer_id not in question_id_set for answer_id in answer_ids):
        raise GradingDataError("answer_not_in_question_set")


def grade(
    questions: Sequence[QuestionSnapshotInput],
    answers: Sequence[AnswerInput],
) -> GradeResult:
    """按题号遍历整卷判分；未作答计错且快照 ``selected_option=None``。

    判分只比较**原卷字母空间**（``selected == correct_paper_letter``）；
    快照自足（题干/选项文本/原卷答案/解析均直接取自输入）。
    """

    question_list = list(questions)
    answer_list = list(answers)
    _validate_inputs(question_list, answer_list)

    selected_by_id = {
        answer.question_id: answer.selected_option for answer in answer_list
    }

    drafts: list[AttemptAnswerDraft] = []
    correct_count = 0
    for question in sorted(question_list, key=lambda item: item.question_no):
        selected = selected_by_id.get(question.question_id)
        is_correct = selected is not None and selected == question.correct_paper_letter
        if is_correct:
            correct_count += 1
        drafts.append(
            AttemptAnswerDraft(
                question_no=question.question_no,
                question_id=question.question_id,
                passage_type=question.passage_type,
                question_text=question.question_text,
                option_a=question.options[0],
                option_b=question.options[1],
                option_c=question.options[2],
                option_d=question.options[3],
                correct_option=question.correct_paper_letter,
                selected_option=selected,
                is_correct=is_correct,
                explanation_text=question.explanation_text,
            )
        )

    question_count = len(question_list)
    facts = [
        PracticeFact(passage_type=draft.passage_type, is_correct=draft.is_correct)
        for draft in drafts
    ]
    return GradeResult(
        answer_drafts=tuple(drafts),
        question_count=question_count,
        correct_count=correct_count,
        correct_rate=correct_rate(correct_count, question_count),
        practice_score=estimate_practice_score(facts),
    )
