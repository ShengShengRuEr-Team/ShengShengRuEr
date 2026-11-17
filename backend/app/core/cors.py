"""全局 CORS 白名单单一来源；调试中间件与 CORSMiddleware 共用。"""

CORS_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def cors_headers_for_origin(origin: str | None) -> list[tuple[bytes, bytes]]:
    """仅对白名单 Origin 返回 CORS 头；不在列表时不放行。"""

    if not origin or origin not in CORS_ALLOWED_ORIGINS:
        return []
    return [
        (
            b"access-control-allow-origin",
            origin.encode("latin-1"),
        ),
        (b"vary", b"Origin"),
        (b"access-control-allow-credentials", b"true"),
    ]
