"""准备独立的 E2E 数据库与三套可见试卷（仅用于真实链路验收）。

用法（在 backend 目录，DATABASE_URL 必须指向名称含 e2e 的独立库）：

    $env:DATABASE_URL="postgresql+psycopg://...@127.0.0.1:5433/shengshengruer_e2e"
    .\\venv\\Scripts\\python.exe scripts\\e2e_attempt_setup.py

脚本会：建库（若不存在）→ alembic upgrade head → seed → 创建/重置
E2E_ATTEMPT_001/002/003（各 2 篇 4 题、WAV 音频、内容检查通过与可见记录），
并创建 E2E 第二学生 e2e_student_b（用于学生隔离验收）。
不会写入开发库/测试库；数据库名不含 e2e 时直接拒绝。
"""

import hashlib
import json
import os
import struct
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

PAPERS = (
    {"code": "E2E_ATTEMPT_001", "paper_set": 1, "audio_code": "E2E_ATTEMPT_AUDIO_1"},
    {"code": "E2E_ATTEMPT_002", "paper_set": 2, "audio_code": "E2E_ATTEMPT_AUDIO_2"},
    {"code": "E2E_ATTEMPT_003", "paper_set": 3, "audio_code": "E2E_ATTEMPT_AUDIO_3"},
)
SECOND_STUDENT = {"username": "e2e_student_b", "password": "student123"}


def _wav_bytes(duration_ms: int = 1000, sample_rate: int = 8000) -> bytes:
    frames = int(sample_rate * duration_ms / 1000)
    data = b"".join(struct.pack("<h", 0) for _ in range(frames))
    byte_rate = sample_rate * 2
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, byte_rate, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
    )
    return header + data


def _ensure_database(e2e_url: str) -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(e2e_url)
    if not url.database or "e2e" not in url.database.lower():
        raise RuntimeError("DATABASE_URL 必须指向名称含 e2e 的独立数据库")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                quoted = url.database.replace('"', '""')
                connection.execute(text(f'CREATE DATABASE "{quoted}"'))
    finally:
        admin.dispose()


