"""Align source sentences; recognition text cannot replace their words or IDs."""

import re
from itertools import pairwise

from app.module3 import audio
from app.module3.contracts import ProcessingError
from app.module3.ctc_alignment import METHOD_VERSION
from app.schemas_processing import ReferenceSegment


def align(normalized, rows, settings):
    references = [ReferenceSegment.model_validate(row) for row in rows]
    if not references:
        raise ProcessingError("REFERENCE_TEXT_REQUIRED", "缺少已核对的逐句原文")
    result = audio.align(
        normalized,
        {
            "boundary_method": METHOD_VERSION,
            "segments": [
                {
                    "text": row.text,
                    "start": row.search_start_ms / 1000,
                    "end": row.search_end_ms / 1000,
                }
                for row in references
            ]
        },
        settings,
    )
    id_map = {}
    merged = []
    position = 0

    def normalize(value):
        return re.sub(r"\s+", " ", value).strip()

    for row in references:
        parts, combined = [], ""
        target = normalize(row.text)
        while position < len(result["segments"]) and combined != target:
            part = result["segments"][position]
            combined = normalize(combined + " " + part["text"])
            if not target.startswith(combined):
                raise ProcessingError("REFERENCE_TEXT_CHANGED", "对齐输出改变了原文")
            parts.append(part)
            id_map[part["_src_id"]] = row.segment_id
            position += 1
        if combined != target or not parts:
            raise ProcessingError("REFERENCE_TEXT_CHANGED", "对齐遗漏原文句子")
        valid = all(
            p["start_ms"] is not None and p["end_ms"] is not None for p in parts
        )
        item = {
            "text": row.text,
            "start_ms": min(p["start_ms"] for p in parts) if valid else None,
            "end_ms": max(p["end_ms"] for p in parts) if valid else None,
            "alignment_status": "aligned"
            if valid and all(p["alignment_status"] == "aligned" for p in parts)
            else "requires_review",
            "chars": [c for p in parts for c in p.get("chars", [])],
            "offset_ms": 0,
            "boundary_method": result.get("boundary_method"),
            "alignment_score": min(
                (p.get("alignment_score", 1.0) for p in parts), default=0.0
            ),
            "alignment_parts": [
                {
                    k: p[k]
                    for k in (
                        "_src_id",
                        "text",
                        "start_ms",
                        "end_ms",
                        "alignment_status",
                    )
                }
                for p in parts
            ],
        }
        item.update(
            _src_id=row.segment_id,
            segment_type=row.segment_type,
            passage_key=row.passage_key,
            speaker=row.speaker,
            question_no=row.question_no,
            text_source="reference",
            source_storage_key=row.source_storage_key,
            source_sha256=row.source_sha256,
            source_pages=row.source_pages,
            search_start_ms=row.search_start_ms,
            search_end_ms=row.search_end_ms,
        )
        merged.append(item)
    if position != len(result["segments"]):
        raise ProcessingError("REFERENCE_TEXT_CHANGED", "对齐输出多出原文以外的句子")
    result["segments"] = merged
    for issue in result.get("issues", []):
        if "segment_src_ids" in issue:
            issue["segment_src_ids"] = list(
                dict.fromkeys(id_map[key] for key in issue["segment_src_ids"])
            )
    _refine_weak_windows(normalized, merged, result, settings)
    for left, right in pairwise(merged):
        if (
            left["end_ms"] is not None
            and left["start_ms"] is not None
            and right["start_ms"] is not None
            and (
                left["end_ms"] - right["start_ms"] > 300
                or right["start_ms"] < left["start_ms"]
            )
        ):
            left["alignment_status"] = right["alignment_status"] = "requires_review"
            result["issues"].append(
                {
                    "issue_code": "ALIGNMENT_NEIGHBOUR_CONFLICT",
                    "segment_src_ids": [left["_src_id"], right["_src_id"]],
                    "message": "相邻来源句出现时间倒序或明显重叠，保留异常",
                }
            )
    result["text_source"] = "reference"
    return result


