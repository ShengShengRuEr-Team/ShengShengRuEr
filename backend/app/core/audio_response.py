"""受控音频的 HTTP Range 分段响应。

浏览器拖动进度条 / seek 会发 ``Range: bytes=start-`` 请求；若服务器总是
返回 200 全文件，播放器会回退到 0 秒重播。这里按 Range 头返回 206 分段、
越界返回 416，并始终带 ``Accept-Ranges: bytes``。

实现参考公开的 FastAPI Range 处理写法（解析单区间 → 分块流式读取 →
Content-Range / Accept-Ranges），不依赖 starlette 是否原生支持 Range，
便于在权限判断之后统一控制输出。
"""

import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_CHUNK = 1024 * 1024  # 1 MB


def _content_disposition(path: Path) -> str:
    """构造 Content-Disposition。

    音频文件名可能含中文（如 ``CET4_2025_06_1_听力.m4a``）。HTTP 头按
    latin-1 编码发送，直接塞非 ASCII 字符会抛 UnicodeEncodeError 变成 500，
    因此非 ASCII 名称一律按 RFC 5987 用 ``filename*=UTF-8''...`` 传递。
    """
    name = path.name
    try:
        name.encode("ascii")
    except UnicodeEncodeError:
        fallback = f"listening{path.suffix or '.m4a'}"
        return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
    return f'inline; filename="{name}"'


def _parse_range(header: str, total: int) -> tuple[int, int] | None:
    """解析单区间 Range 头为 (start, end) 闭区间；非法/越界返回 None。"""
    match = _RANGE_RE.match(header.strip())
    if not match:
        return None
    start_s, end_s = match.groups()
    if not start_s and not end_s:
        return None
    if not start_s:  # 后缀区间：最后 N 字节
        start = max(0, total - int(end_s))
        end = total - 1
    else:
        start = int(start_s)
        end = min(int(end_s) if end_s else total - 1, total - 1)
    if start > end or start >= total:
        return None
    return start, end


def _stream(path: Path, start: int, end: int) -> Iterator[bytes]:
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = fh.read(min(_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def ranged_file_response(request: Request, path: Path, media_type: str) -> Response:
    """按 Range 头返回 206 分段或 200 全文件；均带 Accept-Ranges。"""
    total = path.stat().st_size
    range_header = request.headers.get("range")
    span = _parse_range(range_header, total) if range_header else None

    if range_header and span is None:
        return Response(
            status_code=416,
            headers={
                "Content-Range": f"bytes */{total}",
                "Accept-Ranges": "bytes",
            },
        )

    if span:
        start, end = span
        return StreamingResponse(
            _stream(path, start, end),
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Length": str(end - start + 1),
                "Accept-Ranges": "bytes",
                "Content-Disposition": _content_disposition(path),
            },
        )

    return StreamingResponse(
        _stream(path, 0, total - 1),
        status_code=200,
        media_type=media_type,
        headers={
            "Content-Length": str(total),
            "Accept-Ranges": "bytes",
            "Content-Disposition": _content_disposition(path),
        },
    )
