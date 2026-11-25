"""Formal, read-only query scope for skill/error queries."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db import models_processing as p
from app.db.models_listening import ImportBatch
from app.repositories.annotations import current_annotations

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryScope:
    batch_ids: tuple[int, ...]
    batch_hashes: tuple[tuple[int, str], ...]
    dictionary_snapshot_id: int
    scope_version: str


def begin_read_snapshot(db: Session) -> None:
    """Start a repeatable-read, read-only transaction.

    The caller must invoke this before the first query of the request. All
    scope, dictionary, list and detail reads then share one PostgreSQL
    snapshot, so a batch switch cannot mix two versions in one response.
    """

    if db.in_transaction():
        # Authentication runs on the same request-scoped session and has
        # already opened a read transaction. It is safe to discard that
        # transaction before starting the consistent read snapshot.
        db.rollback()
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))


def latest_snapshot(db: Session) -> p.DictionarySnapshot | None:
    return db.scalar(
        select(p.DictionarySnapshot)
        .order_by(
            p.DictionarySnapshot.created_at.desc(), p.DictionarySnapshot.id.desc()
        )
        .limit(1)
    )


def _scope_version(batches: list[tuple[int, str]], snapshot_id: int) -> str:
    payload = "\n".join(
        f"{batch_id}:{result_hash}" for batch_id, result_hash in batches
    )
    payload += f"|dictionary:{snapshot_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_scope(db: Session) -> QueryScope:
    """Build the current formal scope using the same gate as annotations."""

    snapshot = latest_snapshot(db)
    if snapshot is None:
        raise AppError(
            503,
            "词典快照尚未初始化，请先完成数据库初始化",
            error_code="DICTIONARY_NOT_READY",
        )

    batches = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.is_current.is_(True), ImportBatch.status == "active")
        .order_by(ImportBatch.id)
    ).all()

    formal: list[tuple[int, str]] = []
    for batch in batches:
        try:
            state = current_annotations(db, batch.exam_paper_id, batch.id, 0, 1)
        except AppError as exc:
            if exc.status_code == 409:
                logger.warning(
                    "skip non-formal batch %s for query scope: %s",
                    batch.id,
                    exc.msg,
                )
                continue
            raise
        if state.get("annotation_state") != "approved":
            logger.info(
                "skip batch %s with annotation_state=%s",
                batch.id,
                state.get("annotation_state"),
            )
            continue
        formal.append((batch.id, str(batch.result_hash or "")))

    formal_sorted = sorted(formal, key=lambda item: item[0])
    return QueryScope(
        batch_ids=tuple(item[0] for item in formal_sorted),
        batch_hashes=tuple(formal_sorted),
        dictionary_snapshot_id=snapshot.id,
        scope_version=_scope_version(formal_sorted, snapshot.id),
    )


def check_expected_scope(
    scope: QueryScope, expected_scope_version: str | None, *, cursor: int = 0
) -> None:
    if cursor > 0 and not expected_scope_version:
        raise AppError(
            422,
            "翻页必须携带首次查询返回的 scope_version",
            error_code="SCOPE_REQUIRED",
        )
    if expected_scope_version and expected_scope_version != scope.scope_version:
        raise AppError(
            409,
            "查询范围已变化，请整体刷新",
            error_code="SCOPE_CHANGED",
            context={"scope_version": scope.scope_version},
        )
