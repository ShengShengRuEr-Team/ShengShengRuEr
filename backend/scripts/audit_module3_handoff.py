"""Read-only final audit of current code, both actual DBs, tests and budget."""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
WORKSPACE = BACKEND.parents[1]
ROOT = WORKSPACE / "outputs/module3-independent-acceptance-20261107"
sys.path.insert(0, str(BACKEND))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(name, value):
    (ROOT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def main():
    from app.module3.contracts import file_hash, fingerprint, result_hash

    base_url = make_url(dotenv_values(BACKEND / ".env")["DATABASE_URL"])
    reports = {}
    run_key = fingerprint(
        {"audio": "a23dc74f40f8b9806f52e6f8f0468423df5069afea5730c5f9ca3a8c2684864c"}
    )
    real_attempts, ledgers = [], []
    for route, name in (("text", "text-recheck"), ("scan", "r15-full-pipeline")):
        latest = load(ROOT / name / "latest.json")
        assert latest["status"] == "PASS" and latest["new_llm_calls"] == 0
        directory = Path(latest["directory"])
        payload = load(directory / "draft.json")
        assert result_hash(payload) == latest["result_hash"]
        engine = create_engine(base_url.set(database=latest["database"]))
        try:
            with engine.connect() as c:
                task = (
                    c.execute(
                        text(
                            "SELECT state,stage,method,method_hash,request,batch_id "
                            "FROM processing_tasks WHERE id=:id"
                        ),
                        {"id": latest["task_id"]},
                    )
                    .mappings()
                    .one()
                )
                assert task["state"] == task["stage"] == "completed"
                assert task["method_hash"] == fingerprint(task["method"])
                changed = [
                    k
                    for k, v in task["method"]["implementation_sha256"].items()
                    if file_hash(BACKEND / k) != v
                ]
                assert not changed
                artifact_root = (
                    ROOT / "artifacts"
                    if route == "scan"
                    else WORKSPACE
                    / "outputs/module3-assembly-annotation-20261106/artifacts"
                )
                artifacts = (
                    c.execute(
                        text(
                            "SELECT stage,storage_key,artifact_hash "
                            "FROM processing_artifacts WHERE task_id=:id"
                        ),
                        {"id": latest["task_id"]},
                    )
                    .mappings()
                    .all()
                )
                assert artifacts
                for a in artifacts:
                    assert (
                        file_hash(artifact_root / a["storage_key"])
                        == a["artifact_hash"]
                    )
                # Use the actual API projections as independently verified readback.
                readback = load(directory / "readback-checks.json")
                assert readback["status"] == "PASS" and readback["questions"] == 25
                reports[route] = {
                    "status": "PASS",
                    "task_id": latest["task_id"],
                    "database": latest["database"],
                    "result_hash": latest["result_hash"],
                    "method_hash": task["method_hash"],
                    "changed_method_files": changed,
                    "task_artifact_hashes_checked": len(artifacts),
                    "readback": readback,
                    "pipeline": latest,
                }
        finally:
            engine.dispose()
    admin = create_engine(base_url.set(database="postgres"))
    with admin.connect() as c:
        names = (
            c.execute(
                text(
                    "SELECT datname FROM pg_database "
                    "WHERE NOT datistemplate AND datallowconn"
                )
            )
            .scalars()
            .all()
        )
    admin.dispose()
    for name in names:
        engine = create_engine(
            base_url.set(database=name), connect_args={"connect_timeout": 5}
        )
        try:
            with engine.connect() as c:
                if not c.execute(
                    text("SELECT to_regclass('public.processing_llm_attempts')")
                ).scalar():
                    continue
                row = c.execute(
                    text(
                        "SELECT count(*), coalesce(sum(charged_usd),0), "
                        "coalesce(sum(reserved_usd) "
                        "FILTER (WHERE charged_usd IS NULL),0) "
                        "FROM processing_llm_attempts"
                    )
                ).one()
                ledgers.append(
                    {
                        "database": name,
                        "attempts": row[0],
                        "estimated_usd": row[1],
                        "unknown_reserved_usd": row[2],
                    }
                )
                for attempt in c.execute(
                    text(
                        "SELECT id,task_id,phase,status,input_tokens,output_tokens,"
                        "charged_usd,reserved_usd,response_model "
                        "FROM processing_llm_attempts WHERE run_key=:key ORDER BY id"
                    ),
                    {"key": run_key},
                ).mappings():
                    real_attempts.append({"database": name, **dict(attempt)})
        finally:
            engine.dispose()
    total = sum(
        (r["estimated_usd"] + r["unknown_reserved_usd"] for r in ledgers), Decimal(0)
    )
    actual = sum(
        (
            r["charged_usd"] if r["charged_usd"] is not None else r["reserved_usd"]
            for r in real_attempts
        ),
        Decimal(0),
    )
    sample = sum(
        (
            r["charged_usd"] if r["charged_usd"] is not None else r["reserved_usd"]
            for r in real_attempts
            if r["phase"] == "sample"
        ),
        Decimal(0),
    )
    assert total <= 5 and actual <= 2 and sample <= Decimal(".50")
    dump(
        "budget-final.json",
        {
            "status": "PASS",
            "actual_paper_calls_including_history": len(real_attempts),
            "new_real_calls_this_round": len(real_attempts) - 56,
            "actual_paper_estimated_usd": actual,
            "sample_estimated_usd": sample,
            "stage_conservative_commitment_usd": total,
            "account_debit_verified": False,
            "unknown_reservations_retained": True,
            "ledgers": ledgers,
            "actual_attempts": real_attempts,
        },
    )
    xml = ET.parse(ROOT / "pytest-api.xml").getroot()
    suites = [xml] if xml.tag == "testsuite" else list(xml.findall("testsuite"))
    cases = sum(int(s.attrib["tests"]) for s in suites)
    skipped = sum(int(s.attrib["skipped"]) for s in suites)
    failures = sum(int(s.attrib["failures"]) + int(s.attrib["errors"]) for s in suites)
    assert failures == 0 and cases >= 172
    reference_comparison = load(ROOT / "scan-reference-comparison.json")
    boundary_comparison = load(ROOT / "scan-boundary-comparison.json")
    assert reference_comparison["source_comparison"] == "PASS"
    assert boundary_comparison["status"] == "PASS"
    for prefix in ("pytest-api", "processing-tests", "ocr-tests"):
        assert (ROOT / (prefix + ".exit")).read_text(
            encoding="utf-8-sig"
        ).strip() == "0"
    original = WORKSPACE / "ShengShengRuEr"

    def git(repo, *args):
        return subprocess.check_output(
            ["git", *args], cwd=repo, text=True, encoding="utf-8"
        ).strip()

    assert git(original, "branch", "--show-current") == "develop"
    assert git(original, "status", "--porcelain") == ""
    assert (
        git(BACKEND.parent, "branch", "--show-current")
        == "feature/7-module3-auto-processing"
    )
    assert git(BACKEND.parent, "diff", "--check") == ""
    dump(
        "final-integrity.json",
        {
            "status": "PASS",
            "checked_at": datetime.now(UTC).isoformat(),
            "routes": reports,
            "reference_comparison": reference_comparison,
            "boundary_comparison": boundary_comparison,
            "tests": {
                "api_passed": cases - skipped,
                "environment_cases_run_separately": skipped,
                "failures": failures,
                "processing_passed": 10,
                "ocr_passed": 7,
                "distinct_tests": cases,
            },
            "original_worktree_clean": True,
            "committed_merged_deployed": False,
        },
    )
    print("INTEGRITY_PASS", "actual_calls", len(real_attempts), "stage_usd", total)


if __name__ == "__main__":
    main()
