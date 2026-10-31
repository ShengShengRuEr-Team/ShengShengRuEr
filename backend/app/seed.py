"""开发/测试环境种子数据。

用法（在 backend 目录）：
    python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_NAMES,
    ROLE_PERMISSIONS,
    ROLE_STUDENT,
)
from app.core.security import hash_password
from app.db.base import SessionLocal
from app.db.models import (
    ListeningPaper,
    ListeningQuestion,
    Role,
    RolePermission,
    User,
    UserRole,
)

SEED_USERS = (
    {
        "username": "admin",
        "password": "admin123",
        "nickname": "管理员",
        "role_key": ROLE_ADMIN,
    },
    {
        "username": "student",
        "password": "student123",
        "nickname": "学生",
        "role_key": ROLE_STUDENT,
    },
)

SEED_PAPER = {
    "title": "2025年6月四级听力（占位）",
    "exam_level": "cet4",
    "exam_year": 2025,
    "exam_month": 6,
    "set_no": 1,
    "is_visible": True,
}

SEED_QUESTIONS = (
    {
        "question_no": 1,
        "prompt_text": "What does the man suggest the woman do?",
        "option_a": "Book the train ticket in advance.",
        "option_b": "Take a flight instead.",
        "option_c": "Cancel the trip.",
        "option_d": "Ask her colleague for help.",
        "correct_option": "A",
        "explanation_text": "解析：男士建议女士提前订票，对应选项 A。",
        "transcript_text": (
            "听力原文：W: The train is fully booked. "
            "M: You should book earlier next time."
        ),
    },
    {
        "question_no": 2,
        "prompt_text": "Why is the woman worried about the exam?",
        "option_a": "She missed the review class.",
        "option_b": "She has not prepared enough.",
        "option_c": "The exam room changed.",
        "option_d": "She lost her notes.",
        "correct_option": "B",
        "explanation_text": "解析：女士说自己复习时间不够，对应选项 B。",
        "transcript_text": (
            "听力原文：M: Are you ready for the exam? "
            "W: Not really. I haven't prepared enough."
        ),
    },
)


def _seed_roles(db: Session) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for role_key, permission_codes in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.role_key == role_key))
        if role is None:
            role = Role(role_key=role_key, role_name=ROLE_NAMES[role_key])
            db.add(role)
            db.flush()
        roles[role_key] = role

        for permission_code in sorted(permission_codes):
            exists = db.get(RolePermission, (role.id, permission_code))
            if exists is None:
                db.add(
                    RolePermission(
                        role_id=role.id,
                        permission_code=permission_code,
                    )
                )
    return roles


def _seed_users(db: Session, roles: dict[str, Role]) -> None:
    for item in SEED_USERS:
        user = db.scalar(select(User).where(User.username == item["username"]))
        if user is None:
            user = User(
                username=item["username"],
                password_hash=hash_password(item["password"]),
                nickname=item["nickname"],
                status="active",
            )
            db.add(user)
            db.flush()

        role = roles[item["role_key"]]
        user_role = db.get(UserRole, (user.id, role.id))
        if user_role is None:
            db.add(UserRole(user_id=user.id, role_id=role.id))


def _seed_paper(db: Session) -> ListeningPaper:
    paper = db.scalar(
        select(ListeningPaper).where(ListeningPaper.title == SEED_PAPER["title"])
    )
    if paper is None:
        paper = ListeningPaper(**SEED_PAPER)
        db.add(paper)
        db.flush()

    for item in SEED_QUESTIONS:
        question = db.scalar(
            select(ListeningQuestion).where(
                ListeningQuestion.paper_id == paper.id,
                ListeningQuestion.question_no == item["question_no"],
            )
        )
        if question is None:
            db.add(ListeningQuestion(paper_id=paper.id, **item))
    return paper


def seed() -> dict[str, int]:
    """写入角色、账号、占位试卷与题目；可重复执行。"""

    settings = get_settings()
    if settings.app_env not in ("development", "test"):
        raise RuntimeError("种子数据只允许在 development/test 环境写入默认口令")

    with SessionLocal() as db:
        roles = _seed_roles(db)
        _seed_users(db, roles)
        paper = _seed_paper(db)
        db.commit()
        return {
            "roles": len(roles),
            "users": len(SEED_USERS),
            "paper_id": paper.id,
            "questions": len(SEED_QUESTIONS),
        }


def main() -> None:
    summary = seed()
    print(
        "种子数据完成："
        f"roles={summary['roles']}, users={summary['users']}, "
        f"paper_id={summary['paper_id']}, questions={summary['questions']}"
    )


if __name__ == "__main__":
    main()
