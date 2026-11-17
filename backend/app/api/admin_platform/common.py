"""管理端路由公共辅助。

路径参数统一按字符串接收、在认证依赖之后解析：
- 未登录 + 畸形参数 → 401（认证依赖先执行）
- 学生 + 畸形参数 → 403（权限依赖先执行）
- 已授权 + 畸形参数 → 422（业务入口解析）
"""

import ipaddress
import uuid

from fastapi import Request

from app.core.errors import AppError

MAX_USER_AGENT_LENGTH = 256
INVALID_PARAMETER_MESSAGE = "请求参数校验失败"
PAGE_SIZES: tuple[int, ...] = (10, 20, 50, 100)


def validate_page_size(value: int) -> int:
    """分页大小白名单；pydantic 的 int Literal 不接收查询字符串，故手动校验。"""

    if value not in PAGE_SIZES:
        raise invalid_parameter()
    return value


def request_ip(request: Request) -> str | None:
    """原始 TCP 对端地址；不可解析时不写库（代理信任属 T08/T09）。"""

    client = request.client
    if client is None or not client.host:
        return None
    try:
        return str(ipaddress.ip_address(client.host))
    except ValueError:
        return None


def request_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:MAX_USER_AGENT_LENGTH]


def invalid_parameter() -> AppError:
    return AppError(422, INVALID_PARAMETER_MESSAGE)


def parse_positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise invalid_parameter() from None
    if value <= 0:
        raise invalid_parameter()
    return value


def parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (TypeError, ValueError):
        raise invalid_parameter() from None
