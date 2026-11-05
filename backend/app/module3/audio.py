"""Local audio adapters. Heavy libraries are imported only inside processing calls."""

from __future__ import annotations

import gc
import json
import os
import re
from pathlib import Path

from app.module3.contracts import ProcessingError, file_hash

_DLL_HANDLES = []


def prepare_native(settings):
    import site

    paths = [Path(settings.ffmpeg_dll_dir)]
    for packages in site.getsitepackages():
        paths.extend(Path(packages).glob("nvidia/*/bin"))
    for path in paths:
        if path.is_dir() and hasattr(os, "add_dll_directory"):
            _DLL_HANDLES.append(os.add_dll_directory(str(path.resolve())))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if settings.nltk_data:
        os.environ["NLTK_DATA"] = settings.nltk_data


def local_model(settings, repository):
    config = (
        Path(__file__).resolve().parents[2]
        / "config/module3/model-artifact-manifest.json"
    )
    manifest = json.loads(config.read_text(encoding="utf-8"))
    entry = next(m for m in manifest if m["repository"] == repository)
    directory = (
        settings.m3_path("m3_model_root")
        / repository.replace("/", "--")
        / entry["revision"]
    )
    for item in entry["files"]:
        path = directory / item["filename"]
        if not path.is_file() or file_hash(path) != item["sha256"]:
            raise ProcessingError("MODEL_HASH_MISMATCH", "固定本地模型未通过哈希检查")
    return directory


def decode(source, destination, settings):
    prepare_native(settings)
    import numpy as np
    from torchcodec.decoders import AudioDecoder

    try:
        decoder = AudioDecoder(str(source), sample_rate=16000, num_channels=1)
        samples = decoder.get_all_samples()
        audio = (
            samples.data.squeeze(0).contiguous().numpy().astype(np.float32, copy=False)
        )
    except Exception:
        raise ProcessingError("AUDIO_DECODE_FAILED", "固定TorchCodec解码失败") from None
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ProcessingError("AUDIO_DECODE_FAILED", "音频必须为有限float32单声道")
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.save(destination, audio, allow_pickle=False)
    return {
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "float32",
        "sample_count": int(audio.size),
        "duration_ms": round(audio.size / 16),
        "file_sha256": file_hash(source),
        "normalized_sha256": file_hash(destination),
        "decoder": "torchcodec",
        "offset_ms": 0,
    }


def transcribe(normalized, settings):
    prepare_native(settings)
    import numpy as np
    import torch
    from faster_whisper import WhisperModel

    if not torch.cuda.is_available():
        raise ProcessingError("GPU_UNAVAILABLE", "当前GPU profile不可静默回退CPU")
    directory = local_model(settings, "Systran/faster-whisper-large-v3")
    model = WhisperModel(
        str(directory),
        device="cuda",
        compute_type="int8_float16",
        local_files_only=True,
        num_workers=1,
    )
    try:
        stream, info = model.transcribe(
            np.load(normalized, allow_pickle=False),
            language="en",
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        items = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "words": [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.probability,
                    }
                    for w in (s.words or [])
                ],
            }
            for s in stream
        ]
        return {"language": info.language, "segments": items}
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()


def align(normalized, transcription, settings):
    prepare_native(settings)
    import numpy as np
    import whisperx

    directory = local_model(settings, "jonatasgrosman/wav2vec2-large-xlsr-53-english")
    model, metadata = whisperx.load_align_model(
        language_code="en",
        device="cpu",
        model_name=str(directory),
        model_cache_only=True,
    )
    try:
        raw = whisperx.align(
            transcription["segments"],
            model,
            metadata,
            np.load(normalized, allow_pickle=False),
            device="cpu",
            return_char_alignments=True,
            interpolate_method="ignore",
        )
    finally:
        del model
        gc.collect()
    segments = []
    for i, item in enumerate(raw["segments"]):
        chars = item.get("chars", [])
        spoken = [c for c in chars if c.get("char", "").isalnum()]
        aligned = bool(spoken) and all(
            c.get("start") is not None and c.get("end") is not None for c in spoken
        )
        start, end = item.get("start"), item.get("end")
        segments.append(
            {
                "_src_id": f"seg:{i + 1}",
                "text": item["text"].strip(),
                "start_ms": round(start * 1000) if start is not None else None,
                "end_ms": round(end * 1000) if end is not None else None,
                "alignment_status": "aligned" if aligned else "requires_review",
                "chars": chars,
                "offset_ms": 0,
            }
        )
    source_words = re.findall(
        r"\w+", " ".join(s["text"] for s in transcription["segments"]).casefold()
    )
    aligned_words = re.findall(r"\w+", " ".join(s["text"] for s in segments).casefold())
    issues = []
    if source_words != aligned_words:
        issues.append(
            {
                "issue_code": "ALIGNMENT_TEXT_LOSS",
                "source_words": len(source_words),
                "aligned_words": len(aligned_words),
            }
        )
    return {"segments": segments, "issues": issues}
