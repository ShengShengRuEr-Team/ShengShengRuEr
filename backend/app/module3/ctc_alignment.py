"""Align fixed English source text without treating punctuation as speech.

The frozen WhisperX model supplies CTC emissions. TorchAudio's frozen CTC
decoder keeps blank frames separate from emitted characters. Free context
guards absorb unrelated speech before/after the supplied sentence; neither
guards nor blank frames are assigned to the first/last source character.
"""

from __future__ import annotations

import math
import unicodedata
from itertools import pairwise

from app.module3.contracts import ProcessingError

METHOD_VERSION = "m3.reference-ctc.v2"
SAMPLE_RATE = 16000


def source_symbols(text, dictionary):
    """Return source offsets and acoustic labels; preserve original text elsewhere."""
    labels = []
    for index, char in enumerate(text):
        symbol = char.lower().replace("’", "'")
        if char.isspace() or unicodedata.category(char) == "Pd":
            symbol = "|"
        if symbol in dictionary or char.isalnum():
            if symbol == "|" and (not labels or labels[-1][1] == "|"):
                continue
            labels.append((index, symbol))
    while labels and labels[-1][1] == "|":
        labels.pop()
    return labels


def emission_spans(emission, labels, dictionary, blank):
    """Decode emitted labels; virtual guards allow free prefix/suffix context."""
    import torch
    from torchaudio.functional import forced_align, merge_tokens

    tokens = [dictionary.get(symbol) for _, symbol in labels]
    if not tokens:
        raise ProcessingError("ALIGNMENT_EMPTY_TEXT", "原文没有可对齐的发音字符")
    if any(token is None for token in tokens):
        # Preserve digits/unsupported letters as explicit acoustic wildcards.
        # Punctuation has already been removed and never becomes a wildcard.
        mask = torch.ones(emission.shape[-1], dtype=torch.bool)
        mask[blank] = False
        for symbol, token in dictionary.items():
            if symbol.startswith("__"):
                mask[token] = False
        wildcard_id = emission.shape[-1]
        wildcard = emission[:, :, mask].max(-1, keepdim=True).values
        emission = torch.cat([emission, wildcard], dim=-1)
        tokens = [wildcard_id if token is None else token for token in tokens]
    guard = emission.shape[-1]
    guarded = torch.cat(
        [emission, torch.zeros((*emission.shape[:2], 1), dtype=emission.dtype)],
        dim=-1,
    )
    targets = [guard, *tokens, guard]
    repeats = sum(a == b for a, b in pairwise(targets))
    if guarded.shape[1] < len(targets) + repeats:
        raise ProcessingError("ALIGNMENT_WINDOW_TOO_SHORT", "搜索范围不足以对齐原文")
    paths, scores = forced_align(
        guarded, torch.tensor([targets], dtype=torch.int64), blank=blank
    )
    spans = merge_tokens(paths[0], scores[0].exp(), blank=blank)
    if [span.token for span in spans] != targets:
        raise ProcessingError("ALIGNMENT_TEXT_LOSS", "CTC未完整覆盖固定原文字符")
    spoken = spans[1:-1]
    # Free context guards must not eat part of a sustained first/last label.
    # Extend only through consecutive frames dominated by that SAME label;
    # blank frames, another label and neighbouring source tokens remain separate.
    for index in {0, len(spoken) - 1}:
        span = spoken[index]
        lower = spoken[index - 1].end if index else 0
        upper = (
            spoken[index + 1].start if index + 1 < len(spoken) else emission.shape[1]
        )

        def same_label(frame, token=span.token):
            values = emission[0, frame]
            return bool(
                values[token] > values[blank] and values[token] >= values.max() - 1e-6
            )

        while span.start > lower and same_label(span.start - 1):
            span.start -= 1
        while span.end < upper and same_label(span.end):
            span.end += 1
        span.score = emission[0, span.start : span.end, span.token].exp().mean().item()
    return spoken


def align_segments(segments, model, metadata, samples):
    import torch

    dictionary = metadata["dictionary"]
    blank = dictionary.get("<pad>", dictionary.get("[pad]", 0))
    if metadata["type"] != "huggingface" or metadata["language"] != "en":
        raise ProcessingError(
            "ALIGNMENT_MODEL_UNSUPPORTED", "原文路径需固定英文CTC模型"
        )
    output = []
    for segment in segments:
        text = segment["text"]
        start, end = segment["start"], segment["end"]
        if not (
            all(isinstance(t, (int, float)) and math.isfinite(t) for t in (start, end))
            and 0 <= start < end <= len(samples) / SAMPLE_RATE
        ):
            raise ProcessingError("ALIGNMENT_WINDOW_INVALID", "原文搜索范围超出音频")
        first = round(start * SAMPLE_RATE)
        last = round(end * SAMPLE_RATE)
        waveform = torch.from_numpy(samples[first:last].copy()).unsqueeze(0)
        if waveform.shape[-1] < 400:
            raise ProcessingError(
                "ALIGNMENT_WINDOW_TOO_SHORT", "搜索范围短于模型最小输入"
            )
        with torch.inference_mode():
            emission = model(waveform).logits.log_softmax(-1).cpu()
        labels = source_symbols(text, dictionary)
        spans = emission_spans(emission, labels, dictionary, blank)
        seconds_per_frame = waveform.shape[-1] / SAMPLE_RATE / emission.shape[1]
        chars = [{"char": char} for char in text]
        for (offset, _), span in zip(labels, spans, strict=True):
            chars[offset].update(
                start=round(first / SAMPLE_RATE + span.start * seconds_per_frame, 3),
                end=round(first / SAMPLE_RATE + span.end * seconds_per_frame, 3),
                score=round(span.score, 4),
            )
        spoken = [char for char in chars if char["char"].isalnum()]
        if not spoken or any("start" not in char for char in spoken):
            raise ProcessingError("ALIGNMENT_TEXT_LOSS", "原文发音字符缺少对齐依据")
        output.append(
            {
                "text": text,
                "start": spoken[0]["start"],
                "end": spoken[-1]["end"],
                "chars": chars,
                "boundary_method": METHOD_VERSION,
                "alignment_score": round(
                    sum(char["score"] for char in spoken) / len(spoken), 4
                ),
            }
        )
    return {"segments": output}
