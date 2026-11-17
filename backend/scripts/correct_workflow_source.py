"""Submit a reviewable source-only JSON correction through authenticated HTTP.

Example: python -m scripts.correct_workflow_source --workflow UUID --file patch.json
Use M3_ADMIN_TOKEN in the environment; never place credentials in a patch file.
The exact idempotency key and original body remain in a private recovery file.
"""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.schemas_processing_workflows import (
    AlignmentCorrectionRequest,
    SourceCorrectionRequest,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=UUID, required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--alignment", action="store_true")
    parser.add_argument("--key", type=UUID)
    args = parser.parse_args()
    url = urlparse(args.url)
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
    ):
        parser.error("校正接口须使用HTTPS或本机HTTP")
    token = os.environ.get("M3_ADMIN_TOKEN")
    if not token:
        parser.error("须设置实际管理员M3_ADMIN_TOKEN")
    model = AlignmentCorrectionRequest if args.alignment else SourceCorrectionRequest
    payload = model.model_validate_json(
        args.file.read_text(encoding="utf-8")
    ).model_dump(mode="json")
    recovery = args.file.with_suffix(args.file.suffix + ".operation.json")
    action = "alignment-corrections" if args.alignment else "source-corrections"
    endpoint = (
        f"{args.url.rstrip('/')}/api/v1/admin/processing-workflows/"
        f"{args.workflow}/{action}"
    )
    saved = {"key": str(args.key or uuid4()), "url": endpoint, "body": payload}
    if recovery.exists():
        prior = json.loads(recovery.read_text(encoding="utf-8"))
        if (
            prior["url"] != endpoint
            or prior["body"] != payload
            or (args.key and prior["key"] != str(args.key))
        ):
            parser.error("恢复记录对应不同请求；请先核对原操作，不能覆盖原键")
        saved = prior
    else:
        recovery.write_text(
            json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    with httpx.Client(timeout=60) as client:
        response = client.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": saved["key"],
            },
        )
    # Server projections contain safe command identities; no tokens/paths printed.
    print(response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
