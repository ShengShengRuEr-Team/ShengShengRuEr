"""Personal notebook state keyed by the original graded answer."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WrongAnswerState(Base):
    __tablename__ = "wrong_answer_states"
    __table_args__ = (
        CheckConstraint(
            "learning_status IN ('pending', 'mastered')", name="learning_status"
        ),
    )

    answer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("attempt_answers.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )
    learning_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
