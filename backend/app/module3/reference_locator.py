"""Locate known source sentences in audio, without an ASR transcript or old times."""

from __future__ import annotations

from app.module3.acoustic_features import acoustic_features
from app.module3.contracts import ProcessingError
from app.module3.ctc_alignment import emission_spans, source_symbols

LOCATOR_VERSION = "m3.source-acoustic-locator.v1"


def locate(normalized, rows, settings, output):
    import numpy as np
    import torch

    features, times, metadata, duration = acoustic_features(
        normalized, settings, output
    )
    dictionary = metadata["dictionary"]
    blank = dictionary.get("<pad>", dictionary.get("[pad]", 0))
    groups = list(dict.fromkeys(row["passage_key"] for row in rows))
    anchors = []
    cursor = 0
    for group in groups:
        body = [
            row
            for row in rows
            if row["passage_key"] == group and row["segment_type"] == "body"
        ]
        parts = []
        for row in body[:4]:
            parts.append(row["text"])
            if sum(sum(c.isalnum() for c in text) for text in parts) >= 70:
                break
        text = " ".join(parts)
        labels = source_symbols(text, dictionary)
        spans = emission_spans(features[:, cursor:, :], labels, dictionary, blank)
        spoken = [
            span
            for (offset, _), span in zip(labels, spans, strict=True)
            if text[offset].isalnum()
        ]
        score = sum(span.score for span in spoken) / len(spoken)
        if score < 0.45:
            raise ProcessingError(
                "REFERENCE_AUDIO_ANCHOR_WEAK", "无法在原音中可靠定位来源篇章"
            )
        first, last = cursor + spoken[0].start, cursor + spoken[-1].end - 1
        anchor = {
            "passage_key": group,
            "start_ms": round(times[first, 0]),
            "end_ms": round(times[last, 1]),
            "score": round(score, 4),
            "source_text": text,
        }
        anchors.append(anchor)
        cursor = last + 1
        print(
            f"source anchor {group} {anchor['start_ms']}ms score={score:.4f}",
            flush=True,
        )
    located = []
    diagnostics = []
    for index, group in enumerate(groups):
        selected = [row for row in rows if row["passage_key"] == group]
        begin = max(0, anchors[index]["start_ms"] - 600)
        end = anchors[index + 1]["start_ms"] if index + 1 < len(groups) else duration
        first = max(0, int(np.searchsorted(times[:, 1], begin, side="right")))
        last = min(len(times), int(np.searchsorted(times[:, 0], end, side="left")))
        emissions = features[:, first:last, :]
        gap_id = emissions.shape[-1]
        emissions = torch.cat(
            [emissions, torch.zeros((*emissions.shape[:2], 1), dtype=emissions.dtype)],
            dim=-1,
        )
        local_dictionary = {**dictionary, "__sentence_gap__": gap_id}
        labels, slices = [], []
        for row in selected:
            source = source_symbols(row["text"], dictionary)
            start = len(labels)
            labels.extend(source)
            slices.append((start, len(labels), source))
            labels.append((-1, "__sentence_gap__"))
        labels.pop()
        spans = emission_spans(emissions, labels, local_dictionary, blank)
        for row, (a, b, source) in zip(selected, slices, strict=True):
            speech = [
                span
                for (offset, _), span in zip(source, spans[a:b], strict=True)
                if row["text"][offset].isalnum()
            ]
            start_ms = round(times[first + speech[0].start, 0])
            end_ms = round(times[first + speech[-1].end - 1, 1])
            search_start, search_end = (
                max(0, start_ms - 1000),
                min(duration, end_ms + 1000),
            )
            if search_end - search_start > 30000:
                raise ProcessingError(
                    "REFERENCE_LOCATOR_SPAN_TOO_LONG",
                    "来源句的定位范围异常，不能平均分配时间",
                )
            located.append(
                {**row, "search_start_ms": search_start, "search_end_ms": search_end}
            )
            diagnostics.append(
                {
                    "segment_id": row["segment_id"],
                    "coarse_start_ms": start_ms,
                    "coarse_end_ms": end_ms,
                    "score": round(sum(s.score for s in speech) / len(speech), 4),
                }
            )
        print(f"source group located {group} sentences={len(selected)}", flush=True)
    return {
        "segments": located,
        "locator": {
            "version": LOCATOR_VERSION,
            "asr_calls": 0,
            "historical_artifacts_used": False,
            "anchors": anchors,
            "sentences": diagnostics,
            "chunk_seconds": 20,
            "context_seconds": 2,
        },
    }
