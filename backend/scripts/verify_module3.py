"""Collect reproducible technical evidence in newly created disposable databases.

This does not run paid inference or approve real-material/human acceptance.
Run from backend with the frozen API interpreter; no application modules are
imported here, so a developer's cached engine cannot become a test target.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

import httpx
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = BACKEND.parent
LEGACY = "0004_expected_count_source"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Verification:
    def __init__(self, output: Path):
        self.output = output
        self.output.mkdir(parents=True, exist_ok=False)
        self.report = {
            "started_at": datetime.now(UTC).isoformat(),
            "status": "RUNNING",
            "scope": "technical regression; synthetic data",
            "real_material_quality": "NOT_RUN",
            "human_audio_review": "NOT_RUN",
            "annotation_semantic_review": "NOT_RUN",
            "steps": [],
            "files": {},
        }
        self.save()

    def save(self):
        (self.output / "summary.json").write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def run(self, name, arguments, env, *, timeout=900):
        print(f"Running {name}", flush=True)
        started = time.monotonic()
        log = self.output / f"{name}.log"
        with log.open("w", encoding="utf-8") as stream:
            try:
                result = subprocess.run(
                    arguments,
                    cwd=BACKEND,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write(f"\n{type(error).__name__}: process did not complete\n")
                code = -1
        self.report["steps"].append(
            {
                "name": name,
                "exit_code": code,
                "duration_seconds": round(time.monotonic() - started, 3),
                "log": log.name,
                "sha256": sha256(log),
            }
        )
        self.save()
        if code:
            raise RuntimeError(f"{name} failed; see {log.name}")

    def snapshot(self, url, tables=None):
        engine = create_engine(url)
        try:
            inspector = inspect(engine)
            tables = tables or {
                name: {
                    "columns": [
                        column["name"] for column in inspector.get_columns(name)
                    ]
                }
                for name in inspector.get_table_names()
                if name != "alembic_version"
            }
            snapshot = {}
            with engine.connect() as connection:
                quote = engine.dialect.identifier_preparer.quote
                for table in sorted(tables):
                    columns = tables[table]["columns"]
                    projection = ", ".join(quote(column) for column in columns)
                    rows = (
                        connection.execute(
                            text(
                                f"SELECT row_to_json(t)::text FROM "
                                f"(SELECT {projection} FROM {quote(table)}) AS t"
                            )
                        )
                        .scalars()
                        .all()
                    )
                    # Sorting object keys ignores PostgreSQL column order changes.
                    canonical = sorted(
                        json.dumps(json.loads(row), sort_keys=True) for row in rows
                    )
                    digest = hashlib.sha256("\n".join(canonical).encode()).hexdigest()
                    snapshot[table] = {
                        "columns": columns,
                        "rows": len(rows),
                        "sha256": digest,
                    }
            return snapshot
        finally:
            engine.dispose()

    def migrations(self, python, url, env):
        migration_env = {**env, "DATABASE_URL": url.render_as_string(False)}
        for name, command in (
            ("clean-upgrade", ["upgrade", "head"]),
            ("clean-downgrade", ["downgrade", "base"]),
            ("legacy-upgrade", ["upgrade", LEGACY]),
            ("legacy-fixture", None),
        ):
            if command is None:
                self.run(
                    name,
                    [
                        python,
                        "-m",
                        "scripts.module3_legacy_fixture",
                        "--output",
                        str(self.output),
                    ],
                    migration_env,
                )
            else:
                self.run(name, [python, "-m", "alembic", *command], migration_env)
        before = self.snapshot(url)
        self.run(
            "legacy-to-head",
            [python, "-m", "alembic", "upgrade", "head"],
            migration_env,
        )
        after = self.snapshot(url, before)
        if before != after:
            raise RuntimeError("Module-two rows changed during upgrade")
        self.run(
            "head-to-legacy",
            [python, "-m", "alembic", "downgrade", LEGACY],
            migration_env,
        )
        rollback = self.snapshot(url, before)
        if before != rollback:
            raise RuntimeError("Module-two rows changed during downgrade")
        self.report["migration_preservation"] = {
            "before": before,
            "after_upgrade": after,
            "after_downgrade": rollback,
        }
        self.save()
        self.run(
            "legacy-reupgrade",
            [python, "-m", "alembic", "upgrade", "head"],
            migration_env,
        )

    def tcp_smoke(self, python, env):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        events = []
        with (self.output / "tcp-server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    python,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=BACKEND,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5
                ) as client:
                    deadline = time.monotonic() + 45
                    while True:
                        try:
                            response = client.get("/api/v1/openapi.json")
                            if response.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if server.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("TCP server failed to become ready")
                        time.sleep(0.2)
                    route = "/api/v1/admin/processing-tasks"
                    response = client.get(route)
                    events.append({"role": "anonymous", "status": response.status_code})
                    if response.status_code != 401:
                        raise RuntimeError("Anonymous admin access was not rejected")
                    for role, password, expected in (
                        ("student", "student123", 403),
                        ("admin", "admin123", 200),
                    ):
                        login = client.post(
                            "/api/v1/login",
                            json={
                                "username": role,
                                "password": password,
                            },
                        )
                        login.raise_for_status()
                        token = login.json()["data"]["token"]
                        response = client.get(
                            route,
                            headers={
                                "Authorization": "Bearer " + token,
                            },
                        )
                        events.append({"role": role, "status": response.status_code})
                        if response.status_code != expected:
                            raise RuntimeError(
                                f"TCP permission check failed for {role}"
                            )
            finally:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=15)
                (self.output / "tcp-permissions.json").write_text(
                    json.dumps(events, indent=2), encoding="utf-8"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("api", "all"), default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--asr-python", type=Path, default=BACKEND / ".venv-asr/Scripts/python.exe"
    )
    parser.add_argument(
        "--ocr-python", type=Path, default=BACKEND / ".venv-ocr/Scripts/python.exe"
    )
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = (args.output or BACKEND / "var/verification" / stamp).resolve()
    verification = Verification(output)
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "APP_ENV": "test",
        "JWT_SECRET_KEY": "module3-verification-only-" + uuid4().hex,
        "AUDIO_STORAGE_DIR": str(output / "audio"),
        "M3_MATERIALS_DIR": str(output / "materials"),
        "M3_ARTIFACTS_DIR": str(output / "processing"),
        "DEEPSEEK_API_KEY": "",
    }
    created = []
    admin = None
    try:
        profile = BACKEND / "config/module3/processing-profile.json"
        verification.report.update(
            python=platform.python_version(),
            platform=platform.platform(),
            suite=args.suite,
            commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
            ).strip(),
            working_tree=subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=REPOSITORY,
                text=True,
                encoding="utf-8",
            ).splitlines(),
            lock_hashes={
                path.name: sha256(path)
                for path in (BACKEND / "config/module3").glob("*.lock.txt")
            },
            profile_sha256=sha256(profile),
            packages={
                item.metadata["Name"]: item.version
                for item in importlib.metadata.distributions()
            },
        )
        sources = (
            subprocess.check_output(
                [
                    "git",
                    "ls-files",
                    "-z",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "backend/app",
                    "backend/alembic",
                    "backend/scripts",
                    "backend/tests",
                    "backend/config/module3",
                    "backend/pyproject.toml",
                    "backend/pytest.ini",
                    ".github/workflows",
                    "AGENTS.md",
                ],
                cwd=REPOSITORY,
            )
            .decode("utf-8")
            .split("\0")
        )
        verification.report["source_hashes"] = {
            name: sha256(REPOSITORY / name) for name in sources if name
        }
        verification.run(
            "api-diagnostics",
            [
                sys.executable,
                "-m",
                "app.module3.diagnostics",
                "--profile",
                "api",
                "--output",
                str(output / "diagnostics"),
            ],
            env,
        )
        config = dotenv_values(BACKEND / ".env")
        base = make_url(os.getenv("DATABASE_URL") or config["DATABASE_URL"])
        admin = create_engine(
            base.set(database="postgres"), isolation_level="AUTOCOMMIT"
        )
        names = [
            "m3_verify_" + uuid4().hex + suffix for suffix in ("_migration", "_test")
        ]
        with admin.connect() as connection:
            verification.report["postgresql"] = connection.scalar(
                text("SHOW server_version")
            )
            if verification.report["postgresql"] != "18.6":
                raise RuntimeError("PostgreSQL 18.6 is required by the frozen baseline")
            for name in names:
                # UUID names cannot escape identifiers; only successfully created
                # databases are ever eligible for cleanup.
                connection.execute(text(f'CREATE DATABASE "{name}"'))
                created.append(name)
        verification.report["databases"] = created.copy()
        url = base.set(database=names[0])
        env.update(
            DATABASE_URL=url.render_as_string(False), TEST_DATABASE_NAME=names[1]
        )
        verification.migrations(sys.executable, url, env)
        verification.run("seed", [sys.executable, "-m", "app.seed"], env)
        verification.tcp_smoke(sys.executable, env)
        verification.run(
            "idle-worker",
            [sys.executable, "-m", "app.module3.worker", "--once"],
            env,
            timeout=60,
        )
        verification.run(
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "--junitxml",
                str(output / "pytest.xml"),
            ],
            env,
        )
        suites = ElementTree.parse(output / "pytest.xml").findall(".//testsuite")
        verification.report["pytest"] = {
            key: sum(int(suite.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        verification.save()
        verification.run(
            "ruff",
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "app/module3",
                "app/services/processing",
                "app/api/admin_processing.py",
                "app/schemas_processing.py",
                "tests/module3",
                "scripts/verify_module3.py",
                "scripts/run_module3_unittests.py",
                "scripts/module3_legacy_fixture.py",
            ],
            env,
        )
        verification.run("diff-check", ["git", "diff", "--check"], env)
        for suite in ("asr", "ocr"):
            if args.suite == "api":
                verification.report[suite] = "NOT_RUN (API-only suite)"
                continue
            python = str(getattr(args, suite + "_python").resolve())
            verification.run(
                suite,
                [
                    python,
                    "-m",
                    "scripts.run_module3_unittests",
                    "--suite",
                    suite,
                    "--output",
                    str(output / f"{suite}.json"),
                ],
                env,
            )
        verification.report["status"] = "PASS_TECHNICAL"
    except Exception as error:
        verification.report.update(status="FAIL", error=type(error).__name__)
        print(
            f"Verification failed: {type(error).__name__}; inspect evidence", flush=True
        )
    finally:
        if admin is not None:
            try:
                with admin.connect() as connection:
                    for name in created:
                        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
                verification.report["database_cleanup"] = "PASS"
            except Exception as error:
                verification.report.update(
                    status="FAIL", database_cleanup=type(error).__name__
                )
            finally:
                admin.dispose()
        verification.report["finished_at"] = datetime.now(UTC).isoformat()
        for path in output.rglob("*"):
            if path.is_file() and path.name != "summary.json":
                verification.report["files"][path.relative_to(output).as_posix()] = (
                    sha256(path)
                )
        verification.save()
    print(f"{verification.report['status']}: {output / 'summary.json'}", flush=True)
    return 0 if verification.report["status"] == "PASS_TECHNICAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
