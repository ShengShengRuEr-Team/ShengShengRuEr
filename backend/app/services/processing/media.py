"""Private evidence cache preserving absolute source timestamps."""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

from app.core.config import BASE_DIR
from app.core.errors import AppError
from app.module3.contracts import fingerprint


def evidence_clip(source, audio_hash, start_ms, end_ms, settings):
    if not 0 <= start_ms < end_ms or end_ms - start_ms > 180000:
        raise AppError(422, "证据试听范围无效或超过3分钟")
    key = fingerprint(
        {
            "audio": audio_hash,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "method": "m3.clip.pcm16.v1",
        }
    )
    directory = settings.m3_path("m3_artifacts_dir") / "evidence-clips"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (key + ".wav")
    if target.is_file():
        return target
    if not settings.m3_asr_python or not Path(settings.m3_asr_python).is_file():
        raise AppError(409, "试听解码环境未配置", error_code="ENVIRONMENT_BLOCKED")
    staging = directory / (key + "-" + uuid4().hex + ".wav")
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() != "DATABASE_URL"
        and not k.upper().startswith(("JWT", "PG", "DEEPSEEK"))
    }
    try:
        result = subprocess.run(
            [
                settings.m3_asr_python,
                "-m",
                "app.module3.media_clip",
                "--source",
                str(source),
                "--target",
                str(staging),
                "--start-ms",
                str(start_ms),
                "--end-ms",
                str(end_ms),
            ],
            cwd=BASE_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        if result.returncode or not staging.exists() or staging.stat().st_size <= 44:
            raise AppError(422, "证据片段无法解码", error_code="MATERIAL_INVALID")
        try:
            os.link(staging, target)
        except FileExistsError:
            pass
        return target
    finally:
        staging.unlink(missing_ok=True)
