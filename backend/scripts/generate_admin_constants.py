"""生成管理端前端常量（主文档 §11.4）。

单一来源：`app.core.admin_permissions`（21 个权限码）与 `app.core.admin_enums`
（枚举值/中文标签）。纯函数输出，不读取 Settings/.env，不访问数据库。

用法：
    python scripts/generate_admin_constants.py           # 写入生成物
    python scripts/generate_admin_constants.py --check   # 只比较，有差异返回非零
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
OUTPUT_PATH = REPO_DIR / "frontend" / "src" / "generated" / "adminConstants.ts"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import admin_enums as enums  # noqa: E402
from app.core import admin_permissions  # noqa: E402
from app.core.admin_permissions import ADMIN_PERMISSIONS  # noqa: E402

HEADER = """// 本文件由 backend/scripts/generate_admin_constants.py 生成，请勿手工修改。
// 修改后端枚举或权限码后运行：python scripts/generate_admin_constants.py
// 只用于前端展示与显隐，不替代服务端鉴权。
"""


def _string_array(name: str, values: tuple[str, ...]) -> str:
    items = ",\n  ".join(f"'{value}'" for value in values)
    return f"export const {name} = [\n  {items},\n] as const\n"


def _upper_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _label_map(name: str, mapping: dict[str, str]) -> str:
    items = ",\n  ".join(
        f"{key}: '{value}'" for key, value in sorted(mapping.items())
    )
    return (
        f"export const {name}: Record<string, string> = {{\n  {items},\n}}\n"
    )


def build_content() -> str:
    blocks: list[str] = [HEADER]

    blocks.append(
        "export const ADMIN_PERMISSIONS = [\n"
        + ",\n".join(f"  '{code}'" for code in ADMIN_PERMISSIONS)
        + ",\n] as const\n"
    )

    permission_constants = sorted(
        name
        for name in dir(admin_permissions)
        if name.startswith("PERM_")
        and isinstance(getattr(admin_permissions, name), str)
    )
    for name in permission_constants:
        value = getattr(admin_permissions, name)
        blocks.append(f"export const {name} = '{value}'\n")

    blocks.append(
        _string_array("EVENT_TYPES", tuple(sorted(enums.EVENT_TYPES)))
    )
    blocks.append(
        _string_array("LOG_RESULTS", enums.LOG_RESULTS)
    )
    blocks.append(
        _string_array("LOGIN_FAILURE_TYPES", enums.LOGIN_FAILURE_TYPES)
    )
    blocks.append(
        _string_array("ACCOUNT_STATUSES", enums.ACCOUNT_STATUSES)
    )
    blocks.append(_string_array("ROLE_KEYS", enums.ROLE_KEYS))
    blocks.append(_string_array("REVOKE_REASONS", enums.REVOKE_REASONS))
    blocks.append(_string_array("TARGET_TYPES", enums.TARGET_TYPES))
    blocks.append(_string_array("MONITOR_STATES", enums.MONITOR_STATES))
    blocks.append(_string_array("SEVERITIES", enums.SEVERITIES))
    blocks.append(_string_array("RUN_STATES", enums.RUN_STATES))
    blocks.append(
        _string_array("SEGMENT_TYPES", enums.MODULE2_SEGMENT_TYPES)
    )
    blocks.append(
        _string_array("VISIBILITY_ACTIONS", enums.MODULE2_VISIBILITY_ACTIONS)
    )
    blocks.append(
        _string_array("EXAM_LEVELS", enums.MODULE2_EXAM_LEVELS)
    )

    for name, mapping in enums.LABEL_REGISTRY.items():
        blocks.append(_label_map(_upper_snake(name), mapping))

    return "\n".join(blocks)


def check_file(path: Path = OUTPUT_PATH) -> list[str]:
    """返回差异说明；空列表表示生成物最新。"""

    expected = build_content()
    if not path.exists():
        return [f"生成物不存在：{path}"]
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        return [
            "生成物与后端枚举不一致，请运行 python scripts/generate_admin_constants.py"
        ]
    return []


def write_file(path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_content(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成管理端前端常量")
    parser.add_argument("--check", action="store_true", help="只检查不写文件")
    args = parser.parse_args(argv)

    if args.check:
        problems = check_file()
        if problems:
            for problem in problems:
                print(problem)
            return 1
        print("管理端常量与后端枚举一致。")
        return 0

    write_file()
    print(f"已写入 {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
