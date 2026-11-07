"""Fail-closed runtime validation; exit zero only for the checked environment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import sys
import sysconfig
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.module3.contracts import file_hash


def diagnose(profile: str, settings=None):
    if settings is None and profile == "ocr":
        root = Path(os.environ.get("M3_MODEL_ROOT", "var/models")).resolve()
        settings = SimpleNamespace(m3_path=lambda _: root)
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    issues = []
    report = {
        "profile": profile,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "created_at": datetime.now(UTC).isoformat(),
        "issues": issues,
    }
    if (
        sys.version_info[:3] != (3, 13, 16)
        or sys.maxsize <= 2**32
        or sysconfig.get_config_var("Py_GIL_DISABLED")
    ):
        issues.append("PYTHON_VERSION_MISMATCH")
    from app.services.processing.validation import CONFIG_DIR

    environment = "asr" if profile == "align" else profile
    report["lock_sha256"] = file_hash(
        CONFIG_DIR / f"requirements-{environment}.lock.txt"
    )
    expected = {
        "api": {
            "fastapi": "0.143.0",
            "sqlalchemy": "2.1.4",
            "starlette": "1.7.0",
            "httpx2": "2.13.1",
        },
        "asr": {
            "torch": "2.8.0+cu128",
            "faster-whisper": "1.2.1",
            "whisperx": "3.8.6",
            "torchcodec": "0.7.0",
        },
        "align": {
            "torch": "2.8.0+cu128",
            "torchaudio": "2.8.0+cu128",
            "whisperx": "3.8.6",
            "torchcodec": "0.7.0",
        },
        "ocr": {
            "paddleocr": "3.7.0",
            "paddlex": "3.7.2",
            "paddlepaddle": "3.3.1",
            "pypdfium2": "5.14.0",
        },
    }[profile]
    report["packages"] = {}
    for name, version in expected.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        report["packages"][name] = actual
        if actual != version:
            issues.append("PACKAGE_MISMATCH:" + name)
    if profile in {"asr", "ocr", "align"}:
        manifest = json.loads(
            (CONFIG_DIR / "model-artifact-manifest.json").read_text(encoding="utf-8")
        )
        for model in manifest:
            if (
                profile == "align"
                and model["repository"]
                != "jonatasgrosman/wav2vec2-large-xlsr-53-english"
            ):
                continue
            if model["repository"].startswith("PaddlePaddle/") != (profile == "ocr"):
                continue
            directory = (
                settings.m3_path("m3_model_root")
                / model["repository"].replace("/", "--")
                / model["revision"]
            )
            for item in model["files"]:
                path = directory / item["filename"]
                if not path.is_file() or file_hash(path) != item["sha256"]:
                    issues.append(
                        "MODEL_HASH_MISMATCH:"
                        + model["repository"]
                        + "/"
                        + item["filename"]
                    )
    if profile in {"asr", "align"} and not issues:
        dll_dir = Path(settings.ffmpeg_dll_dir)
        native = json.loads(
            (CONFIG_DIR / "ffmpeg-artifact-manifest.json").read_text(encoding="utf-8")
        )
        for item in native["bin_artifacts"]:
            path = dll_dir / Path(item["path"]).name
            if not path.is_file() or file_hash(path) != item["sha256"]:
                issues.append("NATIVE_HASH_MISMATCH:" + path.name)
        if not issues:
            handle = (
                os.add_dll_directory(str(dll_dir))
                if hasattr(os, "add_dll_directory")
                else None
            )
            try:
                import torch
                from torchcodec.decoders import AudioDecoder  # noqa: F401

                if profile == "asr":
                    report["cuda_available"] = torch.cuda.is_available()
                    if not report["cuda_available"]:
                        issues.append("GPU_UNAVAILABLE")
            except (ImportError, OSError, RuntimeError) as exc:
                issues.append("NATIVE_IMPORT_FAILED:" + type(exc).__name__)
                report["native_error"] = str(exc)
            finally:
                if handle:
                    handle.close()
    report["status"] = "PASS" if not issues else "BLOCKED"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=("api", "asr", "ocr", "align"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-root", type=Path)
    args = parser.parse_args()
    if args.model_root:
        os.environ["M3_MODEL_ROOT"] = str(args.model_root.resolve())
    report = diagnose(args.profile)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f"diagnostics-{args.profile}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(report["status"], *report["issues"], sep="\n")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
