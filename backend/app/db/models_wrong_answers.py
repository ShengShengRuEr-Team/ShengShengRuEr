"""Personal notebook state keyed by the original graded answer."""

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WrongAnswerDismissal(Base):
    __tablename__ = "wrong_answer_dismissals"

    answer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("attempt_answers.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )
