"""Parse listening reference text from source document pages without a template."""

from __future__ import annotations

import re
from collections import Counter

from app.module3.contracts import ProcessingError
from app.module3.ocr_refinement import normalize_citations, strip_markers

HEADING = re.compile(
    r"^(News\s*Report|Conversation|Passage)\s*(One|Two|Three|Four|Five|\d+)\s*$", re.I
)


def paper_structure(pages):
    paper_pages = [p for p in pages if p["source_kind"] in {"paper_text", "paper_scan"}]
    text = "\n".join(
        p["text"] for p in pages if p["source_kind"] in {"paper_text", "paper_scan"}
    )
    text = re.sub(r"\s+", "", text)
    match = re.search(r"PartIIListeningComprehension", text, re.I)
    if not match:
        raise ProcessingError("REFERENCE_LAYOUT_UNSUPPORTED", "未定位原卷听力部分")
    section_start = match.end()
    text = re.split(r"PartIII", text[section_start:], maxsplit=1, flags=re.I)[0]
    pattern = (
        r"Questions(\d+)(and|to|[-–])(\d+)"
        r"arebasedonthe(newsreport|conversation|passage)"
    )
    groups = []
    counters = Counter()
    for item in re.finditer(pattern, text, re.I):
        start, end = int(item[1]), int(item[3])
        kind = re.sub(r"\s+", "", item[4].lower()).replace("newsreport", "news")
        counters[kind] += 1
        position = 0
        source_page = None
        for page in paper_pages:
            size = len(re.sub(r"\s+", "", page["text"]))
            if position <= section_start + item.start() < position + size:
                source_page = page
                break
            position += size
        if source_page is None:
            raise ProcessingError(
                "REFERENCE_COUNT_SOURCE_INVALID", "无法回查原卷题组页码"
            )
        groups.append(
            {
                "key": f"{kind}{counters[kind]}",
                "section": kind,
                "start": start,
                "end": end,
                "source_page": source_page["page"],
                "source_material_id": source_page["material_id"],
            }
        )
    numbers = [n for group in groups for n in range(group["start"], group["end"] + 1)]
    if not numbers or numbers != list(range(1, max(numbers) + 1)):
        raise ProcessingError(
            "REFERENCE_QUESTION_RANGES_INVALID", "原卷题组不连续或重复"
        )
    return {
        "question_count": len(numbers),
        "groups": groups,
        "source": "original_paper_question_headings",
    }


def source_lines(pages):
    for page in pages:
        if page["source_kind"] not in {"answer_explanation", "transcript"}:
            continue
        blocks = page.get("reference_blocks", page.get("blocks"))
        if blocks:
            for block in blocks:
                yield (
                    page,
                    normalize_citations(block["text"], block.get("raw_text", "")),
                )
        else:
            for line in page["text"].splitlines():
                yield page, line


