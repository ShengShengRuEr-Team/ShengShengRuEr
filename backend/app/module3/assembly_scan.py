"""Read answer/explanation rows with frozen PaddleOCR/PaddleX components.

This is a downstream scan: reference text and alignment are never rewritten.
"""

import json
from pathlib import Path

from app.module3.contracts import ProcessingError, atomic_json, file_hash
from app.module3.ocr_worker import model_directory
from app.module3.reference_document_scan import value


def extract(manifest, output):
    import numpy as np
    import pypdfium2
    from paddleocr import TextDetection, TextRecognition
    from paddlex.inference.pipelines.components import CropByPolys, SortQuadBoxes

    config = (
        Path(__file__).resolve().parents[2]
        / "config/module3/model-artifact-manifest.json"
    )
    models = json.loads(config.read_text(encoding="utf-8"))
    root = Path(manifest["model_root"])
    selected = {}
    for name in ("PP-OCRv5_mobile_det", "PP-OCRv5_server_rec"):
        model = next(m for m in models if m["repository"] == "PaddlePaddle/" + name)
        for item in model["files"]:
            if (
                file_hash(model_directory(root, model) / item["filename"])
                != item["sha256"]
            ):
                raise ProcessingError("MODEL_HASH_MISMATCH", "组装OCR模型哈希不符")
        selected[name] = model_directory(root, model)
    detector = TextDetection(
        model_name="PP-OCRv5_mobile_det",
        model_dir=str(selected["PP-OCRv5_mobile_det"]),
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
        limit_side_len=1536,
        limit_type="max",
    )
    recognizer = TextRecognition(
        model_name="PP-OCRv5_server_rec",
        model_dir=str(selected["PP-OCRv5_server_rec"]),
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
    )
    pages = []
    for material in manifest["files"]:
        if material["source_kind"] != "answer_explanation":
            continue
        if file_hash(Path(material["path"])) != material["sha256"]:
            raise ProcessingError("SOURCE_CHANGED", "组装前答案原件哈希不符")
        document = pypdfium2.PdfDocument(material["path"])
        for number in material["page_numbers"]:
            image = document[number - 1].render(scale=300 / 72).to_pil().convert("RGB")
            key = f"pages/{material['material_id']}-{number}.png"
            path = output / key
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path)
            pixels = np.asarray(image)
            detected = value(next(iter(detector.predict(pixels))))
            polygons = SortQuadBoxes()(np.asarray(detected["dt_polys"]))
            crops = list(CropByPolys(det_box_type="quad")(pixels, polygons))
            blocks = []
            for i, (polygon, crop) in enumerate(zip(polygons, crops, strict=True)):
                reading = value(next(iter(recognizer.predict(crop))))
                points = np.asarray(polygon)
                blocks.append(
                    {
                        "text": reading["rec_text"],
                        "confidence": float(reading["rec_score"]),
                        "box": [
                            *points.min(axis=0).astype(int).tolist(),
                            *points.max(axis=0).astype(int).tolist(),
                        ],
                        "polygon": points.tolist(),
                        "block_index": i,
                    }
                )
            page = {
                "material_id": material["material_id"],
                "source_kind": material["source_kind"],
                "sha256": material["sha256"],
                "page": number,
                "blocks": blocks,
                "text": "\n".join(b["text"] for b in blocks),
                "page_image": key,
                "page_image_sha256": file_hash(path),
                "render_dpi": 300,
                "method": "PaddleOCR+PaddleX.SortQuadBoxes+CropByPolys",
                "model_manifest_sha256": file_hash(config),
            }
            pages.append(page)
            atomic_json(
                output, f"page-results/{material['material_id']}-{number}.json", page
            )
            image.close()
            print(f"assembly scan page={number} blocks={len(blocks)}", flush=True)
        document.close()
    return {"schema_version": "m3.assembly-scan.v1", "pages": pages}
