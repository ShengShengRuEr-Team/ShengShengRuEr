"""Best-effort drafts. Missing source fields never become invented answers."""

import copy
import json
import re
from pathlib import Path

from sqlalchemy import select

from app.db import models_processing as m
from app.module3 import source_assembly as strict
from app.module3.contracts import (
    ProcessingError,
    controlled_path,
    file_hash,
    fingerprint,
)
from app.module3.document_reference import HEADING
from app.services.processing import tasks

VERSION = "console.partial-draft.v1"


def stamp_task(task, db):
    materials = tasks.task_materials(db, task.id)
    method = {
        **task.method,
        "console_partial_draft": {
            "version": VERSION,
            "implementation_sha256": file_hash(Path(__file__)),
        },
    }
    task.method = method
    task.method_hash = fingerprint(method)
    task.input_hash = fingerprint(
        {
            "request": {
                k: v
                for k, v in task.request.items()
                if k not in {"material_ids", "retry_reason"}
            },
            "materials": sorted((s.source_kind, s.sha256) for s in materials),
            "method": method,
        }
    )


def pending_source(q):
    missing = [
        k
        for k in [
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "explanation_text",
        ]
        if not str(q.get(k) or "").strip()
    ]
    if not isinstance(q.get("correct_option"), str) or q.get("correct_option") not in {
        "A",
        "B",
        "C",
        "D",
    }:
        missing.append("correct_option")
    return missing


def pending_question(q, payload, phase):
    if pending_source(q):
        return True
    return phase in {"annotate_sample", "annotate"} and not any(
        r.get("question_src_id") == q["_src_id"] and r.get("role") == "PRIMARY"
        for r in payload.get("skill_question_relations", [])
    )


def pending_report(payload, phase="assemble"):
    qs = (
        payload["questions"][:5] if phase == "annotate_sample" else payload["questions"]
    )
    return [
        {
            "question_src_id": q["_src_id"],
            "question_index": q["question_index"],
            "fields": pending_source(q),
            "annotation_pending": phase in {"annotate_sample", "annotate"}
            and pending_question(q, payload, phase),
        }
        for q in qs
        if pending_question(q, payload, phase)
    ]


def source_block(page, b):
    return {
        "material_id": page["material_id"],
        "sha256": page["sha256"],
        "page": page["page"],
        "box": b["box"],
        "block_index": b["block_index"],
        "original_text": b["text"],
        "confidence": b["confidence"],
        "page_image_sha256": page["page_image_sha256"],
    }


def collect_answers(pages, structure):
    records = {}
    current = None
    mode = None
    group = -1
    for page in pages:
        if page["source_kind"] != "answer_explanation":
            continue
        for b in page.get("blocks", []):
            text = b["text"].strip()
            compact = re.sub(r"\s+", "", text)
            if HEADING.match(text):
                group += 1
                current = None
                mode = None
                continue
            if "听力原文" in compact:
                mode = "body"
                current = None
                continue
            if "答案详解" in compact:
                mode = "questions"
                current = None
                continue
            header = re.match(r"^(\d+)\s*[.．、]\s*([A-Za-z].*)", text)
            if header and mode == "questions":
                number = int(header[1])
                if (
                    0 <= group < len(structure["groups"])
                    and structure["groups"][group]["start"]
                    <= number
                    <= structure["groups"][group]["end"]
                ):
                    if number in records:
                        records[number]["ambiguous"] = True
                        current = None
                        continue
                    current = {
                        "question_no": number,
                        "group_key": structure["groups"][group]["key"],
                        "blocks": [],
                        "explanation_blocks": [],
                        "options": set(),
                        "started": False,
                    }
                    records[number] = current
                else:
                    current = None
            if not current:
                continue
            if re.search(r"Part\s*III|Reading\s*Comprehension|选词填空", text, re.I):
                current = None
                mode = None
                continue
            if re.search(r"(?:四级|CET[46])\s*202\d", text, re.I) or re.fullmatch(
                r"Section\s*[ABC]?", text, re.I
            ):
                continue
            src = source_block(page, b)
            current["blocks"].append(src)
            if header:
                continue
            choice = re.match(r"^([ABCD])\s*[)）]", compact)
            if choice and not current["started"]:
                current["options"].add(choice[1])
                continue
            # Keep ownership across page turns; 析 is a split 解析 label.
            marker = compact.startswith(("解", "析")) or "解析" in compact
            if marker:
                current["started"] = True
            if len(compact) <= 2:
                continue
            if current["started"] or (
                len(current["options"]) == 4 and re.search(r"[\u4e00-\u9fff]", text)
            ):
                current["started"] = True
                current["explanation_blocks"].append(src)
    patterns = (
        r"(?:故选(?:项)?|答案[为是])([ABCD])(?:项)?(?:[。；，,]|$)",
        r"(?:选项)?([ABCD])(?:项)?[^ABCD。；]{0,80}(?:为正确答案|为正确选项)",
    )
    for record in records.values():
        explanation = "\n".join(
            b["original_text"] for b in record["explanation_blocks"]
        )
        compact = re.sub(r"\s+", "", explanation)
        letters = {m[1] for p in patterns for m in re.finditer(p, compact)}
        record.update(
            explanation_text=explanation or None,
            correct_option=next(iter(letters))
            if len(letters) == 1 and not record.get("ambiguous")
            else None,
            answer_candidates=sorted(letters),
        )
    return records


