"""作答系统测试数据工厂（自包含，不依赖真实真题文件）。

只允许在 prepared_database 夹具生效后调用：本模块内部延迟 import app.*，
避免 pytest 收集阶段把 engine 绑定到开发库。
"""

from dataclasses import dataclass

OPTION_LETTERS = ("A", "B", "C", "D")

# 本模块创建的试卷 ID；conftest 的 autouse 夹具在每个用例结束后清理，
# 避免污染既有模块二用例依赖的「全库只有一条题目/音频」等历史假设。
_CREATED_PAPER_IDS: list[int] = []


def registry_size() -> int:
    return len(_CREATED_PAPER_IDS)


def cleanup_since(marker: int) -> None:
    """删除 marker 之后创建的试卷及其批次/题目/音频/作答记录。"""

    from sqlalchemy import delete, select

    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_attempt import Attempt, AttemptAnswer, AttemptRejection
    from app.db.models_listening import AudioFile, ExamPaper

    paper_ids = _CREATED_PAPER_IDS[marker:]
    del _CREATED_PAPER_IDS[marker:]
    if not paper_ids:
        return
    storage_root = get_settings().audio_storage_path
    with SessionLocal() as db:
        papers = db.scalars(
            select(ExamPaper).where(ExamPaper.id.in_(paper_ids))
        ).all()
        audio_ids = {
            paper.playback_audio_id for paper in papers if paper.playback_audio_id
        }
        # 作答记录对试卷是 RESTRICT：先按 attempt → answer 顺序清理，再删试卷。
        attempt_ids = list(
            db.scalars(
                select(Attempt.id).where(Attempt.exam_paper_id.in_(paper_ids))
            ).all()
        )
        if attempt_ids:
            db.execute(
                delete(AttemptAnswer).where(
                    AttemptAnswer.attempt_id.in_(attempt_ids)
                )
            )
        db.execute(delete(Attempt).where(Attempt.exam_paper_id.in_(paper_ids)))
        db.execute(
            delete(AttemptRejection).where(
                AttemptRejection.exam_paper_id.in_(paper_ids)
            )
        )
        for paper in papers:
            db.delete(paper)
        db.flush()
        for audio_id in audio_ids:
            audio = db.get(AudioFile, audio_id)
            if audio is None:
                continue
            path = storage_root / audio.storage_key
            if path.is_file():
                path.unlink()
            db.delete(audio)
        db.commit()


@dataclass(frozen=True)
class VisiblePaper:
    paper_id: int
    batch_id: int
    question_ids: tuple[int, ...]
    correct_letters: tuple[str, ...]


def _create_paper(db, *, code: str, question_count: int):
    import hashlib

    from app.core.config import get_settings
    from app.db.models_listening import AudioFile, ExamPaper

    # 提交准入会检查音频文件可读：测试样例落一个小文件，用例结束由 cleanup 删除。
    storage_key = f"{code.lower()}.m4a"
    audio_dir = get_settings().audio_storage_path
    audio_dir.mkdir(parents=True, exist_ok=True)
    payload = b"ssre-test-audio"
    (audio_dir / storage_key).write_bytes(payload)
    audio = AudioFile(
        audio_code=f"{code}_AUDIO",
        storage_key=storage_key,
        duration_ms=5000,
        format="m4a",
        mime_type="audio/mp4",
        file_hash=hashlib.sha256(payload).hexdigest(),
        is_current=True,
    )
    db.add(audio)
    db.flush()
    paper = ExamPaper(
        exam_paper_code=code,
        exam_level="CET4",
        exam_year=2025,
        exam_month=6,
        paper_set=1,
        content_scope="listening",
        playback_audio_id=audio.id,
        expected_question_count=question_count,
        expected_question_count_source={
            "document": "tests/attempt_support.py",
            "sha256": "0" * 64,
            "locator": "自包含测试样例，仅用于接口测试",
        },
        review_status="已通过",
    )
    db.add(paper)
    db.flush()
    return paper


