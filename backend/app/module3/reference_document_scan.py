"""Read reference regions only; classify line prefixes before expensive OCR."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.module3.contracts import ProcessingError, atomic_json, file_hash
from app.module3.document_reference import HEADING, paper_structure
from app.module3.ocr_refinement import (
    verify_question_number,
)


def value(result):
    data = result.json
    if isinstance(data, str):
        data = json.loads(data)
    return data.get("res", data)


def printed_line_boxes(image):
    """Find horizontal printed rows at original resolution, preserving glyphs."""
    import cv2
    import numpy as np

    black = np.asarray(image.convert("L")) < 180
    # Answer boxes can join a question to the following options in row
    # projection. Remove long table rules from layout pixels only.
    binary = black.astype("uint8")
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, np.ones((1, max(80, image.width // 10)), "uint8")
    )
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, np.ones((max(80, image.height // 25), 1), "uint8")
    )
    black &= (horizontal | vertical) == 0
    margin = max(3, round(image.width * 0.025))
    black[:, :margin] = False
    black[:, -margin:] = False
    occupied = np.flatnonzero(black.sum(1) > max(8, image.width * 0.008))
    if not occupied.size:
        return []
    start = previous = int(occupied[0])
    bands = []
    for value in occupied[1:]:
        row = int(value)
        if row - previous - 1 > 4:
            bands.append((start, previous + 1))
            start = row
        previous = row
    bands.append((start, previous + 1))
    boxes = []
    heights = [bottom - top for top, bottom in bands if bottom - top >= 7]
    minimum_height = max(7, round(float(np.median(heights)) * 0.5)) if heights else 7
    for top, bottom in bands:
        if bottom - top < minimum_height:
            continue
        # Dense-row detection suppresses table borders; recover sparse glyph
        # dots/descenders before cropping the original image for recognition.
        nearby_top, nearby_bottom = max(0, top - 6), min(image.height, bottom + 6)
        sparse = np.flatnonzero(black[nearby_top:nearby_bottom].sum(1) > 1)
        if sparse.size:
            top = nearby_top + int(sparse[0])
            bottom = nearby_top + int(sparse[-1]) + 1
        columns = np.flatnonzero(black[top:bottom].sum(0) > 1)
        if columns.size and columns[-1] - columns[0] > 10:
            boxes.append([int(columns[0]), top, int(columns[-1]) + 1, bottom])
    return boxes


def latin_prefix(image, box):
    """Cheap typography triage; headings are always recognized separately."""
    import numpy as np

    x1, y1, x2, y2 = box
    crop = np.asarray(image.convert("L"))[y1:y2, x1 : min(x2, x1 + 500)] < 180
    occupied = np.flatnonzero(crop.sum(0) > 1)
    if not occupied.size:
        return False
    widths = []
    start = previous = int(occupied[0])
    for item in occupied[1:]:
        column = int(item)
        if column - previous > 1:
            widths.append(previous - start + 1)
            start = column
        previous = column
    widths.append(previous - start + 1)
    return bool(np.median(widths) / max(1, y2 - y1) < 0.65)


def extract_reference_only(manifest, output):
    import numpy as np
    import pdfplumber
    import pypdfium2
    from paddleocr import TextDetection, TextRecognition
    from paddlex.inference.pipelines.components import CropByPolys, SortQuadBoxes
    from PIL import Image

    from app.module3.ocr_worker import model_directory

    config = (
        Path(__file__).resolve().parents[2]
        / "config/module3/model-artifact-manifest.json"
    )
    root = Path(manifest["model_root"])
    models = [
        m
        for m in json.loads(config.read_text(encoding="utf-8"))
        if m["repository"].startswith("PaddlePaddle/")
    ]
    for model in models:
        for item in model["files"]:
            if (
                file_hash(model_directory(root, model) / item["filename"])
                != item["sha256"]
            ):
                raise ProcessingError("MODEL_HASH_MISMATCH", "OCR模型哈希不符")
    detector = recognizer = english_recognizer = None
    pages = []
    for material in sorted(
        manifest["files"],
        key=lambda m: m["source_kind"] not in {"paper_text", "paper_scan"},
    ):
        path = Path(material["path"])
        if file_hash(path) != material["sha256"]:
            raise ProcessingError("SOURCE_CHANGED", "原件哈希不符")
        if material["source_kind"] == "paper_text":
            with pdfplumber.open(path) as document:
                selected = material.get("page_numbers")
                if selected and any(n < 1 or n > len(document.pages) for n in selected):
                    raise ProcessingError("PAGE_RANGE_INVALID", "材料页码超出原件")
                content = [
                    (i, p.extract_text() or "")
                    for i, p in enumerate(document.pages, 1)
                    if not selected or i in selected
                ]
            if content and all(text.strip() for _, text in content):
                pages.extend(
                    {
                        "material_id": material["material_id"],
                        "page": i,
                        "source_kind": material["source_kind"],
                        "method": "pdfplumber",
                        "text": text,
                    }
                    for i, text in content
                )
                continue
        if material["source_kind"] in {"paper_text", "paper_scan"}:
            # Scanned papers need their full question-heading context. The
            # reference-region filter below is for answer/transcript pages.
            from app.module3.ocr_worker import extract

            fallback = extract(
                {
                    **manifest,
                    "reference_only": False,
                    "prepare_reference": False,
                    "files": [material],
                },
                output,
            )
            pages.extend(fallback["pages"])
            continue
        expected_count = paper_structure(pages)["question_count"]
        question_numbers = set()
        if recognizer is None:
            det = next(
                m
                for m in models
                if m["repository"] == "PaddlePaddle/PP-OCRv5_mobile_det"
            )
            rec = next(
                m
                for m in models
                if m["repository"] == "PaddlePaddle/PP-OCRv5_server_rec"
            )
            recognizer = TextRecognition(
                model_name="PP-OCRv5_server_rec",
                model_dir=str(model_directory(root, rec)),
                device="cpu",
                enable_mkldnn=False,
                cpu_threads=4,
            )
            english = next(
                m
                for m in models
                if m["repository"] == "PaddlePaddle/en_PP-OCRv5_mobile_rec"
            )
            english_recognizer = TextRecognition(
                model_name="en_PP-OCRv5_mobile_rec",
                model_dir=str(model_directory(root, english)),
                device="cpu",
                enable_mkldnn=False,
                cpu_threads=4,
            )
        document = pypdfium2.PdfDocument(path)
        selected = material.get("page_numbers")
        if selected and any(n < 1 or n > len(document) for n in selected):
            raise ProcessingError("PAGE_RANGE_INVALID", "材料页码超出原件")
        current, mode = False, None
        for number in range(1, len(document) + 1):
            selected = material.get("page_numbers")
            if selected and number not in selected:
                continue
            image = document[number - 1].render(scale=300 / 72).to_pil().convert("RGB")
            image_key = f"pages/{material['material_id']}-{number}.png"
            image_path = output / image_key
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(image_path)
            if detector is None:
                detector = TextDetection(
                    model_name="PP-OCRv5_mobile_det",
                    model_dir=str(model_directory(root, det)),
                    device="cpu",
                    enable_mkldnn=False,
                    cpu_threads=4,
                    limit_side_len=1536,
                    limit_type="max",
                )
            detected = value(next(iter(detector.predict(np.asarray(image)))))
            polygons = SortQuadBoxes()(np.asarray(detected["dt_polys"]))
            boxes = []
            for polygon in polygons:
                points = np.asarray(polygon)
                x1, y1 = points.min(axis=0)
                x2, y2 = points.max(axis=0)
                boxes.append([int(x1), int(y1), int(x2), int(y2)])
            crops = list(CropByPolys(det_box_type="quad")(np.asarray(image), polygons))
            layout_method = "PP-OCRv5_mobile_det+PaddleX.SortQuadBoxes+CropByPolys"
            blocks = []
            stop = False
            for index, (box, pixels) in enumerate(zip(boxes, crops, strict=True)):
                crop = Image.fromarray(pixels)
                prefix_end = crop.width if crop.width < 900 else 320
                if crop.width >= 900 and not current:
                    blocks.append(
                        {
                            "text": "",
                            "box": box,
                            "text_scope": "unselected_nonreference_row",
                        }
                    )
                    crop.close()
                    continue
                prefix = crop.crop((0, 0, prefix_end, crop.height))
                if current and mode == "body" and crop.width >= 900:
                    recognized = {"rec_text": "", "rec_score": 0}
                    known_body_row = True
                else:
                    recognized = value(
                        next(
                            iter(
                                (
                                    english_recognizer if not current else recognizer
                                ).predict(np.asarray(prefix))
                            )
                        )
                    )
                    known_body_row = False
                prefix.close()
                text = recognized["rec_text"].strip()
                compact = re.sub(r"\s+", "", text)
                need_full = False
                if known_body_row:
                    need_full = True
                elif HEADING.match(text):
                    current, mode = True, None
                elif "听力原文" in compact:
                    mode = "body"
                elif "答案详解" in compact:
                    mode = "questions"
                elif current and re.search(
                    r"Part\s*III|Reading\s*Comprehension|选词填空", text, re.I
                ):
                    stop = True
                elif (
                    current
                    and mode == "body"
                    and re.search(r"[A-Za-z]", text)
                    and not re.search(r"[\u4e00-\u9fff]", text)
                ):
                    need_full = True
                elif (
                    current
                    and mode == "questions"
                    and re.match(r"^\d+\s*[.．]\s*[A-Za-z]", text)
                ):
                    need_full = True
                elif material["source_kind"] in {"paper_text", "paper_scan"}:
                    need_full = bool(
                        re.search(r"Questions?\s*\d|Part\s*II", text, re.I)
                    )
                block = {
                    "text": text,
                    "box": box,
                    "confidence": float(recognized["rec_score"]),
                    "text_scope": "line_prefix",
                }
                if need_full:
                    full = value(
                        next(iter(english_recognizer.predict(np.asarray(crop))))
                    )
                    reading = full.get("raw_text", full["rec_text"])
                    number_readings = None
                    if mode == "questions":
                        reading, number_readings = verify_question_number(
                            text, reading, crop, english_recognizer
                        )
                        question_numbers.add(int(re.match(r"\s*(\d+)", reading)[1]))
                        if question_numbers == set(range(1, expected_count + 1)):
                            stop = True
                    crop.close()
                    if mode == "questions" and "?" in reading:
                        reading = reading.split("?", 1)[0] + "?"
                    block.update(
                        text=reading,
                        raw_text=full.get("raw_text", reading),
                        confidence=float(full["rec_score"]),
                        text_scope="full_source_line",
                        prefix_text=text,
                        recognition_model="en_PP-OCRv5_mobile_rec",
                        crop_preprocessing="PaddleX.CropByPolys_quad",
                        number_readings=number_readings,
                    )
                    if mode == "body" and float(full["rec_score"]) < 0.90:
                        raise ProcessingError(
                            "REFERENCE_OCR_UNCERTAIN",
                            "正文识别可信度不足，保留原件，不以词典改写文字",
                        )
                crop.close()
                blocks.append(block)
                print(
                    f"reference scan material={material['material_id']} page={number} "
                    f"line={index + 1}/{len(boxes)} selected={need_full}",
                    flush=True,
                )
                if stop:
                    break
            page = {
                "material_id": material["material_id"],
                "page": number,
                "source_kind": material["source_kind"],
                "method": "PaddleOCR_reference_regions",
                "text": "\n".join(b["text"] for b in blocks),
                "blocks": blocks,
                "reference_blocks": blocks,
                "page_image": image_key,
                "page_image_sha256": file_hash(image_path),
                "render_dpi": 300,
                "line_layout_method": layout_method,
                "detection_polygons": np.asarray(polygons).tolist(),
                "model_manifest_sha256": file_hash(config),
            }
            pages.append(page)
            atomic_json(
                output, f"reference-pages/{material['material_id']}-{number}.json", page
            )
            image.close()
            if stop:
                break
        document.close()
    return {
        "schema_version": "m3.v1",
        "scope": "reference_preparation_only",
        "pages": pages,
    }
