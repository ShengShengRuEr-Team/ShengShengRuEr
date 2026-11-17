"""管理端常量生成物一致性（AC-29）。"""

from pathlib import Path

import pytest

from scripts import generate_admin_constants as generator

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_generated_file_is_up_to_date() -> None:
    problems = generator.check_file()
    assert problems == [], problems


def test_check_detects_missing_or_stale_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ts"
    assert generator.check_file(missing) != []

    stale = tmp_path / "stale.ts"
    stale.write_text("// stale\n", encoding="utf-8")
    assert generator.check_file(stale) != []

    fresh = tmp_path / "fresh.ts"
    generator.write_file(fresh)
    assert generator.check_file(fresh) == []


def test_check_detects_changed_enum(monkeypatch, tmp_path: Path) -> None:
    """后端改值但未重新生成时，检查必须失败。"""

    from app.core import admin_enums

    original = dict(admin_enums.EVENT_TYPE_LABELS)
    monkeypatch.setitem(admin_enums.EVENT_TYPE_LABELS, "NEW_EVENT", "新事件")
    try:
        generator.write_file(tmp_path / "gen.ts")
        monkeypatch.setitem(admin_enums.EVENT_TYPE_LABELS, "NEW_EVENT", "改过的标签")
        problems = generator.check_file(tmp_path / "gen.ts")
        assert problems, "标签变化必须被 check 捕获"
    finally:
        admin_enums.EVENT_TYPE_LABELS.clear()
        admin_enums.EVENT_TYPE_LABELS.update(original)


def test_main_check_exit_code() -> None:
    assert generator.main(["--check"]) == 0


def test_permissions_match_backend() -> None:
    from app.core.admin_permissions import ADMIN_PERMISSIONS

    content = generator.build_content()
    for code in ADMIN_PERMISSIONS:
        assert f"'{code}'" in content
    assert len(ADMIN_PERMISSIONS) == 21
