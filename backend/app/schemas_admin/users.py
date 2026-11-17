"""管理端用户/本人模型（主文档 §4.3）。"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas_admin.common import PageData, to_display_time

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,50}$")
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 64
PASSWORD_MAX_BYTES = 72


def validate_username(value: str) -> str:
    candidate = value.strip()
    if not USERNAME_PATTERN.fullmatch(candidate):
        raise ValueError("用户名需为 3—50 位字母、数字或下划线")
    return candidate


def validate_password_policy(value: str) -> str:
    """密码格式规则（格式问题一律 422）。"""

    if len(value) < PASSWORD_MIN_LENGTH or len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"密码长度需为 {PASSWORD_MIN_LENGTH}—{PASSWORD_MAX_LENGTH} 个字符")
    if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError("密码 UTF-8 编码不得超过 72 字节")
    if not any(char.isascii() and char.isalpha() for char in value):
        raise ValueError("密码必须包含至少一个 ASCII 字母")
    if not any(char.isdigit() for char in value):
        raise ValueError("密码必须包含至少一个数字")
    return value


def validate_reason(value: str) -> str:
    candidate = value.strip()
    if not 1 <= len(candidate) <= 200:
        raise ValueError("reason 需为 1—200 个字符")
    return candidate


def validate_nickname(value: str) -> str:
    candidate = value.strip()
    if len(candidate) > 50:
        raise ValueError("昵称不得超过 50 个字符")
    return candidate


class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    role: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_time(self, value: datetime) -> str:
        return to_display_time(value)


class UserPage(PageData[UserOut]):
    """用户列表：标准分页外壳。"""


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    nickname: str = ""
    role: Literal["admin", "student"] = "student"

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password_policy(value)

    @field_validator("nickname")
    @classmethod
    def _nickname(cls, value: str) -> str:
        return validate_nickname(value)


class UserProfileUpdateRequest(BaseModel):
    """PATCH /admin/users/{id} 与 PATCH /admin/me 共用：只接收 nickname。"""

    model_config = ConfigDict(extra="forbid")

    nickname: str

    @field_validator("nickname")
    @classmethod
    def _nickname(cls, value: str) -> str:
        return validate_nickname(value)


class UserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "disabled"]
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return validate_reason(value)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str
    reason: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password_policy(value)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return validate_reason(value)


class SelfPasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: str = Field(min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password_policy(value)


class UserStatusResult(BaseModel):
    id: int
    status: str
    changed: bool
    revoked_session_count: int


class PasswordResetResult(BaseModel):
    id: int
    changed: bool
    revoked_session_count: int


class SelfPasswordResult(BaseModel):
    changed: bool
    reauth_required: bool
