"""模块二样例导入工具：把结构化导入文件与真实音频写入 PostgreSQL。

用法（在 backend 目录）::

    python -m app.import_module2 --input <import_payload.json> --audio-file <真实音频.m4a>

特性（对齐需求 M2-B07 / M2-B08、验收 B02/B09/B13）：
- **幂等**：以试卷编码 + 材料内容哈希计算 ``batch_code``；同批次已 ``active``
  时直接返回「已导入，无变更」，不新增记录、不切换批次、不清除已有可见确认。
- **事务与回滚**：新批次先写 ``pending``，全部写入成功后在单事务内置
  ``active`` 并切换 ``is_current``；任一步失败整体回滚，不留半套试卷，
  原当前批次及其可见状态保持有效。
- **音频**：校验真实音频存在、可读、SHA-256 与来源清单一致，复制到受控目录；
  数据库只存引用、哈希、时长，不存文件本体。
- 字段缺失、外键错误、映射异常、文件缺失给出可定位信息；不使用占位答案、
  虚构解析或虚构原文。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import SessionLocal
from app.db import models_listening as m

# 采集来源默认标识：本套数据来自试填工作簿的人工整理导入，未经人工核听，
# 因此 review_status 一律保持「待审核」，不得写成「已通过」。
DEFAULT_COLLECTOR = "人工整理导入（试填数据，未经人工核听）"

PAYLOAD_SECTIONS = (
    "exam_paper",
    "audio",
    "content_groups",
    "passages",
    "transcript_segments",
    "questions",
    "presentations",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_hash(payload: dict) -> str:
    core = {k: payload[k] for k in PAYLOAD_SECTIONS}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_payload(payload: dict) -> None:
    for section in PAYLOAD_SECTIONS:
        _require(section in payload, f"导入文件缺少段落：{section}")
    paper = payload["exam_paper"]
    count = paper.get("expected_question_count")
    source = paper.get("expected_question_count_source")
    if count is not None or source is not None:
        _require(type(count) is int and count > 0, "应有题量必须是正整数")
        _require(
            isinstance(source, dict)
            and all(isinstance(source.get(key), str) and source[key].strip()
                    for key in ("document", "sha256", "locator"))
            and re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")) is not None,
            "应有题量须附原卷核对依据 expected_question_count_source：document、sha256、locator",
        )
    for field in ("exam_paper_code", "exam_level", "exam_year", "exam_month", "paper_set"):
        _require(paper.get(field) not in (None, ""), f"exam_paper 缺少字段：{field}")
    audio = payload["audio"]
    _require(bool(audio.get("file_hash")), "audio 缺少 file_hash")
    _require(bool(audio.get("duration_ms")), "audio 缺少 duration_ms")
    _require(bool(payload["questions"]), "导入文件没有任何题目")
    _require(bool(payload["passages"]), "导入文件没有任何篇章")
    for q in payload["questions"]:
        _require(q.get("correct_option") in ("A", "B", "C", "D"),
                 f"题目 {q.get('question_code')} 答案字母非法")
        _require(bool((q.get("explanation_text") or "").strip()),
                 f"题目 {q.get('question_code')} 解析为空（不允许占位解析）")


def _content_state(question: dict) -> str:
    """按 16 表基线判定内容完整度：题干、四选项、答案、解析齐全才算「可用」。"""
    required = ("question_text", "option_a", "option_b", "option_c", "option_d",
                "correct_option", "explanation_text")
    if all(str(question.get(field) or "").strip() for field in required):
        return "可用"
    return "待补齐"


def _resolve_audio_target(
    audio_dir: Path, requested_key: str, content_hash: str
) -> tuple[Path, bool]:
    """决定音频落盘路径，保证不覆盖仍在被旧批次引用的文件（验收报告 F01）。

    - 目标不存在：直接用请求的 storage_key 新建
    - 目标已存在且内容相同：复用，不重写
    - 目标已存在但内容不同：改用带内容指纹的文件名（``<名>-<hash8><后缀>``），
      旧文件原样保留，旧当前批次继续可播放
    """
    _require(Path(requested_key).name == requested_key, "storage_key 必须是单个文件名")
    target = audio_dir / requested_key
    candidates = (
        target,
        audio_dir / f"{target.stem}-{content_hash[:8]}{target.suffix}",
        audio_dir / f"{target.stem}-{content_hash}{target.suffix}",
    )
    for candidate in candidates:
        if not candidate.exists():
            return candidate, True
        if candidate.is_file() and sha256_file(candidate) == content_hash:
            return candidate, False
    raise ValueError("音频内容指纹路径冲突，拒绝覆盖已有文件")


def _set_expected_count(paper: m.ExamPaper, paper_data: dict) -> None:
    """只有显式原卷核对结果可建立基准，绝不按待校验的题数推导。"""
    declared = paper_data.get("expected_question_count")
    if declared is None:
        return
    if paper.expected_question_count is not None and declared != paper.expected_question_count:
        raise ValueError(
            f"应有题量与已固定值冲突：已固定 {paper.expected_question_count} 题，"
            f"本次申报 {declared} 题；同一试卷的应有题量不允许被后续批次改写"
        )
    if paper.expected_question_count_source and (
        paper.expected_question_count_source != paper_data["expected_question_count_source"]
    ):
        raise ValueError("应有题量来源与已固定依据冲突")
    paper.expected_question_count = declared
    paper.expected_question_count_source = paper_data["expected_question_count_source"]


def run_import(payload_path: Path, audio_file: Path) -> dict:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    validate_payload(payload)

    # 音频校验：存在、可读、哈希与来源清单一致。
    if not audio_file.is_file():
        raise FileNotFoundError(f"音频文件不存在：{audio_file}")
    actual_hash = sha256_file(audio_file)
    expected_hash = payload["audio"]["file_hash"]
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(
            f"音频哈希不一致：期望 {expected_hash[:16]}...，实际 {actual_hash[:16]}..."
        )

    settings = get_settings()
    audio_dir = settings.audio_storage_path
    audio_dir.mkdir(parents=True, exist_ok=True)

    requested_key = payload["audio"]["storage_key"]
    destination, needs_write = _resolve_audio_target(audio_dir, requested_key, actual_hash)
    # 实际落库的键可能因内容冲突而与申报值不同，以落盘结果为准。
    storage_key = destination.name

    # 仅在数据库写入完成后暂存；created 只记录本次实际创建的正式文件。
    staged: Path | None = None
    created: Path | None = None

    mhash = manifest_hash(payload)
    paper_code = payload["exam_paper"]["exam_paper_code"]
    batch_code = f"{paper_code}-{mhash[:12]}"

    with SessionLocal() as db:
        try:
            existing = db.scalar(
                select(m.ImportBatch).where(m.ImportBatch.batch_code == batch_code)
            )
            if existing is not None and existing.status == "active":
                if staged is not None and staged.exists():
                    staged.unlink(missing_ok=True)
                # 幂等材料也必须检查基准冲突；不从材料题数补基准。
                paper = db.scalar(
                    select(m.ExamPaper).where(m.ExamPaper.exam_paper_code == paper_code)
                )
                if paper is not None:
                    _set_expected_count(paper, payload["exam_paper"])
                    db.commit()
                return {
                    "status": "noop",
                    "batch_code": batch_code,
                    "message": "已导入，无变更（幂等）",
                }
            if existing is not None:
                # 清理上一次失败/未完成的同批次草稿，避免遗留半套数据。
                db.delete(existing)
                db.flush()

            audio_data = payload["audio"]
            audio_rec = db.scalar(
                select(m.AudioFile).where(m.AudioFile.audio_code == audio_data["audio_code"])
            )
            if audio_rec is not None:
                # audio_code 是唯一身份：已有记录必须与本次材料完全一致，
                # 否则不能「报成功却用另一份文件的元信息」（验收报告 F05）。
                conflicts = []
                if audio_rec.file_hash != expected_hash:
                    conflicts.append(
                        f"文件哈希 现有 {audio_rec.file_hash[:16]}... / 申报 {expected_hash[:16]}..."
                    )
                if audio_rec.storage_key != storage_key:
                    conflicts.append(
                        f"storage_key 现有 {audio_rec.storage_key} / 申报 {storage_key}"
                    )
                if audio_rec.duration_ms != audio_data["duration_ms"]:
                    conflicts.append(
                        f"时长 现有 {audio_rec.duration_ms}ms / 申报 {audio_data['duration_ms']}ms"
                    )
                if conflicts:
                    raise ValueError(
                        f"音频编码 {audio_data['audio_code']} 已被另一份文件占用，拒绝静默复用："
                        + "；".join(conflicts)
                        + "。音频编码是唯一身份，内容变更（如剪辑、降噪）请使用新的 audio_code。"
                    )
            if audio_rec is None:
                audio_rec = m.AudioFile(
                    audio_code=audio_data["audio_code"],
                    storage_provider=audio_data.get("storage_provider", "local"),
                    storage_key=storage_key,
                    duration_ms=audio_data["duration_ms"],
                    format=audio_data.get("format", ""),
                    mime_type=audio_data.get("mime_type", "application/octet-stream"),
                    file_hash=expected_hash,
                    is_current=True,
                    version_no=audio_data.get("version_no") or 1,
                    variant_type=audio_data.get("variant_type") or "原始",
                    collector=audio_data.get("collector") or DEFAULT_COLLECTOR,
                    review_status=audio_data.get("review_status") or "待审核",
                )
                db.add(audio_rec)
                db.flush()

            paper_data = payload["exam_paper"]
            paper_rec = db.scalar(
                select(m.ExamPaper).where(m.ExamPaper.exam_paper_code == paper_code)
            )
            if paper_rec is None:
                paper_rec = m.ExamPaper(
                    exam_paper_code=paper_code,
                    exam_level=paper_data["exam_level"],
                    exam_year=paper_data["exam_year"],
                    exam_month=paper_data["exam_month"],
                    paper_set=paper_data["paper_set"],
                    content_scope=paper_data.get("content_scope", "listening"),
                    source=paper_data.get("source") or "",
                    mapping_source=paper_data.get("mapping_source") or "",
                    collector=paper_data.get("collector") or DEFAULT_COLLECTOR,
                    review_status=paper_data.get("review_status") or "待审核",
                )
                db.add(paper_rec)
                db.flush()

            _set_expected_count(paper_rec, paper_data)
            paper_rec.playback_audio_id = audio_rec.id

            batch = m.ImportBatch(
                exam_paper_id=paper_rec.id,
                audio_id=audio_rec.id,
                batch_code=batch_code,
                status="pending",
                is_current=False,
                source_manifest_hash=mhash,
                source_manifest={
                    "exam_paper_code": paper_code,
                    "audio_file_hash": expected_hash,
                    "duration_ms": audio_data["duration_ms"],
                    "source_xlsx_sha256": payload.get("meta", {}).get("source_xlsx_sha256"),
                    "expected_question_count": paper_rec.expected_question_count,
                    "expected_question_count_source": paper_rec.expected_question_count_source,
                },
            )
            db.add(batch)
            db.flush()

            for group in payload["content_groups"]:
                db.add(
                    m.ContentGroup(
                        batch_id=batch.id,
                        content_group_code=group["content_group_code"],
                        group_name=group.get("group_name", ""),
                        exam_level_scope=group.get("exam_level_scope", ""),
                        content_fingerprint=group.get("content_fingerprint"),
                        collector=group.get("collector") or DEFAULT_COLLECTOR,
                        review_status=group.get("review_status") or "待审核",
                    )
                )

            passage_map: dict[int, int] = {}
            for p in payload["passages"]:
                rec = m.Passage(
                    batch_id=batch.id,
                    exam_paper_id=paper_rec.id,
                    audio_id=audio_rec.id,
                    passage_code=p.get("passage_code", ""),
                    passage_index=p["passage_index"],
                    passage_type=p.get("passage_type", ""),
                    topic=p.get("topic", ""),
                    scene=p.get("scene", ""),
                    accent=p.get("accent") or "未判定",
                    start_ms=p["start_ms"],
                    body_end_ms=p.get("body_end_ms"),
                    end_ms=p.get("end_ms"),
                    speaker_count=p.get("speaker_count"),
                    collector=p.get("collector") or DEFAULT_COLLECTOR,
                    review_status=p.get("review_status") or "待审核",
                )
                db.add(rec)
                db.flush()
                passage_map[p["_src_id"]] = rec.id

            segment_map: dict[int, int] = {}
            for s in payload["transcript_segments"]:
                rec = m.TranscriptSegment(
                    batch_id=batch.id,
                    passage_id=passage_map[s["passage_src_id"]],
                    segment_index=s["segment_index"],
                    segment_type=s["segment_type"],
                    text=s["text"],
                    speaker_code=s.get("speaker_code", ""),
                    start_ms=s["start_ms"],
                    end_ms=s["end_ms"],
                    collector=s.get("collector") or DEFAULT_COLLECTOR,
                    review_status=s.get("review_status") or "待审核",
                )
                db.add(rec)
                db.flush()
                segment_map[s["_src_id"]] = rec.id

            question_map: dict[int, int] = {}
            for q in payload["questions"]:
                rec = m.Question(
                    batch_id=batch.id,
                    passage_id=passage_map[q["passage_src_id"]],
                    question_code=q.get("question_code", ""),
                    question_segment_id=segment_map.get(q.get("question_segment_src_id")),
                    question_index=q.get("question_index"),
                    question_text=q["question_text"],
                    option_a=q["option_a"],
                    option_b=q["option_b"],
                    option_c=q["option_c"],
                    option_d=q["option_d"],
                    correct_option=q["correct_option"],
                    explanation_text=q["explanation_text"],
                    explanation_source=q.get("explanation_source", ""),
                    content_state=_content_state(q),
                    collector=q.get("collector") or DEFAULT_COLLECTOR,
                    review_status=q.get("review_status") or "待审核",
                )
                db.add(rec)
                db.flush()
                question_map[q["_src_id"]] = rec.id

            for pr in payload["presentations"]:
                db.add(
                    m.Presentation(
                        batch_id=batch.id,
                        exam_paper_id=paper_rec.id,
                        question_id=question_map[pr["question_src_id"]],
                        question_no=pr["question_no"],
                        option_mapping_state=pr.get("option_mapping_state", "unknown"),
                        mapping_source=pr.get("mapping_source", ""),
                        option_letter_mapping=pr.get("option_letter_mapping"),
                        collector=pr.get("collector") or DEFAULT_COLLECTOR,
                        review_status=pr.get("review_status") or "待审核",
                    )
                )

            # 切换当前批次：同卷其他批次取消 current，本批次置 active + current。
            db.query(m.ImportBatch).filter(
                m.ImportBatch.exam_paper_id == paper_rec.id,
                m.ImportBatch.id != batch.id,
            ).update({"is_current": False})
            batch.status = "active"
            batch.is_current = True
            batch.imported_at = datetime.now(timezone.utc)

            # 先完成 flush，再发布文件。硬链接以排他方式新建，永不覆盖已有目标。
            db.flush()
            if needs_write:
                staged = audio_dir / f".incoming-{uuid.uuid4().hex}{destination.suffix}"
                shutil.copyfile(audio_file, staged)
                try:
                    os.link(staged, destination)
                except FileExistsError:
                    _require(destination.is_file() and sha256_file(destination) == actual_hash,
                             "音频目标在导入期间发生冲突，拒绝覆盖")
                else:
                    created = destination

            result = {
                "status": "imported",
                "batch_code": batch_code,
                "exam_paper_code": paper_code,
                "counts": {
                    "content_groups": len(payload["content_groups"]),
                    "passages": len(payload["passages"]),
                    "transcript_segments": len(payload["transcript_segments"]),
                    "questions": len(payload["questions"]),
                    "presentations": len(payload["presentations"]),
                },
                "audio": {
                    "storage_key": storage_key,
                    "requested_storage_key": requested_key,
                    "file_hash": expected_hash[:16] + "...",
                },
                "expected_question_count": paper_rec.expected_question_count,
            }
            db.commit()
            return result
        except Exception:
            db.rollback()
            if created is not None:
                created.unlink(missing_ok=True)
            raise
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="导入模块二结构化样例与真实音频")
    parser.add_argument("--input", required=True, help="结构化导入文件 import_payload.json")
    parser.add_argument("--audio-file", required=True, help="真实音频文件（与来源清单哈希一致）")
    args = parser.parse_args()

    try:
        result = run_import(Path(args.input), Path(args.audio_file))
    except Exception as exc:  # noqa: BLE001 - CLI 需把可定位错误打印出来
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
