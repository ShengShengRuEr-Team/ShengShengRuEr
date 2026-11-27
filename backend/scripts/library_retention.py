"""Two-pass retention: scan to a reviewable manifest, then recheck selected IDs."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-manifest", type=Path)
    args = parser.parse_args()
    from app.db.base import SessionLocal
    from app.services.processing.library_versions import prune, retention_candidates

    with SessionLocal() as db:
        if args.execute_manifest:
            document = json.loads(args.execute_manifest.read_text(encoding="utf-8"))
            ids = [UUID(value) for value in document["candidate_ids"]]
            if len(ids) > 1000:
                raise ValueError("A retention manifest is limited to 1000 versions")
            results = {str(identity): prune(db, identity) for identity in ids}
            report = {"mode": "execute_rechecked", "results": results}
        else:
            report = {
                "mode": "scan_only",
                "candidate_ids": [str(i) for i in retention_candidates(db)],
            }
    report["observed_at"] = datetime.now(UTC).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Retention {report['mode']} written to {args.output}")


if __name__ == "__main__":
    main()
