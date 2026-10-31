"""接口请求与响应模型。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse[T](BaseModel):
    code: int = 200
    msg: str = "获取成功"
    data: T | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class LoginData(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int


class UserInfo(BaseModel):
    user_id: int
    username: str
    nickname: str


class GetInfoData(BaseModel):
    user: UserInfo
    roles: list[str]
    permissions: list[str]
    is_admin: bool


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    exam_level: str
    exam_year: int
    exam_month: int
    set_no: int


class PaperListData(BaseModel):
    items: list[PaperOut]
    total: int


class StudentQuestion(BaseModel):
    """学生可见字段白名单；敏感字段不得加入本模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    question_no: int
    prompt_text: str | None
    option_a: str | None
    option_b: str | None
    option_c: str | None
    option_d: str | None


class AdminQuestion(StudentQuestion):
    """管理端字段，显式增加答案、解析与听力原文。"""

    correct_option: str | None
    explanation_text: str | None
    transcript_text: str | None


class StudentQuestionListData(BaseModel):
    items: list[StudentQuestion]
    total: int


class AdminQuestionListData(BaseModel):
    items: list[AdminQuestion]
    total: int


class TaskCreateRequest(BaseModel):
    paper_id: int = Field(gt=0)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: int | None
    task_type: str
    status: str
    progress: int
    message: str | None
    result: dict[str, Any] | None
    created_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: int | None
    task_type: str
    status: str
    progress: int
    message: str | None
    created_at: datetime


class TaskListData(BaseModel):
    items: list[TaskListItem]
    total: int