def collect_options(pages):
    result = {}
    active = False
    heading = False
    current = None
    for page in pages:
        if page["source_kind"] not in {"paper_text", "paper_scan"}:
            continue
        for index, line in enumerate(page["text"].splitlines()):
            if re.fullmatch(r"Part\s*II", line.strip(), re.I):
                heading = True
            if (
                heading and re.search("Listening\\s+Comprehension", line, re.I)
            ) or re.search(r"Part\s+II\s+Listening", line, re.I):
                active = True
            if re.search(r"Part\s+III", line, re.I) and active:
                return result
            if not active:
                continue
            if re.match(r"^(?:Section\b|Directions:|Questions\s*\d)", line, re.I):
                current = None
                continue
            match = re.match(r"^(\d+)\.\s*(?=A\))", line)
            if match:
                current = {
                    "options": {},
                    "source": {
                        "material_id": page["material_id"],
                        "page": page["page"],
                        "line_start": index,
                        "original_lines": [],
                    },
                }
                number = int(match[1])
                if number in result:
                    current["ambiguous"] = True
                result[number] = current
                line = line[match.end() :]
            marks = list(re.finditer(r"(?<!\w)([ABCD])\)\s*", line))
            if current and marks:
                current["source"]["original_lines"].append(line)
                for i, mark in enumerate(marks):
                    value = line[
                        mark.end() : marks[i + 1].start()
                        if i + 1 < len(marks)
                        else len(line)
                    ].strip()
                    if mark[1] in current["options"]:
                        current["ambiguous"] = True
                    current["options"][mark[1]] = value or None
            elif current and line.strip():
                current["ambiguous"] = True
    return result


