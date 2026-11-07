"""Deterministic fixed-layout assembly; no model supplies source fields."""

import re

from app.module3.contracts import ProcessingError
from app.module3.document_reference import HEADING, paper_structure


def fail(code, message):
    raise ProcessingError(code, message)


def paper_options(pages):
    questions = {}
    listening = False
    listening_heading = False
    current = None
    for page in pages:
        if page["source_kind"] not in {"paper_text", "paper_scan"}:
            continue
        for line_index, line in enumerate(page["text"].splitlines()):
            if re.fullmatch(r"Part\s*II", line.strip(), re.I):
                listening_heading = True
            if listening_heading and re.search(
                r"Listening\s+Comprehension", line, re.I
            ):
                listening = True
            if re.search(r"Part\s+II\s+Listening", line, re.I):
                listening = True
            if re.search(r"Part\s+III", line, re.I):
                if listening:
                    return questions
            if not listening:
                continue
            if re.match(r"^(?:Section\b|Directions:|Questions\s*\d)", line, re.I):
                current = None
                continue
            match = re.match(r"^(\d+)\.\s*(?=A\))", line)
            if match:
                number = int(match[1])
                if number in questions:
                    fail("ASSEMBLY_DUPLICATE", "原卷题号重复")
                current = {
                    "question_no": number,
                    "options": {},
                    "source": {
                        "material_id": page["material_id"],
                        "page": page["page"],
                        "line_start": line_index,
                        "original_lines": [],
                    },
                }
                questions[number] = current
                line = line[match.end() :]
            markers = list(re.finditer(r"(?<!\w)([ABCD])\)\s*", line))
            if (
                current is not None
                and not markers
                and line.strip()
                and not line.strip().isdigit()
            ):
                fail(
                    "ASSEMBLY_LAYOUT_UNSUPPORTED", "选项出现未归属的续行，停止而非丢弃"
                )
            if current is None or not markers:
                continue
            current["source"]["original_lines"].append(line)
            for index, marker in enumerate(markers):
                letter = marker[1]
                text = line[
                    marker.end() : markers[index + 1].start()
                    if index + 1 < len(markers)
                    else len(line)
                ].strip()
                if letter in current["options"] or not text:
                    fail("ASSEMBLY_OPTION_CONFLICT", "选项缺失/重复，不能默认覆盖")
                current["options"][letter] = text
    return questions


def paper_answer_key(pages):
    """Independent textual KEYS table, when supplied inside the original paper."""
    result = {}
    for page in pages:
        if page["source_kind"] not in {"paper_text", "paper_scan"} or not re.search(
            r"^KEYS\s*$", page["text"], re.M | re.I
        ):
            continue
        active = False
        pending = None
        for line_index, line in enumerate(page["text"].splitlines()):
            if re.search(r"Part\s+II\s+Listening", line, re.I):
                active = True
                continue
            if active and re.search(r"Part\s+III", line, re.I):
                break
            if not active:
                continue
            if re.fullmatch(r"\d+(?:\s+\d+)*", line):
                if pending is not None:
                    fail("ASSEMBLY_KEY_INVALID", "答案表题号行没有配对答案")
                pending = [int(x) for x in line.split()]
                number_line = line
            elif re.fullmatch(r"[ABCD](?:\s+[ABCD])*", line):
                letters = line.split()
                if pending is None or len(letters) != len(pending):
                    fail("ASSEMBLY_KEY_INVALID", "答案表题号和答案列数不同")
                for column, (number, letter) in enumerate(
                    zip(pending, letters, strict=True)
                ):
                    if number in result:
                        fail("ASSEMBLY_KEY_INVALID", "答案表题号重复")
                    result[number] = {
                        "correct_option": letter,
                        "material_id": page["material_id"],
                        "locator": {
                            "page": page["page"],
                            "line": line_index,
                            "column": column,
                        },
                        "original_text": number_line + "\n" + line,
                    }
                pending = None
            elif line.strip():
                fail("ASSEMBLY_KEY_INVALID", "答案表中出现无法归属的文字")
        if pending is not None:
            fail("ASSEMBLY_KEY_INVALID", "答案表缺少配对答案行")
    return result


