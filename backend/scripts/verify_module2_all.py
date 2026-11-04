"""模块二一键自检：给验收人用的可复现检查脚本。

在 backend 目录执行：

    .venv/Scripts/python.exe -m scripts.verify_module2_all            # 自带起服务
    .venv/Scripts/python.exe -m scripts.verify_module2_all --base-url http://127.0.0.1:8000

它会依次做：
1. 环境检查（Python 版本、数据库连通、迁移版本）
2. 数据检查（当前批次的题量、片段数、音频绑定、三条状态）
3. 跑 pytest（模块一回归 + 模块二用例，只动测试库）
4. 起一个临时服务（或用 --base-url 指定的服务），跑两个验收脚本

每项打印 PASS/FAIL，最后给出汇总与退出码（0 表示全通过）。
脚本不会修改开发库数据，也不会删除任何表。
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))


def _run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(BACKEND_DIR), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )


def check_environment() -> None:
    version = sys.version_info
    record(version >= (3, 14), "Python 版本 ≥ 3.14", f"{version.major}.{version.minor}.{version.micro}")

    try:
        from sqlalchemy import text

        from app.db.base import engine
        with engine.connect() as conn:
            server = conn.execute(text("select version()")).scalar()
        record(True, "数据库连通", str(server)[:40])
    except Exception as exc:  # noqa: BLE001
        record(False, "数据库连通", f"{type(exc).__name__}: {str(exc)[:120]}")
        return

    try:
        with engine.connect() as conn:
            revision = conn.execute(text("select version_num from alembic_version")).scalar()
        record(revision == "0003_exam_paper_expected_count", "迁移版本 = 0003", str(revision))
    except Exception as exc:  # noqa: BLE001
        record(False, "迁移版本 = 0003", f"{type(exc).__name__}: {str(exc)[:120]}")


def check_data() -> None:
    try:
        from sqlalchemy import func, select

        from app.core.config import get_settings
        from app.db.base import SessionLocal
        from app.db.models_listening import (
            AudioFile,
            ExamPaper,
            ImportBatch,
            Passage,
            Presentation,
            Question,
            TranscriptSegment,
        )
        with SessionLocal() as db:
            paper = db.scalar(select(ExamPaper).order_by(ExamPaper.id))
            record(paper is not None, "试卷存在", paper.exam_paper_code if paper else "无")
            if paper is None:
                return
            batch = db.scalar(
                select(ImportBatch).where(
                    ImportBatch.exam_paper_id == paper.id, ImportBatch.is_current.is_(True)
                )
            )
            record(batch is not None, "存在当前批次", batch.batch_code if batch else "无")
            if batch is None:
                return

            def count_of(model) -> int:
                return db.scalar(
                    select(func.count()).select_from(model).where(model.batch_id == batch.id)
                ) or 0

            counts = {
                "篇章": count_of(Passage),
                "片段": count_of(TranscriptSegment),
                "题目": count_of(Question),
                "映射": count_of(Presentation),
            }
            record(
                counts["篇章"] == 8 and counts["片段"] == 165
                and counts["题目"] == 25 and counts["映射"] == 25,
                "题量与片段数（8/165/25/25）",
                " / ".join(f"{k}={v}" for k, v in counts.items()),
            )

            audio = db.get(AudioFile, paper.playback_audio_id) if paper.playback_audio_id else None
            record(audio is not None, "试卷已绑定音频", audio.storage_key if audio else "未绑定")
            if audio:
                path = get_settings().audio_storage_path / audio.storage_key
                record(path.is_file(), "音频文件落盘", str(path))
                record(
                    audio.mime_type == "audio/mp4",
                    "音频 mime_type",
                    f"{audio.mime_type} / duration={audio.duration_ms}ms",
                )

            record(batch.is_current, "当前批次标记", str(batch.is_current))
            record(
                all(q.content_state == "可用" for q in db.scalars(
                    select(Question).where(Question.batch_id == batch.id)
                )),
                "25 题内容完整度均为「可用」",
            )
            record(
                all(q.review_status == "待审核" for q in db.scalars(
                    select(Question).where(Question.batch_id == batch.id)
                )),
                "25 题审核状态为「待审核」（未冒认为已审核）",
            )
    except Exception as exc:  # noqa: BLE001
        record(False, "数据检查", f"{type(exc).__name__}: {str(exc)[:150]}")


def check_state_records() -> None:
    """内容检查与可见性记录要等"确认可见"之后才有，所以放在验收跑完之后查。"""
    try:
        from sqlalchemy import select

        from app.db.base import SessionLocal
        from app.db.models_listening import (
            ContentCheck,
            ExamPaper,
            ImportBatch,
            PaperVisibility,
        )
        with SessionLocal() as db:
            paper = db.scalar(select(ExamPaper).order_by(ExamPaper.id))
            if paper is None:
                record(False, "存在内容检查记录", "没有试卷")
                return
            batch = db.scalar(
                select(ImportBatch).where(
                    ImportBatch.exam_paper_id == paper.id, ImportBatch.is_current.is_(True)
                )
            )
            if batch is None:
                record(False, "存在内容检查记录", "没有当前批次")
                return
            check = db.scalar(
                select(ContentCheck).where(ContentCheck.batch_id == batch.id)
                .order_by(ContentCheck.id.desc())
            )
            visibility = db.scalar(
                select(PaperVisibility).where(PaperVisibility.batch_id == batch.id)
                .order_by(PaperVisibility.id.desc())
            )
            record(
                check is not None, "存在内容检查记录（验收后应已写入）",
                f"is_passed={check.is_passed if check else '无'}",
            )
            record(
                visibility is not None, "存在可见性记录（验收后应已写入）",
                f"is_visible={visibility.is_visible if visibility else '无'}",
            )
    except Exception as exc:  # noqa: BLE001
        record(False, "状态记录检查", f"{type(exc).__name__}: {str(exc)[:150]}")


def run_pytest() -> None:
    # 不加 -q：pytest.ini 的 addopts 已有 -q，再加一次会变成 -qq 而吞掉汇总行。
    proc = _run([sys.executable, "-m", "pytest", "-p", "no:warnings", "-p", "no:cacheprovider"])
    tail = (proc.stdout or "").strip().splitlines()
    summary = next((line for line in reversed(tail) if "passed" in line or "failed" in line), "")
    record(proc.returncode == 0, "pytest 全部通过", summary[:80])


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_http(url: str, timeout: float = 30.0) -> bool:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=3.0, trust_env=False) as client:
                if client.get(url).status_code < 500:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def run_acceptance(base_url: str | None) -> None:
    env = dict(os.environ)
    # 本机环境可能注入 HTTP_PROXY，会让本机请求出现假失败。
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"

    server = None
    if base_url is None:
        port = 8010
        if not _port_free(port):
            record(False, "临时服务端口可用", f"127.0.0.1:{port} 已被占用，请用 --base-url 指定现有服务")
            return
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(port), "--log-level", "warning"],
            cwd=str(BACKEND_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base_url = f"http://127.0.0.1:{port}"
        if not _wait_http(f"{base_url}/docs"):
            record(False, "临时服务启动", f"{base_url}/docs 未就绪")
            server.terminate()
            return
        record(True, "临时服务启动", base_url)

    try:
        m1 = _run([sys.executable, "-m", "scripts.acceptance", "--base-url", base_url], env=env)
        m1_summary = next(
            (line for line in (m1.stdout or "").splitlines() if "验收汇总" in line), ""
        )
        record(m1.returncode == 0, "模块一验收（B15 无回归）", m1_summary or (m1.stderr or "")[:100])

        m2 = _run([sys.executable, "-m", "scripts.acceptance_module2", "--base-url", base_url], env=env)
        m2_summary = next(
            (line for line in (m2.stdout or "").splitlines() if "验收汇总" in line), ""
        )
        failed = [line.strip() for line in (m2.stdout or "").splitlines() if line.startswith("[FAIL]")]
        record(m2.returncode == 0, "模块二验收 16 项", m2_summary or (m2.stderr or "")[:100])
        for line in failed:
            record(False, "  失败项", line[:100])
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="模块二一键自检（验收用）")
    parser.add_argument("--base-url", default=None, help="复用已启动的服务；不填则临时起 8010 端口")
    args = parser.parse_args()

    print("=" * 68)
    print("模块二后端自检")
    print("=" * 68)
    check_environment()
    check_data()
    run_pytest()
    run_acceptance(args.base_url)
    # 验收里的"确认可见"会写入检查与可见性记录，所以这两项放在最后查。
    check_state_records()

    print()
    width = max(len(name) for _, name, _ in RESULTS)
    for ok, name, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    passed = sum(1 for ok, _, _ in RESULTS if ok)
    print(f"\n自检汇总：{passed}/{len(RESULTS)} 通过")
    print("提示：B16（25 题逐题核对 + 整套核听）必须由真人完成，本脚本不覆盖。")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
