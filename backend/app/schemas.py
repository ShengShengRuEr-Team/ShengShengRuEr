"""接口请求与响应模型。"""

from pydantic import BaseModel, Field


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
    is_admin: bool


class AdminOverviewData(BaseModel):
    """管理端首页占位数据，用于验证角色鉴权。"""

    role: str
    message: str
