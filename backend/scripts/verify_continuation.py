"""Focused continuation checks in a newly created, disposable database."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tests",
        nargs="+",
        default=[
            "tests/module3/test_workflows.py",
            "tests/module3/test_workflow_pipeline.py",
        ],
    )
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    output = backend / "var/verification" / ("continuation-" + uuid4().hex[:12])
    output.mkdir(parents=True)
    base = make_url(
        os.getenv("DATABASE_URL") or dotenv_values(backend / ".env")["DATABASE_URL"]
    )
    name = "m3_verify_" + uuid4().hex + "_test"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    created = False
    result = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        env = {
            **os.environ,
            "DATABASE_URL": base.set(database="postgres").render_as_string(False),
            "TEST_DATABASE_NAME": name,
            "JWT_SECRET_KEY": "continuation-test-" + uuid4().hex,
            "DEEPSEEK_API_KEY": "",
            "PYTHONIOENCODING": "utf-8",
            "AUDIO_STORAGE_DIR": str(output / "audio"),
            "M3_MATERIALS_DIR": str(output / "materials"),
            "M3_ARTIFACTS_DIR": str(output / "processing"),
        }
        with (output / "pytest.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *args.tests,
                    "-q",
                    "--tb=short",
                    "--junitxml",
                    str(output / "pytest.xml"),
                ],
                cwd=backend,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        print((output / "pytest.log").read_text(encoding="utf-8")[-12000:])
    finally:
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
        suites = (
            ElementTree.parse(output / "pytest.xml").findall(".//testsuite")
            if (output / "pytest.xml").exists()
            else []
        )
        (output / "summary.json").write_text(
            json.dumps(
                {
                    "exit_code": result.returncode if result else -1,
                    "database_cleanup": "PASS",
                    "scope": "synthetic technical checks, no semantic approval",
                    "pytest": {
                        key: sum(int(s.get(key, "0")) for s in suites)
                        for key in ("tests", "failures", "errors", "skipped")
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    print("Evidence:", output)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