def parse_groups(pages, structure, materials):
    groups = []
    current = None
    mode = None
    for page, original in source_lines(pages):
        text = original.strip()
        heading = HEADING.match(text)
        if heading:
            if len(groups) >= len(structure["groups"]):
                break
            expected = structure["groups"][len(groups)]
            kind = re.sub(r"\s+", "", heading[1].lower()).replace("newsreport", "news")
            if kind != expected["section"]:
                raise ProcessingError(
                    "REFERENCE_GROUP_ORDER_INVALID", "答案原文与原卷题组类型不一致"
                )
            material = next(
                m for m in materials if m["material_id"] == page["material_id"]
            )
            current = {
                **expected,
                "parts": [],
                "questions": [],
                "source_storage_key": material["storage_key"],
                "source_sha256": material["sha256"],
            }
            groups.append(current)
            mode = None
            continue
        compact = re.sub(r"\s+", "", text)
        if "听力原文" in compact or compact.lower() in {
            "transcript",
            "listeningscript",
        }:
            if current is None:
                raise ProcessingError(
                    "REFERENCE_LAYOUT_UNSUPPORTED", "原文标记缺少所属篇章"
                )
            mode = "body"
            continue
        if "答案详解" in compact:
            mode = "questions"
            continue
        if current is None:
            continue
        if mode == "body":
            if not re.search(r"[A-Za-z]", text) or re.search(r"[\u4e00-\u9fff]", text):
                continue
            # Page footers are not part of spoken text.
            if re.match(r"^\d*\s*(CET[46]|20\d\d)", text, re.I):
                continue
            speaker = re.match(r"^([MW])\s*[:：]\s*", text)
            content = strip_markers(text[speaker.end() :] if speaker else text)
            if not current["parts"] or speaker:
                current["parts"].append(
                    {
                        "text": content,
                        "speaker": speaker[1] if speaker else None,
                        "pages": [page["page"]],
                    }
                )
            else:
                part = current["parts"][-1]
                part["text"] += " " + content
                if page["page"] not in part["pages"]:
                    part["pages"].append(page["page"])
        elif mode == "questions":
            question = re.match(r"^(\d+)\s*[.．]\s*([A-Za-z].*)", text)
            if not question:
                continue
            number = int(question[1])
            if not current["start"] <= number <= current["end"]:
                continue
            content = (
                re.split(r"[\u4e00-\u9fff]", question[2], maxsplit=1)[0]
                .strip()
                .replace("？", "?")
            )
            if not content.endswith("?"):
                raise ProcessingError(
                    "REFERENCE_QUESTION_TRUNCATED", "提问原文缺少完整问句"
                )
            current["questions"].append(
                {"question_no": number, "text": content, "pages": [page["page"]]}
            )
    if len(groups) != len(structure["groups"]) or any(
        not group["parts"] for group in groups
    ):
        raise ProcessingError("REFERENCE_GROUPS_INCOMPLETE", "答案正文题组提取不完整")
    numbers = [q["question_no"] for group in groups for q in group["questions"]]
    if sorted(numbers) != list(range(1, structure["question_count"] + 1)):
        raise ProcessingError("REFERENCE_QUESTIONS_INCOMPLETE", "提问原文缺失或重复")
    return groups


def split_groups(groups, nltk_data):
    from nltk import data

    if str(nltk_data) not in data.path:
        data.path.insert(0, str(nltk_data))
    splitter = data.load("tokenizers/punkt_tab/english.pickle")
    splitter._params.abbrev_types.update({"u.s", "no"})
    rows = []
    for group in groups:
        number = 0
        for part in group["parts"]:
            text = part["text"]
            for sentence in splitter.tokenize(text):
                number += 1
                rows.append(
                    {
                        "segment_id": f"{group['key']}:s{number:03}",
                        "text": sentence.strip(),
                        "segment_type": "body",
                        "passage_key": group["key"],
                        "speaker": part["speaker"],
                        "question_no": None,
                        "source_storage_key": group["source_storage_key"],
                        "source_sha256": group["source_sha256"],
                        "source_pages": part["pages"],
                    }
                )
        for question in group["questions"]:
            rows.append(
                {
                    "segment_id": f"q:{question['question_no']}",
                    "text": question["text"],
                    "segment_type": "question",
                    "passage_key": group["key"],
                    "speaker": None,
                    "question_no": question["question_no"],
                    "source_storage_key": group["source_storage_key"],
                    "source_sha256": group["source_sha256"],
                    "source_pages": question["pages"],
                }
            )
    return rows


def restore_word_gaps(text, vocabulary):
    """Insert spacing only; no vocabulary token may add/delete a source letter."""

    def split(match):
        word = match[0]
        lower = word.lower()
        if lower in vocabulary or len(word) < 5:
            return word
        camel = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", word)
        if camel != word:
            return " ".join(
                re.sub(r"[A-Za-z]+", split, piece) for piece in camel.split()
            )
        if word[0].isupper() and not any(
            word.startswith(prefix)
            for prefix in (
                "He",
                "She",
                "The",
                "They",
                "This",
                "That",
                "It",
                "We",
                "But",
                "In",
                "Of",
                "To",
                "And",
            )
        ):
            return word
        best = {0: (0.0, [])}
        for end in range(1, len(word) + 1):
            for start in range(max(0, end - 24), end):
                piece = lower[start:end]
                if (
                    start not in best
                    or piece not in vocabulary
                    or (len(piece) == 1 and piece not in {"a", "i"})
                ):
                    continue
                score, parts = best[start]
                candidate = score + len(piece) ** 1.6 - 3
                if len(parts) < 6 and (end not in best or candidate > best[end][0]):
                    best[end] = (candidate, [*parts, word[start:end]])
        if len(word) in best and len(best[len(word)][1]) > 1:
            return " ".join(best[len(word)][1])
        return word

    return re.sub(r"[A-Za-z]+", split, text)