def answer_records(pages, structure):
    """Question headers anchor ownership; prose explicitly states answer letters.

    The printed answer frame alone is not interpreted as an answer. An explicit
    answer statement in the matching explanation is mandatory.
    """
    records = {}
    current = None
    mode = None
    group_index = -1
    for page in pages:
        if page["source_kind"] != "answer_explanation":
            continue
        for block in page["blocks"]:
            text = block["text"].strip()
            compact = re.sub(r"\s+", "", text)
            if re.fullmatch(r"Section\s*[ABC]?", text, re.I):
                continue
            if HEADING.match(text):
                group_index += 1
                mode, current = None, None
                continue
            if "听力原文" in compact:
                mode, current = "body", None
                continue
            if "答案详解" in compact:
                mode, current = "questions", None
                continue
            header = re.match(r"^(\d+)\s*[.．、]\s*([A-Za-z].*)", text)
            if header and mode == "questions":
                number = int(header[1])
                if not 0 <= group_index < len(structure["groups"]):
                    fail("ASSEMBLY_GROUP_INVALID", "解析题号缺少所属篇章")
                group = structure["groups"][group_index]
                if not group["start"] <= number <= group["end"] or number in records:
                    fail("ASSEMBLY_GROUP_INVALID", "解析题号重复或不属于当前篇章")
                current = {
                    "question_no": number,
                    "group_key": group["key"],
                    "blocks": [],
                    "explanation_blocks": [],
                }
                records[number] = current
            if current is None:
                continue
            if re.search(r"Part\s*III|Reading\s*Comprehension|选词填空", text, re.I):
                return finalize_answers(records)
            # Footers are identified by position and their explicit CET imprint.
            if re.search(r"(?:四级|CET[46])\s*202\d", text, re.I):
                continue
            source = {
                "material_id": page["material_id"],
                "sha256": page["sha256"],
                "page": page["page"],
                "box": block["box"],
                "block_index": block["block_index"],
                "original_text": text,
                "confidence": block["confidence"],
                "page_image_sha256": page["page_image_sha256"],
            }
            current["blocks"].append(source)
            if len(compact) <= 2 and block["box"][2] - block["box"][0] < 100:
                # Side labels/arrows of the printed 解析 decoration remain in raw
                # provenance but are not explanatory prose or answer letters.
                if compact.startswith("解"):
                    current["explanation_started"] = True
                continue
            if (
                "解析" in compact
                or compact.startswith("解")
                or current.get("explanation_started")
                or current["explanation_blocks"]
            ):
                # A question's translated A-D choices precede its explanation.
                current["explanation_blocks"].append(source)
    return finalize_answers(records)


def finalize_answers(records):
    patterns = (
        r"(?:故选(?:项)?|答案[为是])([ABCD])(?:项)?(?:[。；，,]|$)",
        r"(?:选项)?([ABCD])(?:项)?[^ABCD。；]{0,80}(?:为正确答案|为正确选项)",
    )
    for number, record in records.items():
        explanation = "\n".join(
            b["original_text"] for b in record["explanation_blocks"]
        )
        compact = re.sub(r"\s+", "", explanation)
        letters = {m[1].upper() for p in patterns for m in re.finditer(p, compact)}
        if len(letters) != 1 or not explanation.strip():
            fail("ASSEMBLY_ANSWER_UNRESOLVED", f"题{number}解析没有唯一明确的来源答案")
        if any(b["confidence"] < 0.85 for b in record["explanation_blocks"]):
            fail("ASSEMBLY_OCR_UNCERTAIN", f"题{number}解析OCR可信度不足")
        record.update(correct_option=letters.pop(), explanation_text=explanation)
    return records


