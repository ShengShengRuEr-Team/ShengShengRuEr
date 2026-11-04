"""最低内容检查：确认可见前的技术门槛（需求 M2-B06 第 5 条）。

覆盖完整题量、题序与选项映射、必要展示字段、音频可用性。这是本阶段的
最低内容检查，不是模块三的语义标注与证据自动检查引擎；也不等于人工
内容审核（B16）。检查结果持久化到 content_checks，与可见性、标注审核、
模块三验收彼此独立。
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models_listening import (
    ContentCheck,
    ExamPaper,
    ImportBatch,
    Passage,
    Presentation,
    Question,
)


def _issue(kind: str, message: str) -> dict:
    return {"kind": kind, "message": message}


def evaluate(db: Session, paper: ExamPaper, batch: ImportBatch, audio_dir: Path) -> list[dict]:
    """返回问题清单；空清单表示检查通过。"""
    issues: list[dict] = []

    questions = db.scalars(select(Question).where(Question.batch_id == batch.id)).all()
    presentations = db.scalars(
        select(Presentation).where(Presentation.batch_id == batch.id)
    ).all()
    passages = db.scalars(select(Passage).where(Passage.batch_id == batch.id)).all()

    # 1. 完整题量：以该套选定原卷固定的应有题量为准，而不是只比较题目数与映射数。
    #    否则「末尾整题一起缺失」仍会通过检查（验收报告 F02）。
    if not questions:
        issues.append(_issue("missing_questions", "当前批次没有任何题目"))

    expected_count = paper.expected_question_count
    if expected_count is None:
        issues.append(
            _issue(
                "expected_count_missing",
                "试卷未记录应有题量，无法校验整卷完整性；请重新导入以固定应有题量",
            )
        )
    elif len(questions) != expected_count:
        issues.append(
            _issue(
                "question_count_mismatch",
                f"题目数({len(questions)})与选定原卷应有题量({expected_count})不一致",
            )
        )
    if len(questions) != len(presentations):
        issues.append(
            _issue(
                "question_count_mismatch",
                f"题目数({len(questions)})与原卷映射数({len(presentations)})不一致",
            )
        )

    # 2. 题序连续，且覆盖 1..应有题量
    question_nos = sorted(p.question_no for p in presentations)
    upper_bound = expected_count if expected_count is not None else len(question_nos)
    if question_nos and question_nos != list(range(1, upper_bound + 1)):
        issues.append(
            _issue(
                "question_no_not_sequential",
                f"原卷题号应为 1—{upper_bound}，实际为：{question_nos}",
            )
        )

    presentation_by_question = {p.question_id: p for p in presentations}
    passage_ids = {p.id for p in passages}

    # 3/4. 逐题展示字段、选项映射与篇章归属、内容完整度
    for q in questions:
        if q.passage_id not in passage_ids:
            issues.append(_issue("question_passage_missing", f"题目 {q.question_code} 所属篇章不存在"))
        if not q.question_text.strip():
            issues.append(_issue("question_text_empty", f"题目 {q.question_code} 题干为空"))
        for letter, text_ in (("A", q.option_a), ("B", q.option_b), ("C", q.option_c), ("D", q.option_d)):
            if not (text_ or "").strip():
                issues.append(_issue("option_empty", f"题目 {q.question_code} 选项 {letter} 为空"))
        if q.correct_option not in ("A", "B", "C", "D"):
            issues.append(_issue("correct_option_invalid", f"题目 {q.question_code} 答案字母非法：{q.correct_option}"))
        # 16 表基线 content_state：非「可用」的题目不允许进入可展示状态。
        if q.content_state != "可用":
            issues.append(
                _issue(
                    "content_state_not_usable",
                    f"题目 {q.question_code} 内容完整度为「{q.content_state}」，不能确认可见",
                )
            )
        presentation = presentation_by_question.get(q.id)
        if presentation is None:
            issues.append(_issue("presentation_missing", f"题目 {q.question_code} 缺少原卷映射"))
        else:
            mapping = presentation.option_letter_mapping or {}
            letters = ["A", "B", "C", "D"]
            if sorted(mapping.keys()) != letters:
                issues.append(
                    _issue("option_mapping_incomplete", f"题目 {q.question_code} 选项映射未覆盖 A-D")
                )
            elif sorted(str(mapping[letter]) for letter in letters) != letters:
                # 映射值必须是 A–D 的一一对应，否则会出现空选项或重复选项（验收报告 F03）。
                issues.append(
                    _issue(
                        "option_mapping_invalid",
                        f"题目 {q.question_code} 选项映射值非法：{mapping}（必须是 A–D 的排列）",
                    )
                )
            else:
                base_options = {
                    "A": q.option_a,
                    "B": q.option_b,
                    "C": q.option_c,
                    "D": q.option_d,
                }
                shown = [base_options[str(mapping[letter])] for letter in letters]
                if any(not (text or "").strip() for text in shown):
                    issues.append(
                        _issue(
                            "option_display_empty",
                            f"题目 {q.question_code} 按本套映射组装后存在空选项",
                        )
                    )

    # 5. 音频可用性
    from app.db.models_listening import AudioFile

    audio = db.get(AudioFile, paper.playback_audio_id) if paper.playback_audio_id else None
    if audio is None:
        issues.append(_issue("audio_unbound", "试卷未绑定音频"))
    else:
        audio_path = audio_dir / audio.storage_key
        if not audio_path.is_file():
            issues.append(_issue("audio_missing", f"音频文件不存在：{audio.storage_key}"))

    return issues


def run_check(
    db: Session, paper: ExamPaper, batch: ImportBatch, audio_dir: Path
) -> ContentCheck:
    """执行检查并把结果写入 content_checks（持久化，重启后仍可查）。"""
    issues = evaluate(db, paper, batch, audio_dir)
    check = ContentCheck(
        exam_paper_id=paper.id,
        batch_id=batch.id,
        is_passed=(len(issues) == 0),
        issues=issues,
    )
    db.add(check)
    db.flush()
    return check
