"""Recover printed English spacing with image-derived word crops, not ASR text."""

from __future__ import annotations

import difflib
import re
from collections import Counter

from app.module3.contracts import ProcessingError


def strip_markers(text):
    text = re.sub(r"[\[【]\s*\d{1,3}\s*[\]】Il|]", "", text)
    text = re.sub(r"\[\s*\d{1,3}(?=[A-Z])", "", text)
    return re.sub(r"\[\s*\]", "", text)


def normalize_citations(text, evidence):
    """Resolve bracket/I ambiguity only for citations seen in another source read."""
    for number in re.findall(r"\[\s*(\d{1,3})", evidence):
        text = re.sub(
            rf"(?<![A-Za-z0-9])[Il|]\s*{number}\s*[Il|](?=\s*(?:[A-Z]|$))",
            "",
            text,
        )
    return text


def reconcile_line(original, words):
    """Combine source-image readings; retain printed character/spacing evidence."""
    left = re.sub(r"\s+", "", strip_markers(original))
    joined = normalize_citations(" ".join(words), original)
    right = re.sub(r"\s+", "", strip_markers(joined))

    def normalized(value):
        return value.replace("’", "'").replace("“", '"').replace("”", '"')

    left, right = normalized(left), normalized(right)
    merged = []
    for tag, i, j, a, b in difflib.SequenceMatcher(
        None, left, right, autojunk=False
    ).get_opcodes():
        old, new = left[i:j], right[a:b]
        if tag == "equal":
            merged.append(old)
        elif tag == "insert":
            merged.append(new)
        elif tag == "delete":
            merged.append(old)
        else:
            # Preserve the reading with more visible characters for common OCR
            # omissions (rn/m, silent letters, doubled letters). Other changes
            # use the shorter image crop's recognition, retaining both readings.
            merged.append(old if len(old) > len(new) else new)
    result = "".join(merged)
    boundaries = set()
    for source in [strip_markers(original), strip_markers(joined)]:
        source = normalized(source)
        compact = re.sub(r"\s+", "", source)
        position = 0
        splits = set()
        for token in re.findall(r"\S+|\s+", source):
            if token.isspace():
                splits.add(position)
            else:
                position += len(token)
        for match in difflib.SequenceMatcher(
            None, compact, result, autojunk=False
        ).get_matching_blocks():
            for split in splits:
                if match.a <= split <= match.a + match.size:
                    boundaries.add(match.b + split - match.a)
    result = "".join(
        (" " if i in boundaries and i else "") + c for i, c in enumerate(result)
    )
    result = re.sub(r"(?<=\d)\s+(?=\d)", "", result)
    result = re.sub(r"\s+([.,?!;:])", r"\1", result)
    result = re.sub(r"(?<=[a-z0-9])([.!?])(?=[A-Z])", r"\1 ", result)
    result = re.sub(r"\b([A-Z])\.\s+(?=[A-Z]\.)", r"\1.", result)
    return re.sub(r"\s+", " ", result).strip()


def word_spans(image):
    import numpy as np

    black = np.asarray(image.convert("L")) < 180
    columns = black.sum(0) > max(1, black.shape[0] * 0.03)
    occupied = np.flatnonzero(columns)
    if not occupied.size:
        return []
    ink_rows = np.flatnonzero(black.sum(1) > 1)
    threshold = max(4, round((ink_rows[-1] - ink_rows[0] + 1) * 0.12))
    spans = []
    start = previous = int(occupied[0])
    for value in occupied[1:]:
        column = int(value)
        if column - previous - 1 >= threshold:
            spans.append((start, previous + 1))
            start = column
        previous = column
    spans.append((start, previous + 1))
    return spans


def clean_printed_crop(image):
    """Remove only long horizontal rules in a derived OCR input image."""
    import cv2
    import numpy as np
    from PIL import Image

    pixels = np.asarray(image.convert("RGB")).copy()
    binary = (cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY) < 210).astype("uint8")
    width = max(30, image.height * 2)
    lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((1, width), dtype="uint8"))
    lines = cv2.dilate(lines, np.ones((2, 1), dtype="uint8"))
    pixels[lines > 0] = 255
    return Image.fromarray(pixels)


def recognize_printed(recognizer, image):
    """Use CTC character columns plus printed gaps to restore omitted spaces."""
    import json

    import numpy as np

    result = next(
        iter(recognizer.predict(np.asarray(image), return_word_box=True))
    ).json
    if isinstance(result, str):
        result = json.loads(result)
    result = result.get("res", result)
    reading = result["rec_text"]
    if not isinstance(reading, (tuple, list)):
        return result
    text, info = reading
    frame_count, groups, columns, _ = info
    spans = word_spans(image)
    characters = [
        (char, column)
        for group, cols in zip(groups, columns, strict=True)
        for char, column in zip(group, cols, strict=True)
    ]
    output = []
    previous = None
    for char, column in characters:
        if char.isspace():
            output.append(char)
            continue
        x = (column + 0.5) / frame_count * image.width
        bucket = (
            min(
                range(len(spans)),
                key=lambda i: max(spans[i][0] - x, x - spans[i][1], 0),
            )
            if spans
            else 0
        )
        if previous is not None and bucket != previous:
            output.append(" ")
        output.append(char)
        previous = bucket
    spaced = re.sub(r"\s+", " ", "".join(output)).strip()
    spaced = re.sub(r"\b([A-Z])\.\s+(?=[A-Z]\.)", r"\1.", spaced)
    spaced = re.sub(r"(?<=\d)\s+(?=\d)", "", spaced)
    result.update(
        rec_text=spaced,
        raw_text=text,
        character_columns=info,
        spacing_method="ctc_columns_and_printed_gaps_v1",
    )
    return result


