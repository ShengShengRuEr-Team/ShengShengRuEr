"""Inspect stage-7/8 files only; never execute business validation or persistence."""

import argparse
import csv
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory
    payload = load(directory / "draft.json")
    aligned = load(directory / "align-api.json")["data"]["result"]
    reference = load(directory / "reference-api.json")["data"]["result"]
    extracted = load(directory / "extract-api.json")["data"]["result"]
    segments = {s["_src_id"]: s for s in payload["transcript_segments"]}
    upstream = {s["_src_id"]: s for s in aligned["segments"]}
    refs = {r["segment_id"]: r for r in reference["segments"]}
    pages = {(p["material_id"], p["page"]): p for p in extracted["pages"]}
    expected = reference["trusted_question_structure"]["question_count"]
    questions = payload["questions"]
    assert sorted(q["question_index"] for q in questions) == list(
        range(1, expected + 1)
    )
    assert len({q["_src_id"] for q in questions}) == expected
    assert set(segments) == set(upstream) == set(refs)
    assert all(
        s.get("speaker") == refs[sid].get("speaker") for sid, s in segments.items()
    )
    assert all(
        (s["text"], s["start_ms"], s["end_ms"])
        == (upstream[sid]["text"], upstream[sid]["start_ms"], upstream[sid]["end_ms"])
        for sid, s in segments.items()
    )
    rows = []
    for q in questions:
        s = segments[q["question_segment_src_id"]]
        assert s["text"] == q["question_text"] and s["segment_type"] == "question"
        assert refs[s["_src_id"]]["question_no"] == q["question_index"]
        assert s["passage_src_id"] == q["passage_src_id"]
        source = q["source_refs"][0]
        page = pages[(source["material_id"], source["locator"]["page"])]
        for letter in "abcd":
            assert (
                q["option_" + letter].strip() and q["option_" + letter] in page["text"]
            )
        assert q["correct_option"] in "ABCD"
        key = next(
            r for r in q["source_refs"] if r.get("role") == "independent_answer_key"
        )
        numbers, letters = key["original_text"].splitlines()
        column = key["locator"]["column"]
        assert int(numbers.split()[column]) == q["question_index"]
        assert letters.split()[column] == q["correct_option"]
        assert all(
            line in [r.get("original_text") for r in q["source_refs"]]
            for line in q["explanation_text"].splitlines()
        )
        assert all(
            len(r.get("sha256", "")) == 64 and r["locator"].get("page", 0) > 0
            for r in q["source_refs"]
        )
        mapping = next(
            p for p in payload["presentations"] if p["question_src_id"] == q["_src_id"]
        )
        assert mapping["question_no"] == q["question_index"]
        assert mapping["option_letter_mapping"] == dict(
            zip("ABCD", "ABCD", strict=True)
        )
        rows.append(
            {
                "question_no": q["question_index"],
                "passage": q["passage_src_id"],
                "question": q["question_text"],
                **{letter.upper(): q["option_" + letter] for letter in "abcd"},
                "answer": q["correct_option"],
                "explanation": q["explanation_text"],
                "question_segment_id": s["_src_id"],
                "start_ms": s["start_ms"],
                "end_ms": s["end_ms"],
                "paper_page": source["locator"]["page"],
                "answer_source": q["explanation_source"],
            }
        )
    with (directory / "questions.tsv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)
    dump(
        directory / "source-checks.json",
        {
            "status": "PASS",
            "module_step": 7,
            "questions": expected,
            "options": expected * 4,
            "independent_key_agreement": expected,
            "passages": len(payload["passages"]),
            "segments_unchanged": len(segments),
            "endpoints_unchanged": len(segments) * 2,
            "question_source_and_ownership": "PASS",
            "explanation_source_lines": "PASS",
            "mapping": "PASS",
            "issues": [],
            "scope": (
                "source/structure consistency; semantic review reported separately"
            ),
        },
    )
    if payload.get("evidences"):
        from app.module3.annotation_checks import check_candidate

        # Recheck all saved accepted candidates against the frozen full draft.
        root = (
            directory.parent
            / "artifacts"
            / load(directory / "final-task.json")["data"]["id"]
        )
        checks = []
        for p in sorted((root / "annotate").glob("*.json")):
            candidate = load(p)
            q = next(
                q for q in questions if q["_src_id"] == candidate["question_src_id"]
            )
            checks.append(check_candidate(payload, q, candidate["candidate"]))
        evidence_rows = []
        for relation in [
            *payload["skill_question_relations"],
            *payload["other_relations"],
            *payload["error_question_relations"],
        ]:
            if relation["relation_kind"] not in {
                "SKILL_EVIDENCE",
                "ANSWER_EVIDENCE",
                "CANDIDATE_EVIDENCE",
            }:
                continue
            evidence = next(
                e
                for e in payload["evidences"]
                if e["_src_id"] == relation["evidence_src_id"]
            )
            if relation.get("owner_relation_src_id"):
                owner = next(
                    r
                    for r in [
                        *payload["skill_question_relations"],
                        *payload["error_question_relations"],
                    ]
                    if r["_src_id"] == relation["owner_relation_src_id"]
                )
                qid = owner["question_src_id"]
            else:
                owner = relation
                qid = relation["question_src_id"]
            selected = [segments[sid] for sid in evidence["segment_src_ids"]]
            assert evidence["start_ms"] == selected[0]["start_ms"]
            assert evidence["end_ms"] == selected[-1]["end_ms"]
            evidence_rows.append(
                {
                    "question": qid,
                    "relation_kind": relation["relation_kind"],
                    "code": owner.get("skill_code", owner.get("error_cause_code", "")),
                    "role": owner.get("role", ""),
                    "segment_ids": ",".join(evidence["segment_src_ids"]),
                    "quote": evidence["evidence_text"],
                    "start_ms": evidence["start_ms"],
                    "end_ms": evidence["end_ms"],
                    "reason": json.dumps(
                        owner.get("attributes_json", {}), ensure_ascii=False
                    ),
                }
            )
        with (directory / "skills-evidence.tsv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(evidence_rows[0]), dialect="excel-tab"
            )
            writer.writeheader()
            writer.writerows(evidence_rows)
        dump(
            directory / "annotation-recheck.json",
            {
                "status": "PASS",
                "module_step": 8,
                "candidate_count": len(checks),
                "checks": checks,
                "evidence_count": len(evidence_rows),
                "semantic_accuracy": "separate content review required",
            },
        )
    print("PASS", directory, "questions", expected, "segments", len(segments))


if __name__ == "__main__":
    main()
