"""Bounded readability/decode probe in the appropriate frozen subprocess env."""

import argparse
import json
from pathlib import Path


def validate(path, kind):
    if kind in {"paper", "answer"}:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(path))
        try:
            count = len(document)
            if count < 1 or count > 500:
                raise ValueError("PDF page count out of bounds")
            for index in range(count):
                page = document[index]
                try:
                    bitmap = page.render(scale=0.1)
                    bitmap.close()
                finally:
                    page.close()
            return {"page_count": count, "media_type": "application/pdf"}
        finally:
            document.close()
    import av

    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError("audio stream required")
        frames = sum(frame.samples for frame in container.decode(audio=0))
        if frames <= 0:
            raise ValueError("empty audio")
    return {"decoded_samples": frames}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--kind", choices=["paper", "answer", "audio"], required=True)
    args = parser.parse_args()
    try:
        result = validate(args.path, args.kind)
    except Exception:
        print(json.dumps({"valid": False}))
        return 2
    print(json.dumps({"valid": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