def assemble(
    task, extracted, aligned, audio_meta, settings, *, reference_data, answer_extracted
):
    structure = paper_structure(extracted["pages"])
    options = paper_options(extracted["pages"])
    answers = answer_records(answer_extracted["pages"], structure)
    independent_keys = paper_answer_key(extracted["pages"])
    expected = list(range(1, structure["question_count"] + 1))
    if sorted(options) != expected or sorted(answers) != expected:
        fail("ASSEMBLY_INCOMPLETE", "选项/答案解析未完整覆盖独立原卷题量")
    if independent_keys and (
        sorted(independent_keys) != expected
        or any(
            independent_keys[n]["correct_option"] != answers[n]["correct_option"]
            for n in expected
        )
    ):
        fail("ASSEMBLY_ANSWER_CONFLICT", "原卷KEYS与扫描解析中的标准答案冲突")
    if task.request.get("expected_question_count") not in {None, len(expected)}:
        fail("ASSEMBLY_COUNT_CONFLICT", "题量与可信请求冲突")
    references = {r["segment_id"]: r for r in reference_data["segments"]}
    segments = {s["_src_id"]: s for s in aligned["segments"]}
    if len(references) != len(segments) or set(references) != set(segments):
        fail("ASSEMBLY_ALIGNMENT_CHANGED", "原文与对齐句子集合不一致")
    for sid, ref in references.items():
        s = segments[sid]
        if (
            s["text"] != ref["text"]
            or s["alignment_status"] != "aligned"
            or not (
                type(s["start_ms"]) is int
                and type(s["end_ms"]) is int
                and 0 <= s["start_ms"] < s["end_ms"] <= audio_meta["duration_ms"]
            )
        ):
            fail("ASSEMBLY_ALIGNMENT_CHANGED", "来源文字/有效对齐边界不一致")
    material_hashes = {
        p["material_id"]: p.get("sha256") for p in answer_extracted["pages"]
    }
    # pdfplumber pages originate from a source-hash-verified extraction manifest.
    material_hashes.update(extracted.get("material_sha256", {}))
    result = {
        "schema_version": "m3.v1",
        "exam_paper": task.request["exam_paper"],
        "audio": audio_meta,
        "content_groups": [
            {
                "_src_id": "group:1",
                "content_group_code": task.exam_paper_code + "_CG",
                "group_name": task.exam_paper_code,
                "exam_level_scope": task.request["exam_paper"]["exam_level"],
                "collector": "module3",
                "status": "启用",
            }
        ],
        "passages": [],
        "transcript_segments": [],
        "questions": [],
        "presentations": [],
        "language_items": [],
    }
    for i, group in enumerate(structure["groups"], 1):
        pid = f"passage:{i}"
        refs = [r for r in references.values() if r["passage_key"] == group["key"]]
        body = [r for r in refs if r["segment_type"] == "body"]
        question_refs = [r for r in refs if r["segment_type"] == "question"]
        if not body or sorted(r["question_no"] for r in question_refs) != list(
            range(group["start"], group["end"] + 1)
        ):
            fail("ASSEMBLY_GROUP_INVALID", "提问/正文篇章覆盖不完整")
        result["passages"].append(
            {
                "_src_id": pid,
                "passage_code": f"P{i:02}",
                "passage_index": i,
                "passage_type": group["section"],
                "start_ms": segments[body[0]["segment_id"]]["start_ms"],
                "body_end_ms": segments[body[-1]["segment_id"]]["end_ms"],
                "end_ms": max(segments[r["segment_id"]]["end_ms"] for r in refs),
                "collector": "module3",
            }
        )
        for index, ref in enumerate(refs, 1):
            s = segments[ref["segment_id"]]
            result["transcript_segments"].append(
                {
                    **{
                        k: s[k]
                        for k in (
                            "_src_id",
                            "text",
                            "start_ms",
                            "end_ms",
                            "alignment_status",
                        )
                    },
                    "passage_src_id": pid,
                    "segment_index": index,
                    "segment_type": ref["segment_type"],
                    "speaker": ref.get("speaker"),
                    "source_sha256": ref["source_sha256"],
                    "source_pages": ref["source_pages"],
                    "collector": "module3",
                }
            )
        for ref in question_refs:
            n = ref["question_no"]
            option, answer = options[n], answers[n]
            if (
                set(option["options"]) != set("ABCD")
                or answer["group_key"] != group["key"]
            ):
                fail("ASSEMBLY_OPTION_CONFLICT", "选项不完整或解析跨篇")
            paper_source = {
                **option["source"],
                "sha256": material_hashes.get(
                    str(option["source"]["material_id"]),
                    material_hashes.get(option["source"]["material_id"]),
                ),
            }
            if not paper_source["sha256"]:
                fail("ASSEMBLY_SOURCE_MISSING", "选项缺少原件哈希")
            result["questions"].append(
                {
                    "_src_id": f"q:{n}",
                    "question_code": f"Q{n:02}",
                    "question_index": n,
                    "passage_src_id": pid,
                    "question_segment_src_id": ref["segment_id"],
                    "question_text": ref["text"],
                    **{"option_" + k.lower(): v for k, v in option["options"].items()},
                    "correct_option": answer["correct_option"],
                    "explanation_text": answer["explanation_text"],
                    "explanation_source": (
                        f"material:{answer['blocks'][0]['material_id']} pages:"
                    )
                    + ",".join(
                        str(p)
                        for p in sorted(
                            {b["page"] for b in answer["explanation_blocks"]}
                        )
                    ),
                    "source_refs": [
                        {
                            "material_id": paper_source["material_id"],
                            "sha256": paper_source["sha256"],
                            "locator": {
                                "page": paper_source["page"],
                                "line_start": paper_source["line_start"],
                            },
                            "original_text": "\n".join(paper_source["original_lines"]),
                        },
                        *[
                            {
                                "material_id": b["material_id"],
                                "sha256": b["sha256"],
                                "locator": {
                                    "page": b["page"],
                                    "box": b["box"],
                                    "block_index": b["block_index"],
                                },
                                "original_text": b["original_text"],
                                "confidence": b["confidence"],
                            }
                            for b in answer["blocks"]
                        ],
                    ],
                    "collector": "module3",
                }
            )
            result["presentations"].append(
                {
                    "_src_id": f"pr:{n}",
                    "question_src_id": f"q:{n}",
                    "question_no": n,
                    "option_mapping_state": "已知",
                    "mapping_source": "同一原卷A-D原序提取；未跨卷重排",
                    "option_letter_mapping": dict(zip("ABCD", "ABCD", strict=True)),
                    "collector": "module3",
                }
            )
            if n in independent_keys:
                key = independent_keys[n]
                result["questions"][-1]["source_refs"].append(
                    {
                        **key,
                        "sha256": paper_source["sha256"],
                        "role": "independent_answer_key",
                    }
                )
    result["assembly_audit"] = {
        "method": "m3.source-assembly.v1",
        "question_count": len(expected),
        "structure": structure,
        "source_fields_from_llm": False,
        "independent_paper_key_agreement": len(independent_keys),
        "issues": [],
    }
    return result
