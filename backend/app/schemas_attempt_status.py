"""API-3 提交状态响应模型。

`latest_attempt` 复用 API-1 的 `AttemptSubmitData`，字段与 API-1 完全一致；
该模型自带 `exam_paper_id`，嵌套后与外壳同名，值必须一致。

`check_status_invariants` 保证后端不会输出自相矛盾的状态（N02）：
- submitted === (attempt_count > 0)；
- submitted=false 时 latest 必须为 null；
- submitted=true 允许 latest=null（确定已提交、仅汇总不可用），但 count 必须 >= 1；
- 嵌套 exam_paper_id 必须与外壳一致。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas import ApiResponse
from app.schemas_attempts import AttemptSubmitData

# API-3 成功文案；错误文案复用 API-1 常量，避免两套口径。
MSG_STATUS_SUCCESS = "查询成功"


class AttemptStatusData(BaseModel):
    exam_paper_id: int
    submitted: bool
    attempt_count: int = Field(ge=0)
    latest_attempt: AttemptSubmitData | None = None

    @model_validator(mode="after")
    def check_status_invariants(self) -> AttemptStatusData:
        if self.submitted != (self.attempt_count > 0):
            raise ValueError("submitted/attempt_count conflict")
        if not self.submitted and self.latest_attempt is not None:
            raise ValueError("submitted=false requires latest_attempt=null")
        if self.submitted and self.attempt_count < 1:
            raise ValueError("submitted=true requires attempt_count>=1")
        if (
            self.latest_attempt is not None
            and self.latest_attempt.exam_paper_id != self.exam_paper_id
        ):
            raise ValueError("nested exam_paper_id mismatch")
        return self


class AttemptStatusResponse(ApiResponse[AttemptStatusData]):
    msg: str = MSG_STATUS_SUCCESS
