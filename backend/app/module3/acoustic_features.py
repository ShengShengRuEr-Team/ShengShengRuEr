"""Known-text acoustic features; never decode a recognition transcript."""

from __future__ import annotations

import gc
from pathlib import Path

from app.module3 import audio
from app.module3.contracts import atomic_json, file_hash


def acoustic_features(normalized, settings, output):
    import numpy as np
    import torch
    import whisperx

    identity = {
        "normalized_sha256": file_hash(normalized),
        "implementation_sha256": file_hash(Path(__file__)),
        "audio_implementation_sha256": file_hash(Path(audio.__file__)),
        "model_manifest_sha256": file_hash(
            Path(__file__).resolve().parents[2]
            / "config/module3/model-artifact-manifest.json"
        ),
    }
    manifest = output / "acoustic-metadata.json"
    if manifest.is_file():
        import json

        cached = json.loads(manifest.read_text(encoding="utf-8"))
        if cached["identity"] == identity and all(
            file_hash(output / name) == digest
            for name, digest in cached["files"].items()
        ):
            features = np.load(output / "acoustic-features.npy", allow_pickle=False)
            times = np.load(output / "acoustic-frame-times.npy", allow_pickle=False)
            print("verified acoustic feature cache reused (no transcript)", flush=True)
            return (
                torch.from_numpy(features),
                times,
                cached["metadata"],
                cached["duration_ms"],
            )
    audio.prepare_native(settings)
    samples = np.load(normalized, allow_pickle=False)
    model, metadata = whisperx.load_align_model(
        language_code="en",
        device="cpu",
        model_name=str(
            audio.local_model(settings, "jonatasgrosman/wav2vec2-large-xlsr-53-english")
        ),
        model_cache_only=True,
    )
    model.eval()
    emissions, times = [], []
    chunk, context = 20 * 16000, 2 * 16000
    try:
        for index, first in enumerate(range(0, len(samples), chunk), 1):
            last = min(len(samples), first + chunk)
            left, right = max(0, first - context), min(len(samples), last + context)
            waveform = torch.from_numpy(samples[left:right].copy()).unsqueeze(0)
            with torch.inference_mode():
                values = model(waveform).logits.log_softmax(-1).cpu()
            count = values.shape[1]
            ratio = (right - left) / count
            starts = left + np.arange(count) * ratio
            ends = starts + ratio
            centres = (starts + ends) / 2
            select = (centres >= first) & (centres < last)
            emissions.append(values[:, select, :])
            times.append(np.stack([starts[select], ends[select]], axis=1) / 16)
            print(
                f"acoustic features chunk={index} end_ms={round(last / 16)}", flush=True
            )
    finally:
        del model
        gc.collect()
    features = torch.cat(emissions, dim=1)
    frame_times = np.concatenate(times)
    np.save(output / "acoustic-features.npy", features.numpy(), allow_pickle=False)
    np.save(output / "acoustic-frame-times.npy", frame_times, allow_pickle=False)
    duration = round(len(samples) / 16)
    atomic_json(
        output,
        "acoustic-metadata.json",
        {
            "identity": identity,
            "metadata": metadata,
            "duration_ms": duration,
            "files": {
                name: file_hash(output / name)
                for name in ["acoustic-features.npy", "acoustic-frame-times.npy"]
            },
            "asr_calls": 0,
            "historical_transcript_used": False,
        },
    )
    return features, frame_times, metadata, duration
