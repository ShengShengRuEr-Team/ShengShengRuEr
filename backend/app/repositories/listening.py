"""模块二题库查询的数据访问层。

所有 SQLAlchemy 查询集中在此，接口层不写死整套题目；同一接口的数据与
状态来自一致的当前批次。学生可访问 = 当前批次 ∧ 最低内容检查通过 ∧
管理员确认可见；三态分别取自 import_batches / content_checks /
paper_visibility，不合并。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models_listening import (
    AudioFile,
    ContentCheck,
    ExamPaper,
    ImportBatch,
    PaperVisibility,
    Passage,
    Presentation,
    Question,
    TranscriptSegment,
)

BASE_OPTIONS = ("A", "B", "C", "D")


# --------------------------------------------------------------------------- #
# 基础查询
# --------------------------------------------------------------------------- #
def get_paper(db: Session, exam_paper_id: int) -> ExamPaper | None:
    return db.get(ExamPaper, exam_paper_id)


def get_current_batch(db: Session, exam_paper_id: int) -> ImportBatch | None:
    return db.scalar(
        select(ImportBatch).where(
            ImportBatch.exam_paper_id == exam_paper_id,
            ImportBatch.is_current.is_(True),
            ImportBatch.status == "active",
        )
    )


def get_latest_check(db: Session, batch_id: int) -> ContentCheck | None:
    return db.scalar(
        select(ContentCheck)
        .where(ContentCheck.batch_id == batch_id)
        .order_by(ContentCheck.checked_at.desc(), ContentCheck.id.desc())
        .limit(1)
    )


def get_visibility(db: Session, batch_id: int) -> PaperVisibility | None:
    return db.scalar(
        select(PaperVisibility)
        .where(PaperVisibility.batch_id == batch_id)
        .order_by(PaperVisibility.id.desc())
        .limit(1)
    )


def get_audio(db: Session, audio_id: int | None) -> AudioFile | None:
    if audio_id is None:
        return None
    return db.get(AudioFile, audio_id)


# --------------------------------------------------------------------------- #
# 学生可见性判定
# --------------------------------------------------------------------------- #
def student_access(db: Session, exam_paper_id: int) -> tuple[bool, ExamPaper | None, ImportBatch | None]:
    """返回 (是否可见, 试卷, 当前批次)。三态缺一即不可见。"""
    paper = get_paper(db, exam_paper_id)
    if paper is None:
        return False, None, None
    batch = get_current_batch(db, exam_paper_id)
    if batch is None:
        return False, paper, None
    check = get_latest_check(db, batch.id)
    if check is None or not check.is_passed:
        return False, paper, batch
    visibility = get_visibility(db, batch.id)
    if visibility is None or not visibility.is_visible:
        return False, paper, batch
    return True, paper, batch


def list_papers(db: Session, *, is_admin: bool) -> list[tuple[ExamPaper, ImportBatch | None]]:
    """管理员看全部；学生只保留满足可见条件的试卷。"""
    papers = db.scalars(select(ExamPaper).order_by(ExamPaper.id)).all()
    result: list[tuple[ExamPaper, ImportBatch | None]] = []
    for paper in papers:
        if is_admin:
            result.append((paper, get_current_batch(db, paper.id)))
        else:
            visible, _, batch = student_access(db, paper.id)
            if visible:
                result.append((paper, batch))
    return result


# --------------------------------------------------------------------------- #
# 批次内容组装
# --------------------------------------------------------------------------- #
def _load_batch_content(db: Session, batch_id: int):
    passages = db.scalars(
        select(Passage).where(Passage.batch_id == batch_id).order_by(Passage.passage_index)
    ).all()
    passage_ids = [p.id for p in passages]
    segments = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.batch_id == batch_id)
        .order_by(TranscriptSegment.passage_id, TranscriptSegment.segment_index)
    ).all()
    questions = db.scalars(
        select(Question).where(Question.batch_id == batch_id)
    ).all()
    presentations = db.scalars(
        select(Presentation)
        .where(Presentation.batch_id == batch_id)
        .order_by(Presentation.question_no)
    ).all()

    seg_by_passage: dict[int, list[TranscriptSegment]] = {}
    for s in segments:
        seg_by_passage.setdefault(s.passage_id, []).append(s)
    question_by_id = {q.id: q for q in questions}
    questions_by_passage: dict[int, list[Question]] = {}
    for q in questions:
        questions_by_passage.setdefault(q.passage_id, []).append(q)
    # 题目按原卷题号排序
    presentation_by_question = {p.question_id: p for p in presentations}
    return passages, seg_by_passage, questions_by_passage, presentation_by_question, question_by_id


def _options_for(question: Question, presentation: Presentation | None) -> list[dict]:
    """按本套原卷映射组装选项顺序，不默认恒等、不混用其他套卷映射。"""
    base_by_letter = {
        "A": question.option_a,
        "B": question.option_b,
        "C": question.option_c,
        "D": question.option_d,
    }
    mapping = (presentation.option_letter_mapping if presentation else None) or {
        letter: letter for letter in BASE_OPTIONS
    }
    options = []
    for paper_letter in BASE_OPTIONS:  # 原卷字母顺序 A-D
        base_letter = mapping.get(paper_letter, paper_letter)
        options.append({"label": paper_letter, "text": base_by_letter.get(base_letter, "")})
    return options


def assemble_student_detail(db: Session, paper: ExamPaper, batch: ImportBatch) -> dict:
    passages, seg_by_passage, questions_by_passage, presentation_by_question, _ = (
        _load_batch_content(db, batch.id)
    )
    audio = get_audio(db, paper.playback_audio_id)
    out_passages = []
    for passage in passages:
        questions = questions_by_passage.get(passage.id, [])
        questions.sort(
            key=lambda q: (presentation_by_question.get(q.id).question_no
                           if presentation_by_question.get(q.id) else 0)
        )
        out_questions = [
            {
                "question_no": (presentation_by_question[q.id].question_no
                                if q.id in presentation_by_question else 0),
                "question_id": q.id,
                "question_text": q.question_text,
                "options": _options_for(q, presentation_by_question.get(q.id)),
            }
            for q in questions
        ]
        out_passages.append(
            {
                "passage_id": passage.id,
                "passage_index": passage.passage_index,
                "passage_type": passage.passage_type,
                "topic": passage.topic,
                "questions": out_questions,
            }
        )
    return {
        "exam_paper_id": paper.id,
        "exam_paper_code": paper.exam_paper_code,
        "exam_level": paper.exam_level,
        "exam_year": paper.exam_year,
        "exam_month": paper.exam_month,
        "paper_set": paper.paper_set,
        "content_scope": paper.content_scope,
        "audio_url": f"/api/v1/listening-papers/{paper.id}/audio",
        "duration_ms": audio.duration_ms if audio else None,
        "passages": out_passages,
    }


def assemble_admin_companion(
    db: Session, paper: ExamPaper, batch: ImportBatch | None
) -> dict:
    base = {
        "exam_paper_id": paper.id,
        "exam_paper_code": paper.exam_paper_code,
        "exam_level": paper.exam_level,
        "exam_year": paper.exam_year,
        "exam_month": paper.exam_month,
        "paper_set": paper.paper_set,
        "content_scope": paper.content_scope,
        "audio_url": f"/api/v1/listening-papers/{paper.id}/audio",
        "duration_ms": None,
        "batch_code": None,
        "is_current": False,
        "check_passed": False,
        "is_visible": False,
        "is_pending_confirmation": False,
        "mapping_source": "",
        "review_status": paper.review_status,
        "passages": [],
    }
    audio = get_audio(db, paper.playback_audio_id)
    base["duration_ms"] = audio.duration_ms if audio else None
    if batch is None:
        return base

    check = get_latest_check(db, batch.id)
    visibility = get_visibility(db, batch.id)
    base["batch_code"] = batch.batch_code
    base["is_current"] = batch.is_current
    base["check_passed"] = bool(check and check.is_passed)
    base["is_visible"] = bool(visibility and visibility.is_visible)
    base["is_pending_confirmation"] = bool(
        batch.is_current and not base["is_visible"]
    )

    passages, seg_by_passage, questions_by_passage, presentation_by_question, _ = (
        _load_batch_content(db, batch.id)
    )
    out_passages = []
    for passage in passages:
        questions = questions_by_passage.get(passage.id, [])
        questions.sort(
            key=lambda q: (presentation_by_question.get(q.id).question_no
                           if presentation_by_question.get(q.id) else 0)
        )
        out_questions = []
        for q in questions:
            presentation = presentation_by_question.get(q.id)
            out_questions.append(
                {
                    "question_no": presentation.question_no if presentation else 0,
                    "question_id": q.id,
                    "question_text": q.question_text,
                    "options": _options_for(q, presentation),
                    "correct_option": q.correct_option,
                    "explanation_text": q.explanation_text,
                    "explanation_source": q.explanation_source,
                    "question_index": q.question_index,
                    "content_state": q.content_state,
                    "review_status": q.review_status,
                }
            )
        out_passages.append(
            {
                "passage_id": passage.id,
                "passage_index": passage.passage_index,
                "passage_type": passage.passage_type,
                "topic": passage.topic,
                "scene": passage.scene,
                "accent": passage.accent,
                "review_status": passage.review_status,
                "start_ms": passage.start_ms,
                "body_end_ms": passage.body_end_ms,
                "end_ms": passage.end_ms,
                "segments": [
                    {
                        "segment_id": s.id,
                        "segment_index": s.segment_index,
                        "segment_type": s.segment_type,
                        "text": s.text,
                        "speaker_code": s.speaker_code,
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                    }
                    for s in seg_by_passage.get(passage.id, [])
                ],
                "questions": out_questions,
            }
        )
    base["passages"] = out_passages
    if passages:
        first_presentation = db.scalar(
            select(Presentation).where(Presentation.batch_id == batch.id).limit(1)
        )
        base["mapping_source"] = first_presentation.mapping_source if first_presentation else ""
    return base
