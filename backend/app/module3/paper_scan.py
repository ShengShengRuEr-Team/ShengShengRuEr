"""Read image-only English exam papers using frozen native OCR components."""

import json
import re
from pathlib import Path

from app.module3.contracts import ProcessingError, atomic_json, file_hash


def extract(material, model_root, output):
    import numpy as np
    import pypdfium2
    from paddleocr import TextDetection, TextRecognition
    from paddlex.inference.pipelines.components import CropByPolys, SortQuadBoxes

    from app.module3.ocr_worker import model_directory
    from app.module3.reference_document_scan import value

    source = Path(material["path"])
    if file_hash(source) != material["sha256"]:
        raise ProcessingError("SOURCE_CHANGED", "扫描原卷身份发生变化")
    config = (
        Path(__file__).resolve().parents[2]
        / "config/module3/model-artifact-manifest.json"
    )
    models = json.loads(config.read_text(encoding="utf-8"))
    selected = {}
    for name in (
        "PP-OCRv5_mobile_det",
        "en_PP-OCRv5_mobile_rec",
        "PP-OCRv5_server_rec",
    ):
        model = next(m for m in models if m["repository"] == "PaddlePaddle/" + name)
        folder = model_directory(Path(model_root), model)
        if any(
            file_hash(folder / item["filename"]) != item["sha256"]
            for item in model["files"]
        ):
            raise ProcessingError("MODEL_HASH_MISMATCH", "扫描原卷模型哈希不符")
        selected[name] = folder
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
        model_name="en_PP-OCRv5_mobile_rec",
        model_dir=str(selected["en_PP-OCRv5_mobile_rec"]),
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
    )
    marker_recognizer = TextRecognition(
        model_name="PP-OCRv5_server_rec",
        model_dir=str(selected["PP-OCRv5_server_rec"]),
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
    )
    document = pypdfium2.PdfDocument(str(source))
    numbers = material.get("page_numbers") or list(range(1, len(document) + 1))
    if any(type(n) is not int or not 1 <= n <= len(document) for n in numbers):
        raise ProcessingError("PAGE_RANGE_INVALID", "扫描原卷页码超出原件")
    pages = []
    option_open = False
    try:
        for number in numbers:
            image = document[number - 1].render(scale=300 / 72).to_pil().convert("RGB")
            key = f"pages/{material['material_id']}-{number}.png"
            target = output / key
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target)
            pixels = np.asarray(image)
            detected = value(next(iter(detector.predict(pixels))))
            polygons = SortQuadBoxes()(np.asarray(detected["dt_polys"]))
            crops = CropByPolys(det_box_type="quad")(pixels, polygons)
            blocks = []
            for index, (polygon, crop) in enumerate(zip(polygons, crops, strict=True)):
                reading = value(next(iter(recognizer.predict(crop))))
                raw_text = reading["rec_text"].strip()
                text = raw_text
                if re.match(
                    r"^(?:Section\b|Directions:|Questions\s*\d|Part\s*III)", text, re.I
                ):
                    option_open = False
                if re.match(r"^\d+\.\s*A\)", text):
                    option_open = True
                marker_reading = None
                if option_open and not re.match(r"^(?:\d+\.\s*)?[ABCD]\)", text):
                    marker_reading = value(
                        next(
                            iter(
                                marker_recognizer.predict(
                                    crop[:, : min(crop.shape[1], 220)]
                                )
                            )
                        )
                    )
                    prefix_reading = dict(marker_reading)
                    if float(marker_reading["rec_score"]) < 0.85:
                        marker_reading = value(
                            next(iter(marker_recognizer.predict(crop)))
                        )
                        marker_reading["prefix_attempt"] = prefix_reading
                    marker = re.match(
                        r"^\s*([ABCD])\s*[)）]", marker_reading["rec_text"]
                    )
                    if marker and float(marker_reading["rec_score"]) >= 0.85:
                        # Only restore a source-read option marker. English words
                        # remain the recognizer's output; no dictionary respacing.
                        text = re.sub(r"^\)\s*", "", text)
                        text = re.sub(r"^" + marker[1] + r"(?=[A-Z][a-z])", "", text)
                        text = marker[1] + ") " + text
                points = np.asarray(polygon)
                blocks.append(
                    {
                        "text": text,
                        "raw_text": reading["rec_text"],
                        "marker_reading": marker_reading,
                        "confidence": float(reading["rec_score"]),
                        "block_index": index,
                        "box": [
                            *points.min(axis=0).astype(int).tolist(),
                            *points.max(axis=0).astype(int).tolist(),
                        ],
                        "polygon": points.tolist(),
                    }
                )
            page = {
                "material_id": material["material_id"],
                "source_kind": "paper_scan",
                "sha256": material["sha256"],
                "page": number,
                "text": "\n".join(b["text"] for b in blocks),
                "blocks": blocks,
                "page_image": key,
                "page_image_sha256": file_hash(target),
                "render_dpi": 300,
                "method": "PaddleOCR_native_English+PaddleX.SortQuadBoxes+CropByPolys",
                "model_manifest_sha256": file_hash(config),
            }
            pages.append(page)
            atomic_json(
                output, f"paper-pages/{material['material_id']}-{number}.json", page
            )
            image.close()
            print(f"paper scan page={number} blocks={len(blocks)}", flush=True)
    finally:
        document.close()
    return pages
