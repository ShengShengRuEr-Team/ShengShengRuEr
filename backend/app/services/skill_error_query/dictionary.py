"""Build the read-only dictionary payload for skill/error queries."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.repositories import skill_error_query as repo
from app.schemas_skill_error_query import (
    DictionaryData,
    ErrorCauseNode,
    PathNode,
    SkillNode,
)
from app.services.skill_error_query.scope import QueryScope


def _sort_key(display_code: str):
    parts = []
    for piece in display_code.split("."):
        parts.append((0, int(piece)) if piece.isdigit() else (1, piece))
    return tuple(parts)


def _path(
    node_id: int,
    parent_by_id: dict[int, int | None],
    by_id: dict[int, object],
) -> tuple[list[PathNode], int | None, str | None]:
    chain = []
    current = node_id
    seen = set()
    while current is not None and current not in seen:
        seen.add(current)
        node = by_id.get(current)
        if node is None:
            break
        chain.append(
            PathNode(
                code=node.skill_code
                if hasattr(node, "skill_code")
                else node.error_cause_code,
                display_code=node.display_code,
                name=node.skill_name
                if hasattr(node, "skill_name")
                else node.cause_name,
            )
        )
        current = parent_by_id.get(current)
    chain.reverse()
    parent_id = parent_by_id.get(node_id)
    parent = by_id.get(parent_id) if parent_id is not None else None
    parent_code = None
    if parent is not None:
        parent_code = (
            parent.skill_code
            if hasattr(parent, "skill_code")
            else parent.error_cause_code
        )
    return chain, parent_id, parent_code


def build_dictionary(db: Session, scope: QueryScope) -> DictionaryData:
    snapshot = repo.latest_snapshot(db)
    if snapshot is None or snapshot.id != scope.dictionary_snapshot_id:
        # The scope was built in this transaction; a mismatch means the
        # database changed below the transaction and must not be mixed.
        from app.core.errors import AppError

        raise AppError(
            409,
            "词典快照已变化，请刷新后重试",
            error_code="SCOPE_CHANGED",
        )

    skills, errors, taxonomy = repo.load_dictionary_nodes(db, snapshot.id)
    skill_by_id = {row.id: row for row in skills}
    error_by_id = {row.id: row for row in errors}

    skill_parent: dict[int, int | None] = {row.id: None for row in skills}
    for edge in taxonomy:
        if edge.to_skill_id in skill_parent and edge.from_skill_id in skill_by_id:
            # The confirmed taxonomy has one primary parent; keep the first
            # deterministic edge if historical data contains a duplicate.
            if skill_parent[edge.to_skill_id] is None:
                skill_parent[edge.to_skill_id] = edge.from_skill_id

    error_parent: dict[int, int | None] = {
        row.id: row.parent_error_cause_id for row in errors
    }

    skill_counts = repo.count_skill_usage(db, scope.batch_ids)
    error_counts = repo.count_error_usage(db, scope.batch_ids)

    skill_nodes: list[SkillNode] = []
    for row in sorted(skills, key=lambda item: _sort_key(item.display_code)):
        path, parent_id, parent_code = _path(row.id, skill_parent, skill_by_id)
        counts = skill_counts.get(row.id, {})
        leaf = row.skill_level == 3
        skill_nodes.append(
            SkillNode(
                id=row.id,
                code=row.skill_code,
                display_code=row.display_code,
                name=row.skill_name,
                level=row.skill_level,
                parent_id=parent_id,
                parent_code=parent_code,
                path=path,
                definition=row.definition,
                observable_behavior=row.observable_behavior,
                counter_example=row.counter_example,
                usage_scope=row.usage_scope,
                exam_level_scope=row.exam_level_scope,
                status=row.status,
                review_status=row.review_status,
                legacy_codes=row.legacy_codes,
                notes=row.notes,
                question_count=int(counts.get("question", 0)) if leaf else None,
                primary_question_count=int(counts.get("primary", 0)) if leaf else None,
                auxiliary_question_count=int(counts.get("auxiliary", 0))
                if leaf
                else None,
            )
        )

    error_nodes: list[ErrorCauseNode] = []
    for row in sorted(errors, key=lambda item: _sort_key(item.display_code)):
        path, parent_id, parent_code = _path(row.id, error_parent, error_by_id)
        counts = error_counts.get(row.id, {})
        leaf = row.cause_level == 3
        error_nodes.append(
            ErrorCauseNode(
                id=row.id,
                code=row.error_cause_code,
                display_code=row.display_code,
                name=row.cause_name,
                level=row.cause_level,
                parent_id=parent_id,
                parent_code=parent_code,
                path=path,
                definition=row.definition,
                confirmation_rule=row.confirmation_rule,
                boundary_rule=row.boundary_rule,
                maturity=row.maturity,
                status=row.status,
                review_status=row.review_status,
                legacy_codes=row.legacy_codes,
                notes=row.notes,
                question_count=int(counts.get("question", 0)) if leaf else None,
                option_relation_count=(
                    int(counts.get("option_relation", 0)) if leaf else None
                ),
            )
        )

    return DictionaryData(
        dictionary_version=snapshot.version,
        dictionary_snapshot_id=snapshot.id,
        scope_version=scope.scope_version,
        skills=skill_nodes,
        error_causes=error_nodes,
    )


def child_map(nodes: list[SkillNode] | list[ErrorCauseNode]) -> dict[int | None, list]:
    result: dict[int | None, list] = defaultdict(list)
    for node in nodes:
        result[node.parent_id].append(node)
    return dict(result)