def assemble(
    task, extracted, aligned, audio_meta, settings, *, reference_data, answer_extracted
):
    structure = reference_data.get(
        "trusted_question_structure"
    ) or strict.paper_structure(extracted["pages"])
    if not structure.get("question_count"):
        raise ProcessingError(
            "ASSEMBLY_STRUCTURE_MISSING", "无法确定原卷题号，不能猜造整套结构"
        )
    options = collect_options(extracted["pages"])
    answers = collect_answers(answer_extracted["pages"], structure)
    try:
        keys = strict.paper_answer_key(extracted["pages"])
    except ProcessingError:
        keys = {}
    hashes = {str(s["material_id"]): s.get("sha256") for s in answer_extracted["pages"]}
    hashes.update(extracted.get("material_sha256", {}))
    refs = reference_data["segments"]
    aligned_by_id = {s["_src_id"]: s for s in aligned["segments"]}
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
        **{
            name: []
            for name in [
                "passages",
                "transcript_segments",
                "questions",
                "presentations",
                "language_items",
                "evidences",
                "skill_question_relations",
                "error_question_relations",
                "other_relations",
            ]
        },
    }
    warnings = []
    for i, group in enumerate(structure["groups"], 1):
        pid = f"passage:{i}"
        group_refs = [s for s in refs if s["passage_key"] == group["key"]]
        body = [s for s in group_refs if s["segment_type"] == "body"]
        aligned_rows = [
            aligned_by_id[s["segment_id"]]
            for s in group_refs
            if s["segment_id"] in aligned_by_id
        ]
        body_rows = [
            aligned_by_id[s["segment_id"]]
            for s in body
            if s["segment_id"] in aligned_by_id
        ]
        result["passages"].append(
            {
                "_src_id": pid,
                "passage_code": f"P{i:02}",
                "passage_index": i,
                "passage_type": group["section"],
                "start_ms": body_rows[0].get("start_ms") if body_rows else None,
                "body_end_ms": body_rows[-1].get("end_ms") if body_rows else None,
                "end_ms": max((s.get("end_ms") or 0 for s in aligned_rows), default=0),
                "collector": "module3",
            }
        )
        for index, ref in enumerate(group_refs, 1):
            s = aligned_by_id.get(ref["segment_id"], {})
            result["transcript_segments"].append(
                {
                    "_src_id": ref["segment_id"],
                    "text": ref["text"],
                    "start_ms": s.get("start_ms"),
                    "end_ms": s.get("end_ms"),
                    "alignment_status": s.get("alignment_status", "requires_review"),
                    "passage_src_id": pid,
                    "segment_index": index,
                    "segment_type": ref["segment_type"],
                    "speaker": ref.get("speaker"),
                    "source_sha256": ref["source_sha256"],
                    "source_pages": ref["source_pages"],
                    "collector": "module3",
                }
            )
        for number in range(group["start"], group["end"] + 1):
            ref = next((r for r in group_refs if r.get("question_no") == number), None)
            option = options.get(number, {})
            answer = answers.get(number, {})
            letter = answer.get("correct_option")
            key = keys.get(number)
            if key and letter and letter != key["correct_option"]:
                warnings.append(
                    {
                        "question_index": number,
                        "field": "correct_option",
                        "message": "原卷答案表与解析冲突，保留空值待补",
                    }
                )
                letter = None
            elif key and not letter and not answer.get("answer_candidates"):
                letter = key["correct_option"]
            if answer.get("group_key") not in {None, group["key"]} or answer.get(
                "ambiguous"
            ):
                letter = None
            source_refs = copy.deepcopy(answer.get("blocks", []))
            if option.get("source"):
                src = option["source"]
                source_refs.insert(
                    0,
                    {
                        "material_id": src["material_id"],
                        "sha256": hashes.get(str(src["material_id"])),
                        "locator": {
                            "page": src["page"],
                            "line_start": src["line_start"],
                        },
                        "original_text": "\n".join(src["original_lines"]),
                    },
                )
            if key:
                source_refs.append(
                    {
                        **key,
                        "sha256": hashes.get(str(key["material_id"])),
                        "role": "independent_answer_key",
                    }
                )
            q = {
                "_src_id": f"q:{number}",
                "question_code": f"Q{number:02}",
                "question_index": number,
                "passage_src_id": pid,
                "question_segment_src_id": ref["segment_id"] if ref else None,
                "question_text": ref["text"] if ref else None,
                **{
                    "option_" + k.lower(): None
                    if option.get("ambiguous")
                    else option.get("options", {}).get(k)
                    for k in "ABCD"
                },
                "correct_option": letter,
                "explanation_text": answer.get("explanation_text"),
                "explanation_source": "pages:"
                + ",".join(
                    str(p)
                    for p in sorted(
                        {b["page"] for b in answer.get("explanation_blocks", [])}
                    )
                ),
                "source_refs": source_refs,
                "collector": "module3",
            }
            if not q["explanation_text"]:
                warnings.append(
                    {
                        "question_index": number,
                        "field": "explanation_text",
                        "message": "解析未提取，先保留本题待补",
                    }
                )
            for field in pending_source(q):
                warnings.append(
                    {
                        "question_index": number,
                        "field": field,
                        "message": "未取得可靠来源字段，留空继续生成草稿",
                    }
                )
            if any(
                b["confidence"] < 0.85 for b in answer.get("explanation_blocks", [])
            ):
                warnings.append(
                    {
                        "question_index": number,
                        "field": "explanation_text",
                        "message": "部分解析OCR可信度偏低，请生成后核对原件",
                    }
                )
            result["questions"].append(q)
            result["presentations"].append(
                {
                    "_src_id": f"pr:{number}",
                    "question_src_id": q["_src_id"],
                    "question_no": number,
                    "option_mapping_state": "已知",
                    "mapping_source": "同一原卷A-D原序提取",
                    "option_letter_mapping": dict(zip("ABCD", "ABCD", strict=True)),
                    "collector": "module3",
                }
            )
    result["assembly_audit"] = {
        "method": VERSION,
        "implementation_sha256": file_hash(Path(__file__)),
        "question_count": structure["question_count"],
        "structure": structure,
        "source_fields_from_llm": False,
        "independent_paper_key_agreement": sum(
            q["correct_option"]
            == keys.get(q["question_index"], {}).get("correct_option")
            for q in result["questions"]
        ),
        "issues": warnings,
        "draft_first": True,
    }
    return result


