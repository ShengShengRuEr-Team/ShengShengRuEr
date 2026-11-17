"""私有接口文档的调试白名单匹配（主文档 §8.2）。

规则：
- 只接受 `GET`；
- 路径只做一次百分号解码；解码后仍含 `%`、出现双斜杠、尾斜杠或编码斜杠
  一律判为歧义，直接拒绝（不命中白名单 → 400）；
- 模板中的 `{param}` 匹配单个路径段（`[^/]+`），由目标路由再做类型校验。
"""

import re
import urllib.parse

from app.core.admin_permissions import DOC_DEBUG_ALLOWLIST

DEBUG_HEADER = "x-admin-docs-debug"
DEBUG_HEADER_VALUE = "1"

_PARAM_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def _template_regex(template: str) -> re.Pattern[str]:
    parts: list[str] = []
    cursor = 0
    for match in _PARAM_PATTERN.finditer(template):
        parts.append(re.escape(template[cursor : match.start()]))
        parts.append(r"[^/]+")
        cursor = match.end()
    parts.append(re.escape(template[cursor:]))
    return re.compile("^" + "".join(parts) + "$")


_COMPILED: tuple[tuple[str, str, re.Pattern[str], str], ...] = tuple(
    (method, template, _template_regex(template), permission)
    for method, template, permission in DOC_DEBUG_ALLOWLIST
)


def normalize_debug_path(raw_path: str) -> str | None:
    """返回可匹配的路径；歧义/编码绕过返回 None。"""

    if not raw_path.startswith("/"):
        return None
    decoded = urllib.parse.unquote(raw_path)
    # 一次解码后仍有百分号 -> 双重编码；反斜杠/编码斜杠视为绕过。
    if "%" in decoded or "\\" in decoded or "%2f" in raw_path.lower():
        return None
    if "//" in decoded or (len(decoded) > 1 and decoded.endswith("/")):
        return None
    return decoded


def resolve_debug_route(
    method: str, raw_path: str
) -> tuple[str, str] | None:
    """命中时返回 (path_template, permission)，否则 None。"""

    if method.upper() != "GET":
        return None
    path = normalize_debug_path(raw_path)
    if path is None:
        return None
    for route_method, template, pattern, permission in _COMPILED:
        if route_method != "GET":
            continue
        if pattern.match(path):
            return template, permission
    return None


def allowlist_document() -> list[dict[str, str]]:
    return [
        {"method": method, "path_template": template, "permission": permission}
        for method, template, permission in DOC_DEBUG_ALLOWLIST
    ]