def _run_migrations(e2e_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", e2e_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _create_visible_paper(
    *, code: str, paper_set: int, audio_code: str
) -> dict:
    from sqlalchemy import delete, select

    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models import User
    from app.db.models_listening import (
        AudioFile,
        ContentCheck,
        ExamPaper,
        ImportBatch,
        PaperVisibility,
        Passage,
        Presentation,
        Question,
    )

    settings = get_settings()
    audio_dir = settings.audio_storage_path
    audio_dir.mkdir(parents=True, exist_ok=True)
    storage_key = f"{code.lower()}.wav"
    audio_path = audio_dir / storage_key
    audio_path.write_bytes(_wav_bytes())
    file_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()

    with SessionLocal() as db:
        existing = db.scalar(select(ExamPaper).where(ExamPaper.exam_paper_code == code))
        if existing is not None:
            # 先清作答记录（RESTRICT FK），再删试卷（子表 DB 级 CASCADE）。
            from app.db.models_attempt import Attempt, AttemptAnswer

            attempt_ids = list(
                db.scalars(
                    select(Attempt.id).where(Attempt.exam_paper_id == existing.id)
                ).all()
            )
            if attempt_ids:
                db.execute(
                    delete(AttemptAnswer).where(
                        AttemptAnswer.attempt_id.in_(attempt_ids)
                    )
                )
            db.execute(delete(Attempt).where(Attempt.exam_paper_id == existing.id))
            db.execute(delete(ExamPaper).where(ExamPaper.id == existing.id))
            db.commit()

        audio = db.scalar(select(AudioFile).where(AudioFile.audio_code == audio_code))
        if audio is None:
            audio = AudioFile(
                audio_code=audio_code,
                storage_provider="local",
                storage_key=storage_key,
                duration_ms=1000,
                format="wav",
                mime_type="audio/wav",
                file_hash=file_hash,
                is_current=True,
            )
            db.add(audio)
        else:
            audio.storage_key = storage_key
            audio.duration_ms = 1000
            audio.file_hash = file_hash
            audio.mime_type = "audio/wav"
            audio.format = "wav"
        db.flush()

        paper = ExamPaper(
            exam_paper_code=code,
            exam_level="CET4",
            exam_year=2026,
            exam_month=11,
            paper_set=paper_set,
            content_scope="listening",
            playback_audio_id=audio.id,
            expected_question_count=4,
            expected_question_count_source={
                "document": "e2e_attempt_setup.py",
                "sha256": "0" * 64,
                "locator": "E2E 专用自包含样例，不代表真实真题",
            },
            review_status="已通过",
        )
        db.add(paper)
        db.flush()

        batch = ImportBatch(
            exam_paper_id=paper.id,
            audio_id=audio.id,
            batch_code=f"{code}_B1",
            status="active",
            is_current=True,
        )
        db.add(batch)
        db.flush()

        correct = ["A", "B", "C", "D"]
        question_no = 0
        for passage_index in (1, 2):
            passage = Passage(
                batch_id=batch.id,
                exam_paper_id=paper.id,
                audio_id=audio.id,
                passage_code=f"{code}_P{passage_index}",
                passage_index=passage_index,
                passage_type="长对话" if passage_index == 1 else "短文",
                topic=f"{code} 第 {passage_index} 篇",
                start_ms=0,
                body_end_ms=800,
                end_ms=1000,
                review_status="已通过",
            )
            db.add(passage)
            db.flush()
            for _ in range(2):
                question_no += 1
                question = Question(
                    batch_id=batch.id,
                    passage_id=passage.id,
                    question_code=f"{code}_Q{question_no}",
                    question_text=f"{code} 第 {question_no} 题",
                    option_a=f"Question {question_no} option A",
                    option_b=f"Question {question_no} option B",
                    option_c=f"Question {question_no} option C",
                    option_d=f"Question {question_no} option D",
                    correct_option=correct[question_no - 1],
                    explanation_text="E2E 解析",
                    explanation_source="E2E",
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
                        question_no=question_no,
                        option_mapping_state="已知",
                        mapping_source="E2E 恒等映射",
                        option_letter_mapping={"A": "A", "B": "B", "C": "C", "D": "D"},
                        review_status="已通过",
                    )
                )
        db.add(
            ContentCheck(
                exam_paper_id=paper.id,
                batch_id=batch.id,
                is_passed=True,
                issues=[],
            )
        )
        admin = db.scalar(select(User).where(User.username == "admin"))
        db.add(
            PaperVisibility(
                exam_paper_id=paper.id,
                batch_id=batch.id,
                is_visible=True,
                confirmed_by=admin.id if admin else None,
            )
        )
        db.commit()
        return {
            "paper_id": paper.id,
            "paper_code": code,
            "paper_set": paper_set,
            "audio_path": str(audio_path),
            "question_count": 4,
        }


def _ensure_second_student() -> int:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.base import SessionLocal
    from app.db.models import Role, User, UserRole

    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.role_key == "student"))
        assert role is not None, "种子数据缺少 student 角色"
        user = db.scalar(
            select(User).where(User.username == SECOND_STUDENT["username"])
        )
        if user is None:
            user = User(
                username=SECOND_STUDENT["username"],
                password_hash=hash_password(SECOND_STUDENT["password"]),
                nickname=SECOND_STUDENT["username"],
                status="active",
            )
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            db.commit()
        return int(user.id)


def main() -> None:
    e2e_url = os.getenv("DATABASE_URL")
    if not e2e_url:
        raise RuntimeError("请先设置 DATABASE_URL 指向独立 E2E 数据库")
    _ensure_database(e2e_url)
    os.environ["APP_ENV"] = "development"
    os.environ["DATABASE_URL"] = e2e_url
    _run_migrations(e2e_url)

    from app.seed import seed

    seed()
    papers = [
        _create_visible_paper(
            code=item["code"],
            paper_set=item["paper_set"],
            audio_code=item["audio_code"],
        )
        for item in PAPERS
    ]
    second_student_id = _ensure_second_student()
    print(
        json.dumps(
            {
                "papers": papers,
                "second_student": {
                    "id": second_student_id,
                    **SECOND_STUDENT,
                },
                "database": e2e_url.rsplit("/", 1)[-1],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
