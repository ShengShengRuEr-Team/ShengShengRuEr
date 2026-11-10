"""Run environment-specific tests and fail when any required case is skipped."""

import argparse
import importlib.metadata
import json
import platform
import sys
import sysconfig
import unittest
from pathlib import Path

MODULES = {
    "asr": [
        "tests.module3.test_ctc_boundaries",
        "tests.module3.test_reference_locator",
    ],
    "ocr": ["tests.module3.test_printed_ocr"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=MODULES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "suite": args.suite,
        "python": platform.python_version(),
        "status": "FAIL",
        "packages": {
            item.metadata["Name"]: item.version
            for item in importlib.metadata.distributions()
        },
    }
    valid = (
        sys.version_info[:3] == (3, 13, 16)
        and sys.maxsize > 2**32
        and not sysconfig.get_config_var("Py_GIL_DISABLED")
    )
    if valid:
        suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES[args.suite])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        valid = result.wasSuccessful() and not result.skipped and result.testsRun > 0
        report.update(
            tests=result.testsRun,
            failures=len(result.failures),
            errors=len(result.errors),
            skipped=len(result.skipped),
        )
    else:
        report["issue"] = "Python 3.13.16 x64 with standard GIL is required"
    report["status"] = "PASS" if valid else "FAIL"
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
