"""把 16 表采集试填工作簿整理为模块二结构化导入文件，并做自动预检。

只用 Python 标准库（zipfile + ElementTree），不需要 openpyxl / pandas。

用法（在仓库根目录）::

    python scripts/prepare_module2_materials.py \
        --xlsx "C:/Users/win/Desktop/模块二/2025年6月四级第一套_听力采集试填_16表版_20261024.xlsx" \
        --out  "C:/Users/win/Desktop/模块二/_local_materials"

输出（--out 指向的目录，**含真题内容，禁止提交 Git**）：
  - import_payload.json      结构化导入文件（导入工具的输入）
  - precheck_report.md       自动预检报告（不等于人工审核通过）
  - content_check_sheet.md   25 题逐题人工核对记录表（留空待填）+ 整套核听记录
  - source_manifest.md       来源清单与缺失项核对

说明：本脚本只做结构整理与可证伪的自动检查；逐题内容核对与整套核听
必须由真实人员完成（需求 §3.3 第 2 条、验收 B16），历史自动转写与
待审核标注不得直接视为人工审核通过。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 需要导入模块二的来源表（最小业务子集；词典与标注表本期不导入）。
SHEET_EXAM_PAPER = "01_exam_paper"
SHEET_AUDIO = "02_audio"
SHEET_PASSAGE = "03_passage"
SHEET_SEGMENT = "04_transcript_segment"
SHEET_QUESTION = "05_question"
SHEET_CONTENT_GROUP = "12_content_group"
SHEET_PRESENTATION = "13_presentation"

AUDIO_MIME_BY_FORMAT = {"m4a": "audio/mp4", "mp3": "audio/mpeg", "aac": "audio/aac"}


# --------------------------------------------------------------------------- #
# xlsx 解析（纯标准库）
# --------------------------------------------------------------------------- #
def _col_index(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def _cell_text(cell: ET.Element) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{NS}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{NS}t"))
    value = cell.find(f"{NS}v")
    return value.text if (value is not None and value.text is not None) else ""


def _read_sheet(zf: zipfile.ZipFile, filename: str) -> list[list[str]]:
    root = ET.fromstring(zf.read(filename))
    rows: list[list[str]] = []
    for row in root.iter(f"{NS}row"):
        cells: dict[int, str] = {}
        for cell in row.iter(f"{NS}c"):
            cells[_col_index(cell.get("r"))] = _cell_text(cell)
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


def load_workbook(path: Path) -> dict[str, list[dict[str, str]]]:
    """读取所有工作表为 {表名: [行dict,...]}；列名取第 1 行，跳过全空行。"""
    with zipfile.ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        names = [s.get("name") for s in workbook.iter(f"{NS}sheet")]
        tables: dict[str, list[dict[str, str]]] = {}
        for i, name in enumerate(names, start=1):
            rows = _read_sheet(zf, f"xl/worksheets/sheet{i}.xml")
            if not rows:
                tables[name] = []
                continue
            header = rows[0]
            records = []
            for raw in rows[1:]:
                record = {h: (raw[j] if j < len(raw) else "") for j, h in enumerate(header) if h}
                if any(v.strip() for v in record.values()):
                    records.append(record)
            tables[name] = records
    return tables


# --------------------------------------------------------------------------- #
# 取值与类型转换
# --------------------------------------------------------------------------- #
def to_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    return int(float(value))


def to_bool(value: str) -> bool | None:
    value = (value or "").strip()
    if not value:
        return None
    return value in ("1", "true", "True", "TRUE", "是")


def to_json(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def first(tables, name, key):
    rows = [r for r in tables.get(name, []) if r.get(key, "").strip()]
    return rows[0] if rows else None


def rows_of(tables, name, key):
    return [r for r in tables.get(name, []) if r.get(key, "").strip()]


# 来源字段脱敏：只保留文件名，不带个人电脑的盘符路径。
# 这些字段会随导入落库并通过管理员接口返回，不应暴露开发者本机目录结构。
# 负向后顾避免把 `https://...` 里的 `s:/` 误当成盘符路径。
_PATH_RE = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z]:[\\/][^，,；;（）()\n]*")


def sanitize_source(text: str) -> str:
    """把来源说明里的绝对路径压成文件名，保留页/题等定位信息。"""
    text = (text or "").strip()
    if not text:
        return ""

    def _basename(match: "re.Match[str]") -> str:
        raw = match.group(0).replace("\\", "/").rstrip("/ ")
        return raw.rsplit("/", 1)[-1]

    return _PATH_RE.sub(_basename, text).strip()


# --------------------------------------------------------------------------- #
# 构建结构化导入文件
# --------------------------------------------------------------------------- #
def build_payload(tables, xlsx_path: Path, audio_rel_key: str) -> dict:
    paper = first(tables, SHEET_EXAM_PAPER, "exam_paper_id")
    audio = first(tables, SHEET_AUDIO, "audio_id")
    group = first(tables, SHEET_CONTENT_GROUP, "content_group_id")
    if paper is None or audio is None:
        raise SystemExit("01_exam_paper 或 02_audio 没有有效数据行")

    passages = rows_of(tables, SHEET_PASSAGE, "passage_id")
    segments = rows_of(tables, SHEET_SEGMENT, "segment_id")
    questions = rows_of(tables, SHEET_QUESTION, "question_id")
    presentations = rows_of(tables, SHEET_PRESENTATION, "presentation_id")

    fmt = audio.get("format", "").strip().lower()
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "scripts/prepare_module2_materials.py",
            "source_xlsx": Path(xlsx_path).name,
            "source_xlsx_sha256": sha256_file(xlsx_path),
            "note": "结构化导入文件；自动预检不代替人工审核与整套核听（B16）",
        },
        "exam_paper": {
            "_src_id": to_int(paper["exam_paper_id"]),
            "exam_paper_code": paper["exam_paper_code"].strip(),
            "exam_level": paper["exam_level"].strip(),
            "exam_year": to_int(paper["exam_year"]),
            "exam_month": to_int(paper["exam_month"]),
            "paper_set": to_int(paper["paper_set"]),
            "content_scope": "listening",
            "playback_audio_src_id": to_int(paper["playback_audio_id"]),
            # 选定原卷的应有题量：导入时固定，后续批次对照校验（见验收报告 F02）。
            "expected_question_count": len(questions),
            # 来源与采集/审核状态：字段名与取值沿用 16 表基线。
            "source": sanitize_source(paper.get("source", "")),
            "mapping_source": sanitize_source(paper.get("mapping_source", "")),
            "collector": paper.get("collector", "").strip(),
            "review_status": paper.get("review_status", "").strip() or "待审核",
        },
        "audio": {
            "_src_id": to_int(audio["audio_id"]),
            "audio_code": audio["audio_code"].strip(),
            "storage_provider": audio.get("storage_provider", "local").strip() or "local",
            "storage_key": audio_rel_key,
            "duration_ms": to_int(audio["duration_ms"]),
            "format": fmt,
            "mime_type": AUDIO_MIME_BY_FORMAT.get(fmt, "application/octet-stream"),
            "file_hash": audio.get("file_hash", "").strip(),
            "is_current": to_bool(audio.get("is_current", "1")),
            "version_no": to_int(audio.get("version_no", "")) or 1,
            "variant_type": audio.get("variant_type", "").strip() or "原始",
            "collector": audio.get("collector", "").strip(),
            "review_status": audio.get("review_status", "").strip() or "待审核",
        },
        "content_groups": [
            {
                "_src_id": to_int(group["content_group_id"]),
                "content_group_code": group["content_group_code"].strip(),
                "group_name": group.get("group_name", "").strip(),
                "exam_level_scope": group.get("exam_level_scope", "").strip(),
                "content_fingerprint": group.get("content_fingerprint", "").strip(),
                "collector": group.get("collector", "").strip(),
                "review_status": group.get("review_status", "").strip() or "待审核",
            }
        ]
        if group
        else [],
        "passages": [
            {
                "_src_id": to_int(p["passage_id"]),
                "passage_code": p.get("passage_code", "").strip(),
                "audio_src_id": to_int(p["audio_id"]),
                "passage_index": to_int(p["passage_index"]),
                "passage_type": p.get("passage_type", "").strip(),
                "topic": p.get("topic", "").strip(),
                "scene": p.get("scene", "").strip(),
                "accent": p.get("accent", "").strip() or "未判定",
                "start_ms": to_int(p["start_ms"]),
                "body_end_ms": to_int(p["body_end_ms"]),
                "end_ms": to_int(p["end_ms"]),
                "speaker_count": to_int(p.get("speaker_count", "")),
                "collector": p.get("collector", "").strip(),
                "review_status": p.get("review_status", "").strip() or "待审核",
            }
            for p in passages
        ],
        "transcript_segments": [
            {
                "_src_id": to_int(s["segment_id"]),
                "passage_src_id": to_int(s["passage_id"]),
                "segment_index": to_int(s["segment_index"]),
                "segment_type": s.get("segment_type", "").strip(),
                "text": s.get("text", ""),
                "speaker_code": s.get("speaker_code", "").strip(),
                "start_ms": to_int(s["start_ms"]),
                "end_ms": to_int(s["end_ms"]),
                "collector": s.get("collector", "").strip(),
                "review_status": s.get("review_status", "").strip() or "待审核",
            }
            for s in segments
        ],
        "questions": [
            {
                "_src_id": to_int(q["question_id"]),
                "question_code": q.get("question_code", "").strip(),
                "passage_src_id": to_int(q["passage_id"]),
                "question_segment_src_id": to_int(q.get("question_segment_id", "")),
                # 来源卷全卷题号（基线 question_index），与目标卷题号分开。
                "question_index": to_int(q.get("question_index", "")),
                "question_text": q.get("question_text", ""),
                "option_a": q.get("option_a", ""),
                "option_b": q.get("option_b", ""),
                "option_c": q.get("option_c", ""),
                "option_d": q.get("option_d", ""),
                "correct_option": q.get("correct_option", "").strip(),
                "explanation_text": q.get("explanation_text", ""),
                "explanation_source": "CET4_2025_06_1_答案解析.pdf（摘要改写）",
                # 基线 content_state：待补齐 / 可用 / 停用。
                "content_state": q.get("content_state", "").strip() or "待补齐",
                "collector": q.get("collector", "").strip(),
                "review_status": q.get("review_status", "").strip() or "待审核",
            }
            for q in questions
        ],
        "presentations": [
            {
                "question_src_id": to_int(pr["question_id"]),
                "exam_paper_src_id": to_int(pr["exam_paper_id"]),
                "question_no": to_int(pr["question_no"]),
                "option_mapping_state": pr.get("option_mapping_state", "").strip() or "未知",
                "mapping_source": sanitize_source(pr.get("mapping_source", "")),
                "option_letter_mapping": (to_json(pr.get("attributes_json", "")) or {}).get(
                    "option_letter_mapping"
                ),
                "collector": pr.get("collector", "").strip(),
                "review_status": pr.get("review_status", "").strip() or "待审核",
            }
            for pr in presentations
        ],
    }
    return payload


# --------------------------------------------------------------------------- #
# 自动预检（可证伪的结构检查；不等于人工内容审核）
# --------------------------------------------------------------------------- #
def precheck(payload: dict) -> list[tuple[bool, str, str]]:
    checks: list[tuple[bool, str, str]] = []

    def add(ok: bool, name: str, detail: str):
        checks.append((ok, name, detail))

    paper = payload["exam_paper"]
    audio = payload["audio"]
    passages = payload["passages"]
    segments = payload["transcript_segments"]
    questions = payload["questions"]
    presentations = payload["presentations"]
    groups = payload["content_groups"]

    add(True, "试卷字段", f"code={paper['exam_paper_code']} level={paper['exam_level']} "
                         f"{paper['exam_year']}-{paper['exam_month']:02d} 第{paper['paper_set']}套 scope={paper['content_scope']}")
    add(bool(audio["file_hash"]) and audio["duration_ms"], "音频字段",
        f"duration_ms={audio['duration_ms']} format={audio['format']} hash={audio['file_hash'][:16]}...（文件本体需另行核对存在与哈希）")
    add(len(groups) == 1, "内容组数量", f"{len(groups)} 个")

    idxs = [p["passage_index"] for p in passages]
    add(sorted(idxs) == list(range(1, len(idxs) + 1)), "篇章序号连续", f"{len(passages)} 篇 index={idxs}")
    types = {}
    for p in passages:
        types[p["passage_type"]] = types.get(p["passage_type"], 0) + 1
    add(True, "篇章类型分布", str(types))

    body = [s for s in segments if s["segment_type"] == "body"]
    qseg = [s for s in segments if s["segment_type"] == "question"]
    add(len(body) == 140 and len(qseg) == 25, "转写片段构成", f"body={len(body)} question={len(qseg)} 共{len(segments)}")

    passage_by_src = {p["_src_id"]: p for p in passages}
    seg_ids = {s["_src_id"] for s in segments}
    ok_fk = all(s["passage_src_id"] in passage_by_src for s in segments)
    add(ok_fk, "片段→篇章外键", "全部片段的 passage_src_id 存在" if ok_fk else "存在悬空引用")

    time_ok = True
    for s in segments:
        p = passage_by_src.get(s["passage_src_id"])
        if not (s["start_ms"] < s["end_ms"]):
            time_ok = False
        if p and not (p["start_ms"] <= s["start_ms"] and s["end_ms"] <= p["end_ms"]):
            time_ok = False
    add(time_ok, "片段时间在篇章范围内", "start<end 且落在篇章 start_ms..end_ms 内")

    opts_ok = all(q["option_a"] and q["option_b"] and q["option_c"] and q["option_d"] for q in questions)
    ans_ok = all(q["correct_option"] in ("A", "B", "C", "D") for q in questions)
    exp_ok = all(q["explanation_text"].strip() for q in questions)
    add(opts_ok, "题目四选项非空", f"{len(questions)} 题")
    add(ans_ok, "答案字母 A–D", "全部合法" if ans_ok else "存在非法答案字母")
    add(exp_ok, "解析非空", "全部有解析" if exp_ok else "存在空解析")
    qseg_ok = all(q["question_segment_src_id"] in seg_ids for q in questions)
    add(qseg_ok, "题目→录音问题片段外键", "question_segment_src_id 均指向存在的片段")
    qp_ok = all(q["passage_src_id"] in passage_by_src for q in questions)
    add(qp_ok, "题目→篇章外键", "question.passage_src_id 均存在")

    nos = [pr["question_no"] for pr in presentations]
    add(sorted(nos) == list(range(1, len(nos) + 1)), "原卷题号连续", f"{len(presentations)} 条 question_no={nos}")
    qids = {q["_src_id"] for q in questions}
    pr_fk = all(pr["question_src_id"] in qids for pr in presentations)
    add(pr_fk, "映射→题目外键", "presentation.question_src_id 均存在")
    identity = all(
        (pr["option_letter_mapping"] in (None, {"A": "A", "B": "B", "C": "C", "D": "D"}))
        for pr in presentations
    )
    add(identity, "选项字母映射", "全部恒等映射 A-D→A-D" if identity else "存在非恒等映射，需人工复核")
    add(all(pr["exam_paper_src_id"] == paper["_src_id"] for pr in presentations), "映射属同一试卷", "exam_paper_src_id 一致")

    return checks


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def write_outputs(out_dir: Path, payload: dict, checks, xlsx_path: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "import_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    failed = [c for c in checks if not c[0]]
    lines = [
        "# 模块二样例自动预检报告",
        "",
        f"- 生成时间：{payload['meta']['generated_at']}",
        f"- 来源工作簿：`{xlsx_path.name}`（SHA-256 `{payload['meta']['source_xlsx_sha256'][:16]}...`）",
        "",
        "> 这是**自动结构预检**，只验证可证伪的结构与外键；不代替需求 §3.3 第 2 条",
        "> 要求的**逐题内容核对与整套音频核听**（验收 B16）。历史自动转写与待审核标注",
        "> 不得直接视为人工审核通过。",
        "",
        f"**结果：{len(checks) - len(failed)}/{len(checks)} 项通过" + (f"，{len(failed)} 项待处理**" if failed else "**"),
        "",
        "| 项 | 结果 | 说明 |",
        "|---|---|---|",
    ]
    for ok, name, detail in checks:
        lines.append(f"| {name} | {'✅' if ok else '❌'} | {detail} |")
    (out_dir / "precheck_report.md").write_text("\n".join(lines), encoding="utf-8")

    q_by_no = {pr["question_no"]: pr for pr in payload["presentations"]}
    q_by_src = {q["_src_id"]: q for q in payload["questions"]}
    sheet = [
        "# 模块二样例内容核对记录表（逐题，留空待人工填写）",
        "",
        "- 负责人：__________（待施博宇指定）　核听人：__________　日期：__________",
        "- 说明：每题核对题干、A–D 选项、标准答案、解析与原文对应关系；问题与修正如实记录。",
        "- 本表由脚本按当前导入数据生成，「参考答案/选项」来自试填工作簿，**仍需对照原卷 PDF 与答案解析 PDF 人工确认**。",
        "",
        "| 题号 | 参考答案 | 题干核对 | 选项核对 | 答案核对 | 解析核对 | 原文对应 | 问题与修正 | 核对人 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for no in sorted(q_by_no):
        q = q_by_src.get(q_by_no[no]["question_src_id"], {})
        sheet.append(
            f"| {no} | {q.get('correct_option','')} | ☐ | ☐ | ☐ | ☐ | ☐ |  |  |"
        )
    sheet += [
        "",
        "## 整套音频核听记录",
        "",
        f"- 音频：`{payload['audio']['storage_key']}`（{payload['audio']['duration_ms']} ms，"
        f"{payload['audio']['format']}，SHA-256 `{payload['audio']['file_hash'][:16]}...`）",
        "- 核听范围：完整整套约 23 分 36 秒，含 8 篇章正文与 25 个录音问题。",
        "- 核听结论：__________　发现问题：__________　修正记录：__________",
    ]
    (out_dir / "content_check_sheet.md").write_text("\n".join(sheet), encoding="utf-8")

    manifest = [
        "# 来源清单核对（脚本整理，供人工补全）",
        "",
        "| 材料 | 状态 | 哈希（SHA-256） | 备注 |",
        "|---|---|---|---|",
        f"| 试填工作簿 {xlsx_path.name} | ✅ 已就位 | `{payload['meta']['source_xlsx_sha256'][:16]}...` | 16 表数据来源 |",
        f"| 听力音频 {payload['audio']['storage_key']} | ⚠️ 待放入受控目录 | 采集登记 `{payload['audio']['file_hash'][:16]}...` | 后缀需为 .m4a，不转码；导入前复核哈希 |",
        "| 真题 PDF | ⚠️ 需人工对照 | 见来源清单_CET4_2025_06_1.md | 逐题核对题干/选项/题号 |",
        "| 答案解析 PDF | ⚠️ 需人工对照 | 见来源清单_CET4_2025_06_1.md | 核对答案/解析 |",
        "| 原始时间校对稿 | ❌ 缺失 | 待补 | 现有为由采集表导出的替代稿 |",
        "| 旧采集表 ljt.xlsx | ❌ 缺失 | 待补 | 数据溯源 |",
        "| schema_options_merged_16tables.json | ❌ 缺失 | 待补 | 16 表字段结构与枚举 |",
    ]
    (out_dir / "source_manifest.md").write_text("\n".join(manifest), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="整理模块二结构化导入文件并自动预检")
    parser.add_argument("--xlsx", required=True, help="16 表试填工作簿路径")
    parser.add_argument("--out", required=True, help="输出目录（仓库外，禁止提交 Git）")
    parser.add_argument(
        "--audio-key",
        default="CET4_2025_06_1_听力.m4a",
        help="音频在受控目录内的相对 storage_key",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    out_dir = Path(args.out)
    tables = load_workbook(xlsx_path)
    payload = build_payload(tables, xlsx_path, args.audio_key)
    checks = precheck(payload)
    write_outputs(out_dir, payload, checks, xlsx_path)

    failed = [c for c in checks if not c[0]]
    print(f"已生成结构化导入文件与预检报告 → {out_dir}")
    print(f"自动预检：{len(checks) - len(failed)}/{len(checks)} 通过")
    for ok, name, detail in checks:
        if not ok:
            print(f"  ❌ {name}: {detail}")
    print("提醒：自动预检不代替人工逐题核对与整套核听（B16）。")


if __name__ == "__main__":
    main()
