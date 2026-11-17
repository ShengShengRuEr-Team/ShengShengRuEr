"""服务端请求上下文：request_id、event_id 与 UTC/单调时钟。

- 每个 HTTP 请求生成一个 `request_id`（UUID），即使失败也通过响应头
  `X-Request-ID` 返回；不采用客户端传入值作主键。
- 一个业务事件只分配一个 `event_id`；失败路径复用同一动作标识。
- `monotonic_ms()` 只用于耗时统计，不写入业务时间字段。
"""

import time
import uuid
from contextvars import ContextVar, Token

_request_id: ContextVar[uuid.UUID | None] = ContextVar(
    "admin_request_id", default=None
)


def new_request_id() -> uuid.UUID:
    return uuid.uuid4()


def new_event_id() -> uuid.UUID:
    return uuid.uuid4()


def bind_request_id(request_id: uuid.UUID) -> Token:
    return _request_id.set(request_id)


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


def current_request_id() -> uuid.UUID:
    """取当前请求的 request_id；无上下文时生成一个，保证审计必有值。"""

    value = _request_id.get()
    return value if value is not None else uuid.uuid4()


def monotonic_ms() -> float:
    return time.monotonic() * 1000.0


def elapsed_ms(started_at: float) -> int:
    return max(0, int(round(monotonic_ms() - started_at)))
