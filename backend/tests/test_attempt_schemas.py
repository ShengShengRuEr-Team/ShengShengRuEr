"""T02 模型级契约：请求/响应模型、幂等键校验与统一 msg 常量。

只做模型级断言：直接构造/解析 Pydantic 模型，不涉及 HTTP、路由、服务与
数据库（T02 边界）。app.* 在夹具内延迟导入，沿用仓库测试约定。
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


@pytest.fixture(scope="module")
def schemas():
    import app.schemas_attempts as module

    return module


def _valid_payload() -> dict:
    return {
        "loaded_question_ids": [101, 102, 103],
        "answers": [
            {"question_id": 101, "selected_option": "B"},
            {"question_id": 103, "selected_option": "A"},
        ],
    }


# --------------------------------------------------------------------------- #
# T02-A1：合法请求解析成功，字段与契约一致
# --------------------------------------------------------------------------- #
def test_a1_valid_request_parses(schemas):
    model = schemas.AttemptSubmitIn.model_validate(_valid_payload())

    assert model.loaded_question_ids == [101, 102, 103]
    assert len(model.answers) == 2
    assert model.answers[0].question_id == 101
    assert model.answers[0].selected_option == "B"
    assert model.answers[1].question_id == 103
    assert model.answers[1].selected_option == "A"


def test_a1_extra_fields_are_ignored(schemas):
    payload = _valid_payload()
    payload["replay"] = True
    payload["student_id"] = 999

    model = schemas.AttemptSubmitIn.model_validate(payload)

    assert set(model.model_dump()) == {"loaded_question_ids", "answers"}


def test_a1_question_id_bigint_upper_bound_is_accepted(schemas):
    model = schemas.AttemptSubmitIn.model_validate(
        {
            "loaded_question_ids": [2**63 - 1],
            "answers": [{"question_id": 2**63 - 1, "selected_option": "D"}],
        }
    )
    assert model.loaded_question_ids == [2**63 - 1]


def test_a1_option_letters_are_original_paper_letters(schemas):
    for letter in ("A", "B", "C", "D"):
        payload = {
            "loaded_question_ids": [1],
            "answers": [{"question_id": 1, "selected_option": letter}],
        }
        assert schemas.AttemptSubmitIn.model_validate(payload).answers[0].selected_option == letter


# --------------------------------------------------------------------------- #
# T02-A2：字段必须存在；answers 显式空数组合法
# --------------------------------------------------------------------------- #
def test_a2_missing_answers_is_validation_error(schemas):
    with pytest.raises(ValidationError):
        schemas.AttemptSubmitIn.model_validate({"loaded_question_ids": [101]})


def test_a2_missing_loaded_question_ids_is_validation_error(schemas):
    with pytest.raises(ValidationError):
        schemas.AttemptSubmitIn.model_validate({"answers": []})


def test_a2_empty_answers_is_allowed(schemas):
    model = schemas.AttemptSubmitIn.model_validate(
        {"loaded_question_ids": [101, 102], "answers": []}
    )
    assert model.answers == []


# --------------------------------------------------------------------------- #
# T02-A3：question_id strict / 字母域
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_id",
    ["1", 1.0, True, False, 0, -1, 2**63, 2**64, None, [1]],
)
def test_a3_invalid_question_id_rejected(schemas, bad_id):
    with pytest.raises(ValidationError):
        schemas.AttemptAnswerIn.model_validate(
            {"question_id": bad_id, "selected_option": "A"}
        )


@pytest.mark.parametrize("bad_letter", ["E", "a", "AB", "", "1", 1, None])
def test_a3_invalid_selected_option_rejected(schemas, bad_letter):
    with pytest.raises(ValidationError):
        schemas.AttemptAnswerIn.model_validate(
            {"question_id": 101, "selected_option": bad_letter}
        )


def test_a3_answers_element_missing_field_rejected(schemas):
    with pytest.raises(ValidationError):
        schemas.AttemptSubmitIn.model_validate(
            {"loaded_question_ids": [101], "answers": [{"selected_option": "A"}]}
        )
    with pytest.raises(ValidationError):
        schemas.AttemptSubmitIn.model_validate(
            {"loaded_question_ids": [101], "answers": [{"question_id": 101}]}
        )


# --------------------------------------------------------------------------- #
# T02-A4：loaded_question_ids 空数组可过模型；元素 strict
# --------------------------------------------------------------------------- #
def test_a4_empty_loaded_question_ids_passes_model(schemas):
    # 判空属服务层（T06-A12 验 400 E07），模型层不拦截。
    model = schemas.AttemptSubmitIn.model_validate(
        {"loaded_question_ids": [], "answers": []}
    )
    assert model.loaded_question_ids == []


@pytest.mark.parametrize(
    "bad_id",
    ["1", 1.0, True, False, 0, -1, 2**63, None],
)
def test_a4_invalid_loaded_question_id_element_rejected(schemas, bad_id):
    with pytest.raises(ValidationError):
        schemas.AttemptSubmitIn.model_validate(
            {"loaded_question_ids": [bad_id], "answers": []}
        )


def test_a4_loaded_question_ids_must_be_list(schemas):
    for bad in (101, "101", None, {"101": 1}):
        with pytest.raises(ValidationError):
            schemas.AttemptSubmitIn.model_validate(
                {"loaded_question_ids": bad, "answers": []}
            )


# --------------------------------------------------------------------------- #
# T02-A5：Idempotency-Key 必须是 UUIDv4 规范字符串
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        str(uuid.uuid4()),
        "0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40",
        "0F5C2A1E-9D4B-4F6A-9C77-2B1E8A3D5C40",
        "00000000-0000-4000-8000-000000000000",
        "00000000-0000-4000-b000-000000000000",
    ],
)
def test_a5_valid_uuid4_keys(schemas, value):
    assert schemas.validate_idempotency_key(value) is True


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c4",  # 35 字符
        "0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c400",  # 37 字符
        "{0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40}",
        "urn:uuid:0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40",
        "0f5c2a1e9d4b4f6a9c772b1e8a3d5c40",  # 无连字符
        "0f5c2a1e-9d4b-1f6a-9c77-2b1e8a3d5c40",  # 版本位不是 4
        "0f5c2a1e-9d4b-4f6a-0c77-2b1e8a3d5c40",  # 变体位 0 非法
        "0f5c2a1e-9d4b-4f6a-7c77-2b1e8a3d5c40",  # 变体位 7 非法
        "0f5c2a1e-9d4b-4f6a-cc77-2b1e8a3d5c40",  # 变体位 c 非法
        "zzzzzzzz-zzzz-4zzz-8zzz-zzzzzzzzzzzz",  # 非十六进制
        123,
        b"0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40",
    ],
)
def test_a5_invalid_keys_are_rejected(schemas, value):
    assert schemas.validate_idempotency_key(value) is False


# --------------------------------------------------------------------------- #
# T02-A6：响应模型只含汇总字段，不含逐题/答案/解析/正文/内部 ID
# --------------------------------------------------------------------------- #
FORBIDDEN_RESPONSE_KEYS = {
    "id",
    "attempt_id",
    "student_id",
    "attempt_key",
    "request_fingerprint",
    "answers",
    "questions",
    "question_id",
    "question_no",
    "selected_option",
    "correct_option",
    "is_correct",
    "correct_count_detail",
    "explanation",
    "explanation_text",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "passage",
    "transcript",
    "batch_id",
    "status",
}


def test_a6_response_envelope_field_set(schemas):
    assert set(schemas.AttemptSubmitResponse.model_fields) == {"code", "msg", "data"}
    assert schemas.AttemptSubmitResponse.model_fields["msg"].default == "提交成功"


def test_a6_data_field_set(schemas):
    assert set(schemas.AttemptSubmitData.model_fields) == {
        "attempt_code",
        "exam_paper_id",
        "submitted_at",
        "question_count",
        "correct_count",
        "correct_rate",
        "practice_score",
    }
    assert set(schemas.PracticeScoreData.model_fields) == {
        "available",
        "value",
        "max",
        "label",
        "reason",
    }


def test_a6_response_contains_no_protected_fields(schemas):
    model = schemas.AttemptSubmitResponse(
        data={
            "attempt_code": "0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40",
            "exam_paper_id": 1,
            "submitted_at": datetime(2026, 11, 8, 6, 30, tzinfo=UTC),
            "question_count": 25,
            "correct_count": 24,
            "correct_rate": 96,
            "practice_score": {
                "available": True,
                "value": 235,
                "max": 249,
                "label": "练习估分，非官方成绩",
                "reason": None,
            },
        }
    )
    dumped = model.model_dump(mode="json")

    assert set(dumped) == {"code", "msg", "data"}
    assert set(dumped["data"]) == {
        "attempt_code",
        "exam_paper_id",
        "submitted_at",
        "question_count",
        "correct_count",
        "correct_rate",
        "practice_score",
    }
    assert dumped["msg"] == "提交成功"
    assert dumped["data"]["submitted_at"] == "2026-11-08T06:30:00Z"
    assert FORBIDDEN_RESPONSE_KEYS.isdisjoint(dumped["data"])
    assert FORBIDDEN_RESPONSE_KEYS.isdisjoint(dumped["data"]["practice_score"])


def test_a6_practice_score_unavailable_has_no_value(schemas):
    score = schemas.PracticeScoreData(
        available=False,
        value=None,
        reason="not_standard_25",
    )
    assert score.value is None
    assert score.max == 249
    assert score.label == "练习估分，非官方成绩"


def test_a6_practice_score_value_range(schemas):
    with pytest.raises(ValidationError):
        schemas.PracticeScoreData(available=True, value=250)
    with pytest.raises(ValidationError):
        schemas.PracticeScoreData(available=True, value=-1)


# --------------------------------------------------------------------------- #
# 统一 msg 常量（开发文档 2.7.1）
# --------------------------------------------------------------------------- #
def test_msg_constants_match_contract(schemas):
    assert schemas.MSG_E03_PAPER_NOT_ACCESSIBLE == "资源不存在"
    assert schemas.MSG_E04_CONTENT_VERSION_MISMATCH == "内容已更新，请重新作答"
    assert (
        schemas.MSG_E05_INVALID_IDEMPOTENCY_KEY
        == "缺少或非法的提交键 Idempotency-Key"
    )
    assert schemas.MSG_E06_REQUEST_VALIDATION == "请求参数校验失败"
    assert schemas.MSG_E08_ATTEMPT_LIMIT == "本轮同一试卷仅允许提交一次"
    assert schemas.MSG_E09_KEY_REUSED == "提交键已用于其他提交，请使用新键"
    assert schemas.MSG_E12_SUCCESS == "提交成功"
    assert schemas.msg_e07("题目不属于本卷") == "提交内容不合法：题目不属于本卷"
