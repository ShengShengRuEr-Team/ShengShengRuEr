"""Deterministic identities, safe local paths and durable JSON artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import os
import re
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any

SCHEMA_VERSION = "m3.v1"
RULE_VERSION = "m3.checks.v1"
STAGES = (
    "registered",
    "preflight",
    "extract",
    "normalize",
    "reference",
    "transcribe",
    "align",
    "assemble",
    "annotate",
    "validate",
    "persist",
    "review",
    "completed",
)


class ProcessingError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def issue(self, stage: str, **location: Any) -> dict:
        return {
            "issue_code": self.code,
            "severity": "error",
            "stage": stage,
            "message": str(self),
            "retryable": self.retryable,
            **location,
        }


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def result_identity(payload: dict) -> dict:
    """Normalize temporary IDs and unordered entity collections for result identity."""
    result = copy.deepcopy(payload)
    maps = {}
    fields = {
        "passage_src_id": "passages",
        "question_src_id": "questions",
        "question_segment_src_id": "transcript_segments",
        "segment_src_id": "transcript_segments",
        "segment_src_ids": "transcript_segments",
        "evidence_src_id": "evidences",
        "language_item_src_id": "language_items",
        "content_group_src_id": "content_groups",
    }

    def normalized(row, section):
        value = {}
        for key, item in row.items():
            if key in {"_src_id", "task_id", "created_at", "id_mapping"}:
                continue
            if key == "relation_code" and "relations" in section:
                continue
            target = section if key == "owner_relation_src_id" else fields.get(key)
            if target:
                mapping = maps.get(target, {})
                item = (
                    [mapping.get(str(x), str(x)) for x in item]
                    if isinstance(item, list)
                    else mapping.get(str(item), str(item))
                )
            value[key] = item
        return value

    for section, code in (
        ("content_groups", "content_group_code"),
        ("passages", "passage_code"),
        ("transcript_segments", None),
        ("questions", "question_code"),
        ("presentations", None),
        ("language_items", "item_code"),
        ("evidences", None),
        ("skill_question_relations", None),
        ("error_question_relations", None),
        ("other_relations", None),
    ):
        maps[section] = {}
        rows = result.get(section, [])
        ordered = sorted(rows, key=lambda row: bool(row.get("owner_relation_src_id")))
        for row in ordered:
            value = normalized(row, section)
            stable_key = (
                str(row[code]) if code and row.get(code) else fingerprint(value)
            )
            maps[section][str(row.get("_src_id"))] = stable_key
        values = [normalized(row, section) for row in rows]
        result[section] = sorted(values, key=canonical_bytes)
    for key in ("task_id", "created_at", "id_mapping", "runtime"):
        result.pop(key, None)
    return result


def result_hash(payload: dict) -> str:
    return fingerprint(result_identity(payload))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def controlled_path(root: Path, key: str, *, must_exist: bool = True) -> Path:
    """Interpret every key with Windows semantics, even in Linux tests."""
    windows = PureWindowsPath(key)
    if (
        not key
        or ntpath.isreserved(key)
        or "\x00" in key
        or ":" in key
        or windows.drive
        or windows.root
        or key.startswith(("/", "\\"))
        or any(
            p in ("", ".", "..") or p.endswith((" ", "."))
            for p in re.split(r"[/\\]", key)
        )
    ):
        raise ProcessingError("UNSAFE_PATH", "仅接受受控目录内的相对文件路径")
    base = root.resolve(strict=True)
    target = base.joinpath(*windows.parts).resolve(strict=must_exist)
    if not target.is_relative_to(base) or target == base:
        raise ProcessingError("UNSAFE_PATH", "文件解析后超出受控目录")
    if must_exist and not target.is_file():
        raise ProcessingError("SOURCE_MISSING", "材料文件不存在")
    return target


def atomic_json(root: Path, key: str, data: Any) -> tuple[str, int]:
    root.mkdir(parents=True, exist_ok=True)
    path = controlled_path(root, key, must_exist=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = canonical_bytes(data)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        # Artifacts are immutable. A matching repeat is safe; a collision is not.
        if path.exists():
            if path.read_bytes() != blob:
                raise ProcessingError("ARTIFACT_CONFLICT", "不可覆盖已存在的阶段产物")
        else:
            # Hard link publishes without replacing a concurrently created file.
            try:
                os.link(tmp, path)
            except FileExistsError:
                if path.read_bytes() != blob:
                    raise ProcessingError(
                        "ARTIFACT_CONFLICT", "阶段产物并发冲突"
                    ) from None
    finally:
        tmp.unlink(missing_ok=True)
    return hashlib.sha256(blob).hexdigest(), len(blob)


def media_type(path: Path) -> str:
    with path.open("rb") as stream:
        head = stream.read(64)
    signatures = (
        (head.startswith(b"%PDF-"), {".pdf"}, "application/pdf"),
        (head.startswith(b"\x89PNG\r\n\x1a\n"), {".png"}, "image/png"),
        (head.startswith(b"\xff\xd8\xff"), {".jpg", ".jpeg"}, "image/jpeg"),
        (head.startswith((b"II*\x00", b"MM\x00*")), {".tif", ".tiff"}, "image/tiff"),
        (head.startswith(b"RIFF") and head[8:12] == b"WAVE", {".wav"}, "audio/wav"),
        (head.startswith(b"fLaC"), {".flac"}, "audio/flac"),
        (head.startswith(b"OggS"), {".ogg", ".opus"}, "audio/ogg"),
        (head[4:8] == b"ftyp", {".m4a", ".mp4"}, "audio/mp4"),
        (
            head.startswith(b"ID3")
            or (len(head) > 1 and head[0] == 255 and head[1] & 224 == 224),
            {".mp3"},
            "audio/mpeg",
        ),
    )
    for matches, extensions, mime in signatures:
        if matches and path.suffix.lower() in extensions:
            return mime
    raise ProcessingError("MEDIA_TYPE_INVALID", "文件内容与支持的媒体类型不符")
