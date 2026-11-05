"""OCR-environment subprocess. No database/configuration imports or credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.module3.contracts import ProcessingError, atomic_json, file_hash


def model_directory(root, model):
    return root / model["repository"].replace("/", "--") / model["revision"]


def make_ocr(model_root):
    from paddleocr import PaddleOCR

    config = (
        Path(__file__).resolve().parents[2]
        / "config/module3/model-artifact-manifest.json"
    )
    models = json.loads(config.read_text(encoding="utf-8"))
    selected = [m for m in models if m["repository"].startswith("PaddlePaddle/")]
    for model in selected:
        for item in model["files"]:
            path = model_directory(model_root, model) / item["filename"]
            if not path.is_file() or file_hash(path) != item["sha256"]:
                raise ProcessingError(
                    "MODEL_HASH_MISMATCH", "OCR本地模型缺失或哈希不符"
                )
    det = next(m for m in selected if m["repository"].endswith("_det"))
    rec = next(m for m in selected if m["repository"].endswith("_rec"))
    return PaddleOCR(
        device="cpu",
        text_detection_model_name="PP-OCRv5_server_det",
        text_detection_model_dir=str(model_directory(model_root, det)),
        text_recognition_model_name="PP-OCRv5_server_rec",
        text_recognition_model_dir=str(model_directory(model_root, rec)),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        text_det_limit_side_len=1536,
        text_det_limit_type="max",
        text_recognition_batch_size=1,
        cpu_threads=4,
    )


def extract(manifest, output_dir):
    import pdfplumber
    import pypdfium2

    pages = []
    ocr = None
    model_root = Path(manifest["model_root"])
    for material in manifest["files"]:
        path = Path(material["path"])
        if file_hash(path) != material["sha256"]:
            raise ProcessingError("SOURCE_CHANGED", "提取前原件哈希不符")
        scan = material["source_kind"] == "paper_scan"
        if not scan and path.suffix.lower() == ".pdf":
            with pdfplumber.open(path) as document:
                for number, page in enumerate(document.pages, 1):
                    if (
                        material.get("page_numbers")
                        and number not in material["page_numbers"]
                    ):
                        continue
                    text = page.extract_text(layout=False) or ""
                    if text.strip() and "\ufffd" not in text:
                        pages.append(
                            {
                                "material_id": material["material_id"],
                                "page": number,
                                "source_kind": material["source_kind"],
                                "method": "pdfplumber",
                                "text": text,
                                "words": page.extract_words(),
                                "page_size": [page.width, page.height],
                            }
                        )
                    else:
                        scan = True
                        break
            if not scan:
                continue
            # Rerender this material; retain each page's actual route explicitly.
            pages = [p for p in pages if p["material_id"] != material["material_id"]]
        if ocr is None:
            ocr = make_ocr(model_root)
        if path.suffix.lower() == ".pdf":
            document = pypdfium2.PdfDocument(path)
            selected = material.get("page_numbers") or list(range(1, len(document) + 1))
            if any(number > len(document) or number < 1 for number in selected):
                raise ProcessingError("PAGE_RANGE_INVALID", "材料页码超出原件")
            images = (
                (i + 1, document[i].render(scale=300 / 72).to_pil())
                for i in range(len(document))
                if i + 1 in selected
            )
        else:
            from PIL import Image

            images = [(1, Image.open(path).convert("RGB"))]
        for number, image in images:
            import numpy as np

            print(
                f"OCR material={material['material_id']} page={number} started",
                flush=True,
            )

            image_key = f"pages/{material['material_id']}-{number}.png"
            image_path = output_dir / image_key
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(image_path)
            results = list(ocr.predict(np.asarray(image)))
            blocks = []
            for result in results:
                obj = result.json
                if isinstance(obj, str):
                    obj = json.loads(obj)
                obj = obj.get("res", obj)
                texts, scores = obj.get("rec_texts", []), obj.get("rec_scores", [])
                boxes = obj.get("rec_boxes", obj.get("rec_polys", []))
                for i, text in enumerate(texts):
                    box = boxes[i]
                    blocks.append(
                        {
                            "text": text,
                            "confidence": float(scores[i]),
                            "box": box.tolist() if hasattr(box, "tolist") else box,
                        }
                    )
            pages.append(
                {
                    "material_id": material["material_id"],
                    "page": number,
                    "source_kind": material["source_kind"],
                    "method": "PaddleOCR",
                    "text": "\n".join(b["text"] for b in blocks),
                    "blocks": blocks,
                    "page_image": image_key,
                    "page_image_sha256": file_hash(image_path),
                    "render_dpi": 300,
                    "detection_limit_side_len": 1536,
                    "detection_limit_type": "max",
                    "recognition_batch_size": 1,
                }
            )
            atomic_json(
                output_dir,
                f"page-results/{material['material_id']}-{number}.json",
                pages[-1],
            )
            print(
                f"OCR material={material['material_id']} "
                f"page={number} blocks={len(blocks)}",
                flush=True,
            )
            image.close()
        if path.suffix.lower() == ".pdf":
            document.close()
    return {"schema_version": "m3.v1", "pages": pages}


def derive_scan(source, target):
    import pypdfium2

    document = pypdfium2.PdfDocument(source)
    images = [
        document[i].render(scale=300 / 72).to_pil().convert("RGB")
        for i in range(len(document))
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        target, "PDF", save_all=True, append_images=images[1:], resolution=300
    )
    for image in images:
        image.close()
    document.close()
    return {
        "source_sha256": file_hash(source),
        "derived_sha256": file_hash(target),
        "render_dpi": 300,
        "renderer": "pypdfium2==5.14.0",
        "image_only": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--derive-scan", type=Path)
    args = parser.parse_args()
    if args.derive_scan:
        result = derive_scan(args.derive_scan, args.output)
        print(json.dumps(result))
        return 0
    if not args.manifest:
        parser.error("--manifest is required for extraction")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    result = extract(manifest, args.output)
    atomic_json(args.output, "extracted.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
