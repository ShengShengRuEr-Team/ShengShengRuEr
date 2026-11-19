"""Server-computed changes between immutable responses, including rejected ones."""

from app.module3.contracts import fingerprint


def candidate_diff(before, after, *, before_call=None, after_call=None):
    def index(raw):
        assessments, candidates = {}, {}
        if not isinstance(raw, dict):
            return assessments, candidates
        for a in raw.get("distractor_assessments", []):
            if not isinstance(a, dict):
                continue
            letter = a.get("option_letter")
            assessments[letter] = a
            for c in a.get("candidates", []):
                if isinstance(c, dict):
                    candidates[(letter, c.get("error_cause_code"))] = c
        return assessments, candidates

    left_a, left = index(before)
    right_a, right = index(after)
    changes = []
    for key in sorted(left.keys() | right.keys(), key=str):
        a, b = left.get(key), right.get(key)
        if a == b:
            continue
        changes.append(
            {
                "kind": "added"
                if a is None
                else "deleted"
                if b is None
                else "candidate_changed",
                "option_letter": key[0],
                "error_cause_code": key[1],
                "evidence_changed": bool(
                    a and b and a.get("evidence") != b.get("evidence")
                ),
                "before": a,
                "after": b,
            }
        )
    for letter in sorted(left_a.keys() | right_a.keys(), key=str):
        a, b = left_a.get(letter), right_a.get(letter)
        if (
            a is None
            or b is None
            or any(
                a.get(k) != b.get(k)
                for k in (
                    "status",
                    "reason",
                    "comparison_evidence",
                    "unresolved_points",
                )
            )
        ):
            changes.append(
                {
                    "kind": "assessment_changed",
                    "option_letter": letter,
                    "before": a,
                    "after": b,
                }
            )
    removed = [c for c in changes if c["kind"] == "deleted"]
    added = [c for c in changes if c["kind"] == "added"]
    return {
        "before_hash": fingerprint(before),
        "after_hash": fingerprint(after),
        "before_call_id": before_call,
        "after_call_id": after_call,
        "changes": changes,
        "reclassifications": [
            {
                "option_letter": a["option_letter"],
                "from_code": a["error_cause_code"],
                "to_code": b["error_cause_code"],
            }
            for a in removed
            for b in added
            if a["option_letter"] == b["option_letter"]
        ],
        "semantic_deletion_review_required": bool(removed),
    }