def _refine_weak_windows(normalized, rows, result, settings):
    """Retry weak/edge matches in neighbour-derived context, never invent times."""
    issues = result.setdefault("issues", [])
    for index, row in enumerate(rows):
        edge = _touches_search_edge(row)
        if row.get("alignment_score", 1.0) >= 0.60 and not edge:
            continue
        start, end = row["search_start_ms"], row["search_end_ms"]
        previous = rows[index - 1] if index else None
        following = rows[index + 1] if index + 1 < len(rows) else None
        duration = result.get("duration_ms", end)
        left = (
            previous["end_ms"] - 250
            if previous
            and previous["passage_key"] == row["passage_key"]
            and previous["end_ms"] is not None
            else start - 2000
        )
        right = (
            following["start_ms"] + 250
            if following
            and following["passage_key"] == row["passage_key"]
            and following["start_ms"] is not None
            else end + 2000
        )
        retry_start, retry_end = max(0, min(start, left)), min(
            duration, max(end, right)
        )
        row["search_attempts"] = [
            {
                "start_ms": start,
                "end_ms": end,
                "alignment_score": row["alignment_score"],
            }
        ]
        if 0 < retry_end - retry_start <= 30000 and (retry_start, retry_end) != (
            start,
            end,
        ):
            retry = audio.align(
                normalized,
                {
                    "boundary_method": METHOD_VERSION,
                    "segments": [
                        {
                            "text": row["text"],
                            "start": retry_start / 1000,
                            "end": retry_end / 1000,
                        }
                    ],
                },
                settings,
            )
            candidates = retry.get("segments", [])
            if len(candidates) != 1 or candidates[0]["text"] != row["text"]:
                raise ProcessingError("REFERENCE_TEXT_CHANGED", "重对齐改变原文")
            candidate = candidates[0]
            row["search_attempts"].append(
                {
                    "start_ms": retry_start,
                    "end_ms": retry_end,
                    "alignment_score": candidate.get("alignment_score", 0),
                }
            )
            if (
                (
                    candidate.get("alignment_score", 0) > row["alignment_score"]
                    or (edge and candidate.get("alignment_score", 0) >= 0.60)
                )
                and candidate["alignment_status"] == "aligned"
                and not retry.get("issues")
            ):
                for key in (
                    "start_ms",
                    "end_ms",
                    "chars",
                    "alignment_score",
                    "boundary_method",
                    "alignment_status",
                ):
                    row[key] = candidate[key]
                row.update(
                    requested_search_start_ms=start,
                    requested_search_end_ms=end,
                    search_start_ms=retry_start,
                    search_end_ms=retry_end,
                    search_window_method="neighbour_bounded_ctc_retry",
                    alignment_parts=[
                        {
                            key: candidate[key]
                            for key in (
                                "_src_id",
                                "text",
                                "start_ms",
                                "end_ms",
                                "alignment_status",
                            )
                        }
                    ],
                )
        if row["alignment_score"] < 0.60:
            row["alignment_status"] = "requires_review"
            issues.append(
                {
                    "issue_code": "ALIGNMENT_LOW_CONFIDENCE",
                    "segment_src_ids": [row["_src_id"]],
                    "message": "局部重对齐后仍缺少可靠声学匹配，保留异常",
                }
            )
        elif _touches_search_edge(row):
            row["alignment_status"] = "requires_review"
            issues.append(
                {
                    "issue_code": "ALIGNMENT_SEARCH_EDGE",
                    "segment_src_ids": [row["_src_id"]],
                    "message": "扩窗后仍贴近搜索边缘，不能证明句子未被截断",
                }
            )


def _touches_search_edge(row):
    return (
        row.get("boundary_method") == METHOD_VERSION
        and row["start_ms"] is not None
        and row["end_ms"] is not None
        and (
            row["start_ms"] - row["search_start_ms"] <= 50
            or row["search_end_ms"] - row["end_ms"] <= 50
        )
    )
