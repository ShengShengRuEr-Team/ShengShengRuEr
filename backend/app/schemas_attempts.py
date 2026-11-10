"""作答系统（API-1）接口契约：请求/响应模型、幂等键校验与统一 msg 常量。

范围（开发文档 2.4、2.7.1；任务卡 T02）：

- 只定义模型级契约，不实现路由、Header 解析、HTTP 状态码与 OpenAPI path（T06）；
- 不实现判分/练习估分（T05）、幂等仓储与准入（T03/T04）、服务编排（T06）；
- 业务规则（整卷集合完整、版本一致、重复题号、限次、跨表互斥）由服务层判定，
  本模块只做字段类型、取值范围与字母空间的严格校验；
- 额外字段按 Pydantic 默认忽略；响应只含汇总，不含逐题正误/答案/解析/正文/内部 ID。
"""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas import ApiResponse

# JSON 请求体中的 ID：strict，拒绝字符串、浮点、布尔被静默转 int，
# 且必须 > 0 且不超过 BIGINT 上限（开发文档 2.4.2，R7-01）。
JsonId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]

# 本套原卷展示字母；契约只接受大写 A–D，小写由 schema 层拒绝（422）。
OptionLetter = Literal["A", "B", "C", "D"]

# 练习估分固定口径（BR-16a）：满分 249，标签固定，不可用时 value 为 null。
PRACTICE_SCORE_MAX = 249
PRACTICE_SCORE_LABEL = "练习估分，非官方成绩"

# 估分不可用的机器可读原因（开发文档 2.4.2）。
PracticeUnavailableReason = Literal[
    "not_standard_25",
    "question_type_missing",
    "type_count_mismatch",
    "unknown_type",
]

# --------------------------------------------------------------------------- #
# 统一 msg 常量（开发文档 2.7.1，E03–E09、E12）；HTTP 状态码由 T06 决定。
# --------------------------------------------------------------------------- #
MSG_E03_PAPER_NOT_ACCESSIBLE = "资源不存在"
MSG_E04_CONTENT_VERSION_MISMATCH = "内容已更新，请重新作答"
MSG_E05_INVALID_IDEMPOTENCY_KEY = "缺少或非法的提交键 Idempotency-Key"
MSG_E06_REQUEST_VALIDATION = "请求参数校验失败"
MSG_E07_PREFIX = "提交内容不合法："
MSG_E08_ATTEMPT_LIMIT = "本轮同一试卷仅允许提交一次"
MSG_E09_KEY_REUSED = "提交键已用于其他提交，请使用新键"
MSG_E12_SUCCESS = "提交成功"

# Idempotency-Key：UUIDv4 规范字符串（36 字符、8-4-4-4-12 十六进制）。
# 版本位固定为 4，变体位 8/9/a/b；十六进制大小写均接受。
_UUID4_KEY_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}"
    r"-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def msg_e07(reason: str) -> str:
    """E07 统一前缀 + 安全业务原因（不得含答案/解析/正文等内部信息）。"""

    return f"{MSG_E07_PREFIX}{reason}"


def validate_idempotency_key(value: str | None) -> bool:
    """判断请求头 Idempotency-Key 是否为 UUIDv4 规范字符串。

    仅接受 36 字符 `8-4-4-4-12` 结构、版本位 4、变体位 8/9/a/b；
    缺失（None）、非字符串、超长/过短、带花括号或 URN 前缀一律返回 False。
    供 T06 路由在请求可解析后调用；本卡不解析 Header。
    """

    if not isinstance(value, str) or len(value) != 36:
        return False
    return _UUID4_KEY_PATTERN.fullmatch(value) is not None


# --------------------------------------------------------------------------- #
# 请求模型（API-1 请求体）
# --------------------------------------------------------------------------- #
class AttemptAnswerIn(BaseModel):
    """单题作答：question_id 为题库题目身份，selected_option 为本套原卷字母。"""

    question_id: JsonId
    selected_option: OptionLetter


class AttemptSubmitIn(BaseModel):
    """提交整卷作答的请求体；两个字段都必须存在。"""

    # 页面加载时整卷全部题目身份；字段必须存在，不得为空由服务层判 400 E07。
    loaded_question_ids: list[JsonId]
    # 字段必须存在，可为空数组（全部未作答）；缺失属 422，不按空卷处理。
    answers: list[AttemptAnswerIn]


# --------------------------------------------------------------------------- #
# 响应模型（成功 200）；复用既有 {code,msg,data} 外壳，不改既有 ApiResponse。
# --------------------------------------------------------------------------- #
class PracticeScoreData(BaseModel):
    """练习估分快照：不可用时 available=false 且 value=null，不输出 0 分。"""

    available: bool
    value: int | None = Field(default=None, ge=0, le=PRACTICE_SCORE_MAX)
    max: int = PRACTICE_SCORE_MAX
    label: str = PRACTICE_SCORE_LABEL
    reason: PracticeUnavailableReason | None = None


class AttemptSubmitData(BaseModel):
    """作答提交成功后的汇总数据（不含逐题正误、答案、解析与内部主键）。"""

    attempt_code: str
    exam_paper_id: int
    submitted_at: datetime
    question_count: int
    correct_count: int
    correct_rate: int
    practice_score: PracticeScoreData


class AttemptSubmitResponse(ApiResponse[AttemptSubmitData]):
    """固定 data 为 AttemptSubmitData 的成功响应外壳。"""

    msg: str = MSG_E12_SUCCESS