def load_candidates(task, result, settings):
    from app.db.base import SessionLocal
    from app.module3.annotation_checks import check_candidate

    found = {}
    bindings = [
        ("reuse_annotation_task_id", "sample_review"),
        ("reuse_full_annotation_task_id", "annotation_review"),
    ]
    if task.request.get("retry_reason") and task.parent_task_id:
        bindings.append(("_retry_source", "_retry_review"))
    for key, reviewkey in bindings:
        is_retry = key == "_retry_source"
        source_id = str(task.parent_task_id) if is_retry else task.request.get(key)
        review = task.request.get(reviewkey) or {}
        if not source_id:
            continue
        with SessionLocal() as db:
            source = tasks.get_task(db, source_id)
            draft = tasks.get_draft(db, source)
            if not draft or (
                not is_retry and review.get("result_hash") != draft.result_hash
            ):
                raise ProcessingError(
                    "ANNOTATION_REVIEW_CHANGED", "复核与来源版本不一致"
                )
            if is_retry and source.input_hash != task.input_hash:
                raise ProcessingError("ANNOTATION_SOURCE_CHANGED", "重试输入版本不一致")
            current_questions = {q["_src_id"]: q for q in result["questions"]}
            if any(
                current_questions[q["_src_id"]] != q for q in draft.payload["questions"]
            ):
                raise ProcessingError("ANNOTATION_SOURCE_CHANGED", "标注来源字段已变化")
            approved = (
                set(current_questions)
                if is_retry
                else {
                    i["question_src_id"]
                    for i in review.get("items", [])
                    if i["decision"] == "approved"
                }
            )
            rows = list(
                db.scalars(
                    select(m.ProcessingArtifact)
                    .where(
                        m.ProcessingArtifact.task_id == source.id,
                        m.ProcessingArtifact.stage == "annotate",
                    )
                    .order_by(m.ProcessingArtifact.id)
                )
            )
            for row in rows:
                path = controlled_path(
                    settings.m3_path("m3_artifacts_dir"), row.storage_key
                )
                if file_hash(path) != row.artifact_hash:
                    raise ProcessingError(
                        "ANNOTATION_SOURCE_CHANGED", "标注来源产物校验失败"
                    )
                data = json.loads(path.read_text(encoding="utf-8"))
                qid = data.get("question_src_id")
                if qid in approved:
                    check_candidate(result, current_questions[qid], data["candidate"])
                    found[qid] = data
    return found


