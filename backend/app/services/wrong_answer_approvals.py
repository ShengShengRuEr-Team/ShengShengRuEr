"""Verify trusted release records against the exact stored explanation."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExplanationApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["student_wrong_answer_detail"]
    field: Literal["explanation_text"]
    import_batch_id: PositiveInt
    attempt_answer_id: PositiveInt
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approved", "denied", "revoked"]
    reviewer: NonBlank
    decision_ref: NonBlank
    decided_at: AwareDatetime
    expires_at: AwareDatetime | None = None


_approvals = TypeAdapter(list[ExplanationApproval])


def is_explanation_approved(
    path: Path | None, *, batch_id: int, answer_id: int, explanation: str
) -> bool:
    if path is None:
        return False
    try:
        records = _approvals.validate_json(path.read_bytes())
    except (OSError, ValidationError):
        return False

    digest = sha256(explanation.encode("utf-8")).hexdigest()
    matches = [
        record
        for record in records
        if record.import_batch_id == batch_id
        and record.attempt_answer_id == answer_id
        and record.sha256 == digest
    ]
    if len(matches) != 1:
        return False
    (record,) = matches
    now = datetime.now(UTC)
    return (
        record.decision == "approved"
        and record.decided_at <= now
        and (record.expires_at is None or now < record.expires_at)
    )