def verify_question_number(prefix, text, crop, recognizer):
    """Resolve numeric OCR disagreement from an independent printed crop."""
    from PIL import ImageOps

    def number(reading):
        match = re.match(r"^\s*(\d{1,3})(?:\s*[.．]|\s*(?=[A-Za-z])|\s*$)", reading)
        return int(match[1]) if match else None

    readings = [prefix, text]
    votes = [number(reading) for reading in readings]
    if votes[0] is None or votes[0] != votes[1]:
        spans = word_spans(crop)
        if spans:
            # Keep a little following text: thin leading digits can be separate
            # pixel spans, and a digit-only crop can drop the second digit.
            left, right = spans[0][0], spans[min(2, len(spans) - 1)][1]
            tile = ImageOps.expand(
                crop.crop(
                    (max(0, left - 3), 0, min(crop.width, right + 3), crop.height)
                ),
                border=(12, 5),
                fill="white",
            )
            value = recognize_printed(recognizer, tile)
            readings.append(value.get("raw_text", value["rec_text"]))
            votes.append(number(readings[-1]))
            tile.close()
    counts = Counter(value for value in votes if value is not None)
    if not counts or counts.most_common(1)[0][1] < 2:
        raise ProcessingError("REFERENCE_NUMBER_AMBIGUOUS", "提问题号的独立识别不一致")
    selected = counts.most_common(1)[0][0]
    replaced = re.sub(r"^\s*\d{1,3}\s*[.．]?\s*", f"{selected}. ", text, count=1)
    if number(replaced) != selected:
        # A long recognition strip can omit its leading number while both
        # independent short image reads retain it. Number is a separate source
        # field; preserve the recognized question words without guessing them.
        stem = re.sub(r"^\s*[A-Za-z0-9|]{0,3}\s*[.．]\s*", "", text, count=1).strip()
        if not re.match(r"[A-Za-z]", stem):
            raise ProcessingError("REFERENCE_NUMBER_AMBIGUOUS", "提问原文不完整")
        replaced = f"{selected}. {stem}"
    return replaced, readings


def refine_blocks(image, blocks, recognizer):
    import numpy as np
    from PIL import ImageOps

    refined = []
    for index, block in enumerate(blocks):
        x1, y1, x2, y2 = [int(value) for value in block["box"]]
        crop = clean_printed_crop(
            image.crop(
                (
                    max(0, x1 - 3),
                    max(0, y1 - 3),
                    min(image.width, x2 + 3),
                    min(image.height, y2 + 3),
                )
            )
        )
        pieces = []
        spans = word_spans(crop)
        fragments = [
            (spans[i][0], spans[min(i + 3, len(spans) - 1)][1])
            for i in range(0, len(spans), 4)
        ]
        for start, end in fragments:
            tile = crop.crop(
                (max(0, start - 2), 0, min(crop.width, end + 2), crop.height)
            )
            tile = ImageOps.expand(tile, border=(8, 3), fill="white")
            value = recognize_printed(recognizer, tile)
            text = value.get("rec_text", "")
            if re.search(r"\d", text) or float(value.get("rec_score", 0)) < 0.92:
                individual = []
                for a, b in spans:
                    if a < start or b > end:
                        continue
                    small = crop.crop(
                        (max(0, a - 2), 0, min(crop.width, b + 2), crop.height)
                    )
                    small = ImageOps.expand(small, border=(8, 3), fill="white")
                    reading = next(iter(recognizer.predict(np.asarray(small)))).json
                    if isinstance(reading, str):
                        import json

                        reading = json.loads(reading)
                    individual.append(reading.get("res", reading).get("rec_text", ""))
                text = reconcile_line(text, individual)
            pieces.append(
                {
                    "text": text,
                    "score": float(value.get("rec_score", 0)),
                    "x_span": [start, end],
                }
            )
            if re.search(r"[\u4e00-\u9fff]", text):
                break
        refined.append(
            {
                **block,
                "raw_text": block["text"],
                "text": reconcile_line(block["text"], [p["text"] for p in pieces]),
                "word_readings": pieces,
                "refinement": "printed_word_projection_v1",
                "crop_preprocessing": "horizontal_rule_removal_v1",
            }
        )
        crop.close()
        print(f"reference OCR line {index + 1}/{len(blocks)}", flush=True)
    return refined