def annotate_questions(task, token, result, settings, checkpoint):
    from pydantic import ValidationError

    from app.module3.annotation_checks import PROMPT_VERSION, check_candidate
    from app.module3.annotations import SYSTEM_PROMPT, annotation_input, merge_candidate
    from app.module3.llm import request_json

    qs = (
        result["questions"][:5]
        if task.request.get("stop_after") == "annotate_sample"
        else result["questions"]
    )
    reused = load_candidates(task, result, settings)
    run_key = fingerprint({"audio": result["audio"]["file_hash"]})
    skipped = []
    budget_block = None
    for q in qs:
        fields = pending_source(q)
        if fields or budget_block:
            skipped.append(
                {
                    "question_src_id": q["_src_id"],
                    "question_index": q["question_index"],
                    "fields": fields,
                    "reason": budget_block or "来源字段待补，暂不调用模型",
                }
            )
            checkpoint(task.id, token, "annotation_skipped", skipped[-1], settings)
            continue
        raw = None
        call = None
        error = None
        feedback = None
        for _attempt in range(3):
            try:
                if q["_src_id"] in reused:
                    prior = reused[q["_src_id"]]
                    raw = prior["candidate"]
                    call = {
                        **prior["call"],
                        "reused_from_task_id": task.request.get(
                            "reuse_full_annotation_task_id"
                        )
                        or task.request.get("reuse_annotation_task_id"),
                    }
                else:
                    data = annotation_input(result, q)
                    if feedback:
                        data["validation_feedback"] = feedback
                    review = task.request.get("annotation_review") or {}
                    semantic = next(
                        (
                            i
                            for i in review.get("items", [])
                            if i["question_src_id"] == q["_src_id"]
                            and i["decision"] == "changes_required"
                        ),
                        None,
                    )
                    if semantic:
                        data["semantic_review_constraints"] = semantic
                    raw, call = request_json(
                        task.id,
                        run_key,
                        "sample" if q["question_index"] <= 5 else "run",
                        SYSTEM_PROMPT,
                        data,
                        settings,
                    )
                check = check_candidate(result, q, raw)
                error = None
                break
            except (ProcessingError, ValidationError) as exc:
                code = getattr(exc, "code", "ANNOTATION_SCHEMA_INVALID")
                if code in {"STALE_LEASE", "SOURCE_CHANGED", "METHOD_CHANGED"}:
                    raise
                error = {"issue_code": code, "message": str(exc)[:1000]}
                feedback = {**error, "previous_candidate": raw}
                if code in {
                    "BUDGET_LIMIT",
                    "BUDGET_AUDIT_BLOCKED",
                    "CREDENTIALS_MISSING",
                }:
                    budget_block = error["message"]
                    break
                if code.startswith("LLM_"):
                    break
        if error:
            skipped.append(
                {
                    "question_src_id": q["_src_id"],
                    "question_index": q["question_index"],
                    "fields": [],
                    "reason": error["message"],
                    "issue_code": error["issue_code"],
                }
            )
            checkpoint(task.id, token, "annotation_skipped", skipped[-1], settings)
            continue
        checkpoint(
            task.id,
            token,
            "annotation_raw",
            {
                "question_src_id": q["_src_id"],
                "candidate": raw,
                "call": call,
                "prompt_version": PROMPT_VERSION,
                "validation_attempt": _attempt,
            },
            settings,
        )
        merge_candidate(result, q, raw)
        checkpoint(
            task.id,
            token,
            "annotate",
            {
                "question_src_id": q["_src_id"],
                "candidate": raw,
                "call": call,
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": fingerprint(SYSTEM_PROMPT),
                "checks": check,
            },
            settings,
        )
    result["assembly_audit"]["annotation_skipped"] = skipped
    checkpoint(
        task.id,
        token,
        "annotation_checks",
        {
            "status": "DRAFT_WITH_PENDING" if skipped else "PASS",
            "question_count": len(qs),
            "skipped": skipped,
            "semantic_accuracy": "requires separate review",
        },
        settings,
    )


def dispatch(task_id, token, settings, worker, original_process):
    from app.db.base import SessionLocal
    from app.module3 import annotation_checks

    with SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        policy = task.method.get("console_partial_draft")
    if not policy:
        return original_process(task_id, token, settings)
    if policy.get("implementation_sha256") != file_hash(Path(__file__)):
        with SessionLocal() as db:
            current = tasks.fenced_task(db, task_id, token)
            current.state = "failed"
            current.lease_token = None
            current.expires_at = None
            current.issues = [
                ProcessingError(
                    "METHOD_CHANGED", "草稿生成实现已变化，请重新建立任务"
                ).issue(current.stage)
            ]
            db.commit()
        return 2
    previous_assemble = worker.assemble_sources
    previous_annotate = annotation_checks.annotate_questions
    worker.assemble_sources = assemble
    annotation_checks.annotate_questions = annotate_questions
    try:
        return original_process(task_id, token, settings)
    finally:
        worker.assemble_sources = previous_assemble
        annotation_checks.annotate_questions = previous_annotate