def _add_batch(db, *, paper, batch_code: str, current: bool, correct_letters):
    from app.db.models_listening import (
        ContentCheck,
        ImportBatch,
        PaperVisibility,
        Passage,
        Presentation,
        Question,
    )

    audio_id = paper.playback_audio_id
    batch = ImportBatch(
        exam_paper_id=paper.id,
        audio_id=audio_id,
        batch_code=batch_code,
        status="active",
        is_current=current,
    )
    db.add(batch)
    db.flush()

    passage = Passage(
        batch_id=batch.id,
        exam_paper_id=paper.id,
        audio_id=audio_id,
        passage_code=f"{batch_code}_P1",
        passage_index=1,
        passage_type="长对话",
        topic="测试主题",
        start_ms=0,
        body_end_ms=4000,
        end_ms=5000,
        review_status="已通过",
    )
    db.add(passage)
    db.flush()

    question_ids: list[int] = []
    for index, correct in enumerate(correct_letters, start=1):
        question = Question(
            batch_id=batch.id,
            passage_id=passage.id,
            question_code=f"{batch_code}_Q{index}",
            question_text=f"Question {index}?",
            option_a=f"Option {index} A",
            option_b=f"Option {index} B",
            option_c=f"Option {index} C",
            option_d=f"Option {index} D",
            correct_option=correct,
            explanation_text="测试解析",
            explanation_source="测试",
            content_state="可用",
            review_status="已通过",
        )
        db.add(question)
        db.flush()
        db.add(
            Presentation(
                batch_id=batch.id,
                exam_paper_id=paper.id,
                question_id=question.id,
                question_no=index,
                option_mapping_state="已知",
                mapping_source="测试恒等映射",
                option_letter_mapping={letter: letter for letter in OPTION_LETTERS},
                review_status="已通过",
            )
        )
        question_ids.append(question.id)

    db.add(
        ContentCheck(
            exam_paper_id=paper.id,
            batch_id=batch.id,
            is_passed=True,
            issues=[],
        )
    )
    db.add(
        PaperVisibility(
            exam_paper_id=paper.id,
            batch_id=batch.id,
            is_visible=current,
        )
    )
    db.flush()
    return batch, tuple(question_ids)


def create_visible_paper(
    *, code: str, correct_letters=("A", "B", "C", "D")
) -> VisiblePaper:
    from app.db.base import SessionLocal

    with SessionLocal() as db:
        paper = _create_paper(db, code=code, question_count=len(correct_letters))
        batch, question_ids = _add_batch(
            db,
            paper=paper,
            batch_code=f"{code}_B1",
            current=True,
            correct_letters=correct_letters,
        )
        db.commit()
        _CREATED_PAPER_IDS.append(paper.id)
        return VisiblePaper(
            paper_id=paper.id,
            batch_id=batch.id,
            question_ids=question_ids,
            correct_letters=tuple(correct_letters),
        )


def create_hidden_paper(*, code: str) -> int:
    """有批次但没有可见记录：学生提交/查询都应 404。"""
    from app.db.base import SessionLocal

    with SessionLocal() as db:
        paper = _create_paper(db, code=code, question_count=1)
        _add_batch(
            db,
            paper=paper,
            batch_code=f"{code}_B1",
            current=True,
            correct_letters=("A",),
        )
        # 可见性置 false（_add_batch 跟随 current 写入 true，这里显式关闭）。
        from sqlalchemy import select

        from app.db.models_listening import ImportBatch, PaperVisibility

        batch = db.scalar(
            select(ImportBatch).where(ImportBatch.exam_paper_id == paper.id)
        )
        visibility = db.scalar(
            select(PaperVisibility).where(PaperVisibility.batch_id == batch.id)
        )
        visibility.is_visible = False
        db.commit()
        _CREATED_PAPER_IDS.append(paper.id)
        return paper.id


def create_stale_paper(*, code: str) -> tuple[int, tuple[int, ...], tuple[int, ...]]:
    """返回 (试卷 ID, 旧批次题目 ID, 当前批次题目 ID)。模拟「换批」。"""
    from app.db.base import SessionLocal

    with SessionLocal() as db:
        paper = _create_paper(db, code=code, question_count=4)
        _old_batch, old_ids = _add_batch(
            db,
            paper=paper,
            batch_code=f"{code}_OLD",
            current=False,
            correct_letters=("A", "B", "C", "D"),
        )
        _new_batch, new_ids = _add_batch(
            db,
            paper=paper,
            batch_code=f"{code}_CUR",
            current=True,
            correct_letters=("A", "B", "C", "D"),
        )
        db.commit()
        _CREATED_PAPER_IDS.append(paper.id)
        return paper.id, old_ids, new_ids


def create_student(username: str, password: str = "attempt123") -> int:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.base import SessionLocal
    from app.db.models import Role, User, UserRole

    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.role_key == "student"))
        assert role is not None, "测试库缺少 student 角色种子"
        user = User(
            username=username,
            password_hash=hash_password(password),
            nickname=username,
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        return user.id


def set_visibility(paper_id: int, visible: bool) -> None:
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_listening import ImportBatch, PaperVisibility

    with SessionLocal() as db:
        batch = db.scalar(
            select(ImportBatch).where(
                ImportBatch.exam_paper_id == paper_id,
                ImportBatch.is_current.is_(True),
            )
        )
        assert batch is not None
        visibility = db.scalar(
            select(PaperVisibility).where(PaperVisibility.batch_id == batch.id)
        )
        assert visibility is not None
        visibility.is_visible = visible
        db.commit()
