"""Version-two fingerprints, separate from the immutable legacy hash algorithm."""

from copy import deepcopy
from pathlib import Path

from app.module3.contracts import file_hash, fingerprint, result_identity

RESULT_VERSION = "m3.v2"
ERROR_RULE_VERSION = "m3.option-errors.v1"
PROMPT_VERSION = "m3.annotations.v6"
CHECK_VERSION = "m3.checks.v2"


def request_hash(action: str, target: str | None, payload: dict) -> str:
    # Original preconditions are deliberately part of the accepted request.
    return fingerprint({"action": action, "target": target, "payload": payload})


def rules_manifest() -> dict:
    root = Path(__file__).resolve().parents[2]
    files = (
        "app/module3/annotation_identity.py",
        "app/module3/annotations.py",
        "app/module3/annotation_checks.py",
    )
    content = {
        "result_version": RESULT_VERSION,
        "error_rule_version": ERROR_RULE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "check_version": CHECK_VERSION,
        "dictionary_sha256": file_hash(root / "config/module3/dictionary-schema.json"),
        "implementation": {name: file_hash(root / name) for name in files},
        # Enabled only after the new candidate/worker path is actually implemented.
        "generation_enabled": False,
    }
    return {**content, "manifest_hash": fingerprint(content)}


def materials_hash(materials: list[dict], document_mode: str) -> str:
    return fingerprint(
        {
            "version": RESULT_VERSION,
            "document_mode": document_mode,
            "materials": sorted(materials, key=lambda row: row["kind"]),
        }
    )


def question_input_hash(payload: dict, question: dict) -> str:
    passage = question["passage_src_id"]
    source_ids = {question["_src_id"], passage} | {
        s["_src_id"]
        for s in payload["transcript_segments"]
        if s["passage_src_id"] == passage
    }
    return fingerprint(
        {
            "version": RESULT_VERSION,
            "question": question,
            "passage": [p for p in payload["passages"] if p["_src_id"] == passage],
            "segments": sorted(
                [
                    s
                    for s in payload["transcript_segments"]
                    if s["passage_src_id"] == passage
                ],
                key=lambda row: (row["segment_index"], row["_src_id"]),
            ),
            "source_refs": sorted(
                [
                    r
                    for r in payload.get("source_refs", [])
                    if r.get("src_id") in source_ids
                ],
                key=fingerprint,
            ),
        }
    )


def sample_dependency_hash(payload: dict, manifest: dict) -> str:
    return fingerprint(
        {
            "version": RESULT_VERSION,
            "rules_manifest": manifest,
            "sample": [
                {
                    "question_src_id": q["_src_id"],
                    "input_hash": question_input_hash(payload, q),
                }
                for q in payload["questions"][:5]
            ],
        }
    )


def result_hash(payload: dict, manifest: dict) -> str:
    normalized = deepcopy(payload)
    # Review/progress metadata cannot change immutable content identity.
    for key in ("review", "review_session", "read_at", "row_version"):
        normalized.pop(key, None)
    return fingerprint(
        {
            "version": RESULT_VERSION,
            "rules_manifest": manifest,
            "content": result_identity(normalized),
        }
    )
