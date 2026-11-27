"""Read-only skill/error question list and detail assembly."""

from __future__ import annotations

from sqlalchemy import distinct, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models_annotations import (
    ErrorQuestionRelation,
    SkillQuestionRelation,
)
from app.db.models_listening import ImportBatch, Presentation, Question
from app.repositories import listening
from app.repositories import skill_error_query as repo
from app.schemas_skill_error_query import (
    CandidateCauseDetail,
    CandidateCauseSummary,
    CorrectOption,
    DictionaryData,
    ErrorCauseNode,
    ErrorOptionDetail,
    ErrorOptionSummary,
    EvidenceView,
    MatchedLeaf,
    MatchedSkill,
    OptionDisplay,
    PaperDetail,
    PaperOptionRef,
    PaperRef,
    PassageView,
    PersonalError,
    QuestionContent,
    QuestionDetailData,
    QuestionListData,
    QuestionListItem,
    SegmentView,
    SkillDetail,
    SkillNode,
    SkillRoleItem,
    SubjectRef,
    WarningItem,
)
from app.services.skill_error_query.dictionary import build_dictionary
from app.services.skill_error_query.scope import QueryScope

BASE_OPTIONS = ("A", "B", "C", "D")


def _invalid(msg: str) -> AppError:
    return AppError(422, msg, error_code="INVALID_SUBJECT")


def _not_found(msg: str, code: str = "ENTRY_NOT_FOUND") -> AppError:
    return AppError(404, msg, error_code=code)


def _warning(code: str, message: str) -> WarningItem:
    return WarningItem(code=code, message=message)


def _mapping_state(
    presentation: Presentation | None,
) -> tuple[str, dict | None, bool]:
    mapping = presentation.option_letter_mapping if presentation else None
    if not isinstance(mapping, dict):
        return "未知", None, False
    if set(mapping) != set(BASE_OPTIONS):
        return "invalid", None, False
    values = [mapping[letter] for letter in BASE_OPTIONS]
    if any(not isinstance(value, str) for value in values):
        return "invalid", None, False
    if sorted(values) != list(BASE_OPTIONS):
        return "invalid", None, False
    reordered = any(mapping[letter] != letter for letter in BASE_OPTIONS)
    return "已知", mapping, reordered


def _normalize_role(role: str) -> str:
    """Map the API's lower-case role to the database enum value."""

    return "all" if role == "all" else role.upper()


def _matched_leaf(node: SkillNode | ErrorCauseNode) -> MatchedLeaf:
    return MatchedLeaf(
        code=node.code,
        name=node.name,
        display_code=node.display_code,
        question_count=int(node.question_count or 0),
        primary_question_count=(
            int(node.primary_question_count or 0)
            if node.kind == "skill"
            else None
        ),
        auxiliary_question_count=(
            int(node.auxiliary_question_count or 0)
            if node.kind == "skill"
            else None
        ),
        option_relation_count=(
            int(node.option_relation_count or 0)
            if node.kind == "error_cause"
            else None
        ),
    )


def _inverse(mapping: dict) -> dict[str, str]:
    return {value: key for key, value in mapping.items()}


def _option_text(question: Question, base_letter: str) -> str:
    return {
        "A": question.option_a,
        "B": question.option_b,
        "C": question.option_c,
        "D": question.option_d,
    }.get(base_letter, "")


def _answer_state(question: Question) -> str:
    return "available" if question.correct_option in BASE_OPTIONS else "unavailable"


def _sort_leaf(nodes: list[SkillNode] | list[ErrorCauseNode]):
    def key(node):
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in node.display_code.split(".")
        )

    return key


def _resolve_subject(
    dictionary: DictionaryData, subject_type: str, subject_code: str
) -> tuple[SubjectRef, list[MatchedLeaf], list[int], str]:
    if subject_type in {"skill", "skill_category"}:
        nodes = dictionary.skills
        target = next((node for node in nodes if node.code == subject_code), None)
        if target is None:
            raise _not_found("条目不存在或不在当前词典", "ENTRY_NOT_FOUND")
        expected_leaf = subject_type == "skill"
        if expected_leaf and target.level != 3:
            raise _invalid("按技能查询必须使用第三层具体技能")
        if subject_type == "skill_category" and target.level not in {1, 2}:
            raise _invalid("分类查询必须使用一级或二级分类")
        if expected_leaf:
            leaves = [target]
        else:
            candidates = [node for node in nodes if node.level == 3]
            leaves = [
                node
                for node in candidates
                if any(part.code == target.code for part in node.path)
            ]
        return (
            SubjectRef(
                type=subject_type,
                code=target.code,
                name=target.name,
                display_code=target.display_code,
            ),
            [
                _matched_leaf(node)
                for node in leaves
            ],
            [node.id for node in leaves],
            "skill",
        )

    if subject_type in {"error_cause", "error_category"}:
        nodes = dictionary.error_causes
        target = next((node for node in nodes if node.code == subject_code), None)
        if target is None:
            raise _not_found("条目不存在或不在当前词典", "ENTRY_NOT_FOUND")
        if subject_type == "error_cause" and target.level != 3:
            raise _invalid("按错因查询必须使用第三层具体错因")
        if subject_type == "error_category" and target.level not in {1, 2}:
            raise _invalid("分类查询必须使用一级或二级分类")
        if subject_type == "error_cause":
            leaves = [target]
        else:
            candidates = [node for node in nodes if node.level == 3]
            leaves = [
                node
                for node in candidates
                if any(part.code == target.code for part in node.path)
            ]
        return (
            SubjectRef(
                type=subject_type,
                code=target.code,
                name=target.name,
                display_code=target.display_code,
            ),
            [
                _matched_leaf(node)
                for node in leaves
            ],
            [node.id for node in leaves],
            "error_cause",
        )

    raise _invalid("不支持的查询类型")


def _paper_contexts(
    db: Session, scope: QueryScope, questions: dict[int, Question]
) -> dict[int, tuple[Presentation, object, int, bool]]:
    presentations = repo.load_presentations(db, questions, scope.batch_ids)
    audio_ids = []
    for rows in presentations.values():
        for _presentation, paper in rows:
            audio_ids.append(paper.playback_audio_id)
    batch_ids = {question.batch_id for question in questions.values()}
    batches = {
        row.id: row
        for row in db.scalars(
            select(ImportBatch).where(ImportBatch.id.in_(batch_ids))
        ).all()
    }
    for batch in batches.values():
        audio_ids.append(batch.audio_id)
    audio_map = repo.load_audio_rows(db, audio_ids)
    result: dict[int, tuple[Presentation, object, int, bool]] = {}
    for question_id, rows in presentations.items():
        if not rows:
            continue
        question = questions[question_id]
        chosen = None
        if question.source_paper_id is not None:
            chosen = next(
                (row for row in rows if row[1].id == question.source_paper_id), None
            )
        if chosen is None:
            chosen = rows[0]
        batch = batches.get(question.batch_id)
        has_audio = chosen[1].playback_audio_id in audio_map or (
            batch is not None and batch.audio_id in audio_map
        )
        result[question_id] = (chosen[0], chosen[1], len(rows), has_audio)
    return result


def _skill_items(
    db: Session,
    scope: QueryScope,
    dictionary: DictionaryData,
    qids: list[int],
    leaf_ids: set[int],
    role: str,
) -> list[QuestionListItem]:
    questions = repo.load_questions(db, qids)
    contexts = _paper_contexts(db, scope, questions)
    all_skills = repo.load_question_skills(db, qids, scope.batch_ids)
    skill_by_id = {node.id: node for node in dictionary.skills}
    items: list[QuestionListItem] = []
    for qid in qids:
        question = questions.get(qid)
        if question is None or qid not in contexts:
            continue
        presentation, paper, paper_count, has_audio = contexts[qid]
        roles: list[SkillRoleItem] = []
        matched: list[MatchedSkill] = []
        for relation in all_skills.get(qid, []):
            node = skill_by_id.get(relation.skill_id)
            if node is None:
                continue
            roles.append(
                SkillRoleItem(code=node.code, name=node.name, role=relation.role)
            )
            if relation.skill_id in leaf_ids and (
                role == "all" or relation.role == role
            ):
                matched.append(
                    MatchedSkill(code=node.code, name=node.name, role=relation.role)
                )
        warnings: list[WarningItem] = []
        if sum(1 for skill in roles if skill.role == "PRIMARY") > 1:
            warnings.append(
                _warning(
                    "CO_PRIMARY_SKILLS",
                    "该题有多个主要技能（共同主要），需结合各技能证据判断",
                )
            )
        answer_state = _answer_state(question)
        if answer_state == "unavailable":
            warnings.append(
                _warning("ANSWER_UNAVAILABLE", "答案待补齐，无法确认错误选项")
            )
        items.append(
            QuestionListItem(
                question_id=qid,
                question_code=question.question_code,
                question_text=question.question_text,
                paper=PaperRef(
                    exam_paper_id=paper.id,
                    exam_paper_code=paper.exam_paper_code,
                    question_no=presentation.question_no,
                    paper_count=paper_count,
                ),
                has_audio=has_audio,
                answer_state=answer_state,
                matched_skills=matched,
                skills=roles,
                warnings=warnings,
            )
        )
    return items


def _error_items(
    db: Session,
    scope: QueryScope,
    dictionary: DictionaryData,
    qids: list[int],
    leaf_ids: set[int],
) -> list[QuestionListItem]:
    questions = repo.load_questions(db, qids)
    contexts = _paper_contexts(db, scope, questions)
    relations = repo.load_question_errors(db, qids, scope.batch_ids)
    owner_ids = [row.id for rows in relations.values() for row in rows]
    evidence_counts = repo.count_error_evidence(db, owner_ids, scope.batch_ids)
    error_by_id = {node.id: node for node in dictionary.error_causes}
    items: list[QuestionListItem] = []
    for qid in qids:
        question = questions.get(qid)
        if question is None or qid not in contexts:
            continue
        presentation, paper, paper_count, has_audio = contexts[qid]
        mapping_state, mapping, mapping_reordered = _mapping_state(presentation)
        answer_state = _answer_state(question)
        warnings: list[WarningItem] = []
        if answer_state == "unavailable":
            warnings.append(
                _warning(
                    "ANSWER_UNAVAILABLE",
                    "答案待补齐，无法确认错误选项；不展示候选错因组",
                )
            )
        option_groups: dict[str, ErrorOptionSummary] = {}
        for relation in relations.get(qid, []):
            if relation.option_letter not in BASE_OPTIONS:
                warnings.append(
                    _warning("OPTION_LETTER_INVALID", "候选错因的基准选项字母无效")
                )
                continue
            if (
                answer_state == "available"
                and relation.option_letter == question.correct_option
            ):
                warnings.append(
                    _warning(
                        "CANDIDATE_ON_CORRECT_OPTION",
                        "候选错因指向正确选项，已从错误选项组排除",
                    )
                )
                continue
            node = error_by_id.get(relation.error_cause_id)
            if node is None:
                warnings.append(
                    _warning("ERROR_CAUSE_UNAVAILABLE", "候选错因不在当前词典快照中")
                )
                continue
            base_letter = relation.option_letter
            group = option_groups.get(base_letter)
            if group is None:
                if mapping is not None:
                    display = _inverse(mapping).get(base_letter)
                else:
                    display = None
                group = ErrorOptionSummary(
                    base_option_letter=base_letter,
                    display_option_letter=display,
                    option_mapping_state=mapping_state,
                    option_mapping_reordered=mapping_reordered,
                    option_text=_option_text(question, base_letter),
                )
                option_groups[base_letter] = group
            rationale = ""
            if relation.attributes_json:
                rationale = str(
                    relation.attributes_json.get("trigger_mechanism")
                    or relation.attributes_json.get("rationale")
                    or ""
                )
            is_match = relation.error_cause_id in leaf_ids
            group.candidate_causes.append(
                CandidateCauseSummary(
                    code=node.code,
                    name=node.name,
                    rationale=rationale,
                    is_match=is_match,
                    evidence_count=int(evidence_counts.get(relation.id, 0)),
                )
            )
            if is_match:
                group.matched_error_codes.append(node.code)
        # Keep only options that match the requested error cause.
        options = (
            []
            if answer_state == "unavailable"
            else [
                group for group in option_groups.values() if group.matched_error_codes
            ]
        )
        items.append(
            QuestionListItem(
                question_id=qid,
                question_code=question.question_code,
                question_text=question.question_text,
                paper=PaperRef(
                    exam_paper_id=paper.id,
                    exam_paper_code=paper.exam_paper_code,
                    question_no=presentation.question_no,
                    paper_count=paper_count,
                ),
                has_audio=has_audio,
                answer_state=answer_state,
                error_options=options,
                warnings=warnings,
            )
        )
    return items


def _skill_count(
    db: Session, scope: QueryScope, leaf_ids: list[int], role: str
) -> tuple[int, int, int]:
    if not leaf_ids or not scope.batch_ids:
        return 0, 0, 0
    base = (
        select(func.count(distinct(Question.id)))
        .select_from(Question)
        .join(
            SkillQuestionRelation,
            SkillQuestionRelation.question_id == Question.id,
        )
        .where(
            Question.batch_id.in_(scope.batch_ids),
            SkillQuestionRelation.batch_id.in_(scope.batch_ids),
            SkillQuestionRelation.relation_kind == "QUESTION_SKILL",
            SkillQuestionRelation.is_current.is_(True),
            SkillQuestionRelation.skill_id.in_(leaf_ids),
        )
    )
    if role != "all":
        base = base.where(SkillQuestionRelation.role == role)
    total = int(db.scalar(base) or 0)
    role_rows = db.execute(
        select(
            SkillQuestionRelation.role,
            func.count(distinct(SkillQuestionRelation.question_id)),
        )
        .where(
            SkillQuestionRelation.batch_id.in_(scope.batch_ids),
            SkillQuestionRelation.relation_kind == "QUESTION_SKILL",
            SkillQuestionRelation.is_current.is_(True),
            SkillQuestionRelation.skill_id.in_(leaf_ids),
        )
        .group_by(SkillQuestionRelation.role)
    ).all()
    by_role = {row[0]: int(row[1]) for row in role_rows}
    return total, by_role.get("PRIMARY", 0), by_role.get("AUXILIARY", 0)


def _skill_question_ids(
    db: Session,
    scope: QueryScope,
    leaf_ids: list[int],
    role: str,
    cursor: int,
    limit: int,
) -> tuple[list[int], int]:
    from app.db.models_annotations import SkillQuestionRelation

    if not leaf_ids or not scope.batch_ids:
        return [], 0
    base = (
        select(Question.id)
        .join(
            SkillQuestionRelation,
            SkillQuestionRelation.question_id == Question.id,
        )
        .where(
            Question.batch_id.in_(scope.batch_ids),
            SkillQuestionRelation.batch_id.in_(scope.batch_ids),
            SkillQuestionRelation.relation_kind == "QUESTION_SKILL",
            SkillQuestionRelation.is_current.is_(True),
            SkillQuestionRelation.skill_id.in_(leaf_ids),
        )
        .distinct()
    )
    if role != "all":
        base = base.where(SkillQuestionRelation.role == role)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    ids = list(db.scalars(base.order_by(Question.id).offset(cursor).limit(limit)).all())
    return ids, total


def _error_count(
    db: Session, scope: QueryScope, leaf_ids: list[int]
) -> tuple[int, int]:

    if not leaf_ids or not scope.batch_ids:
        return 0, 0
    base = (
        select(
            func.count(distinct(ErrorQuestionRelation.question_id)),
            func.count(
                distinct(
                    tuple_(
                        ErrorQuestionRelation.question_id,
                        ErrorQuestionRelation.option_letter,
                        ErrorQuestionRelation.error_cause_id,
                    )
                )
            ),
        )
        .select_from(ErrorQuestionRelation)
        .where(
            ErrorQuestionRelation.batch_id.in_(scope.batch_ids),
            ErrorQuestionRelation.relation_kind == "QUESTION_ERROR_CANDIDATE",
            ErrorQuestionRelation.is_current.is_(True),
            ErrorQuestionRelation.business_eligible.is_(True),
            ErrorQuestionRelation.option_letter.is_not(None),
            ErrorQuestionRelation.question_id.is_not(None),
            ErrorQuestionRelation.error_cause_id.in_(leaf_ids),
        )
    )
    questions, relations = db.execute(base).one()
    return int(questions or 0), int(relations or 0)


def _error_question_ids(
    db: Session, scope: QueryScope, leaf_ids: list[int], cursor: int, limit: int
) -> tuple[list[int], int]:

    if not leaf_ids or not scope.batch_ids:
        return [], 0
    base = (
        select(Question.id)
        .join(
            ErrorQuestionRelation,
            ErrorQuestionRelation.question_id == Question.id,
        )
        .where(
            Question.batch_id.in_(scope.batch_ids),
            ErrorQuestionRelation.batch_id.in_(scope.batch_ids),
            ErrorQuestionRelation.relation_kind == "QUESTION_ERROR_CANDIDATE",
            ErrorQuestionRelation.is_current.is_(True),
            ErrorQuestionRelation.business_eligible.is_(True),
            ErrorQuestionRelation.option_letter.is_not(None),
            ErrorQuestionRelation.error_cause_id.in_(leaf_ids),
        )
        .distinct()
    )
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    ids = list(db.scalars(base.order_by(Question.id).offset(cursor).limit(limit)).all())
    return ids, total


def list_questions(
    db: Session,
    scope: QueryScope,
    subject_type: str,
    subject_code: str,
    role: str,
    cursor: int,
    limit: int,
) -> QuestionListData:
    dictionary = build_dictionary(db, scope)
    subject, matched_leaves, leaf_ids, kind = _resolve_subject(
        dictionary, subject_type, subject_code
    )
    if kind == "error_cause" and role != "all":
        raise _invalid("错因查询不支持角色筛选")
    if role not in {"all", "primary", "auxiliary"}:
        raise _invalid("角色筛选值不合法")
    db_role = _normalize_role(role)

    if kind == "skill":
        qids, total = _skill_question_ids(
            db, scope, leaf_ids, db_role, cursor, limit
        )
        items = _skill_items(db, scope, dictionary, qids, set(leaf_ids), db_role)
        total_all, primary, auxiliary = _skill_count(db, scope, leaf_ids, db_role)
        # If a role filter is active, question_count is the filtered count;
        # the role buckets remain absolute counts for the UI.
        return QuestionListData(
            scope_version=scope.scope_version,
            subject=subject,
            matched_leaves=matched_leaves,
            question_count=total,
            primary_question_count=primary,
            auxiliary_question_count=auxiliary,
            items=items,
            next_cursor=cursor + limit if cursor + limit < total_all else None,
        )

    qids, total = _error_question_ids(db, scope, leaf_ids, cursor, limit)
    items = _error_items(db, scope, dictionary, qids, set(leaf_ids))
    total_questions, relation_count = _error_count(db, scope, leaf_ids)
    return QuestionListData(
        scope_version=scope.scope_version,
        subject=subject,
        matched_leaves=matched_leaves,
        question_count=total_questions,
        option_relation_count=relation_count,
        items=items,
        next_cursor=cursor + limit if cursor + limit < total_questions else None,
    )


def _paper_detail(
    question: Question,
    presentation: Presentation,
    paper,
    paper_count: int,
    audio,
    batch_id: int,
) -> PaperDetail:
    mapping_state, _, mapping_reordered = _mapping_state(presentation)
    return PaperDetail(
        exam_paper_id=paper.id,
        exam_paper_code=paper.exam_paper_code,
        exam_level=paper.exam_level,
        exam_year=paper.exam_year,
        exam_month=paper.exam_month,
        paper_set=paper.paper_set,
        question_no=presentation.question_no,
        question_index=question.question_index,
        option_mapping_state=mapping_state,
        option_mapping_reordered=mapping_reordered,
        mapping_source=presentation.mapping_source or "",
        audio_url=(
            f"/api/v1/listening-papers/{paper.id}/audio" if audio is not None else None
        ),
        audio_batch_id=batch_id if audio is not None else None,
        duration_ms=audio.duration_ms if audio is not None else None,
        paper_count=paper_count,
    )


def get_question_detail(
    db: Session,
    scope: QueryScope,
    question_id: int,
    exam_paper_id: int | None,
) -> QuestionDetailData:
    question = db.get(Question, question_id)
    if question is None or question.batch_id not in scope.batch_ids:
        raise _not_found("题目不存在或不在当前正式范围", "QUESTION_NOT_FOUND")

    rows = repo.load_presentations(db, [question_id], scope.batch_ids).get(
        question_id, []
    )
    if not rows:
        raise _not_found("题目没有可用试卷映射", "QUESTION_NOT_FOUND")
    if exam_paper_id is not None:
        selected = next((row for row in rows if row[1].id == exam_paper_id), None)
        if selected is None:
            raise _not_found("指定试卷未引用该题", "PAPER_CONTEXT_NOT_FOUND")
    else:
        selected = None
        if question.source_paper_id is not None:
            selected = next(
                (row for row in rows if row[1].id == question.source_paper_id), None
            )
        selected = selected or rows[0]
    presentation, paper = selected
    mapping_state, mapping, _mapping_reordered = _mapping_state(presentation)
    if mapping_state != "已知" or mapping is None:
        raise AppError(
            422,
            "该题选项映射缺失或非法，无法展示答案字母",
            error_code="OPTION_MAPPING_INVALID",
        )

    answer = question.correct_option or ""
    if not answer:
        answer_state = "unavailable"
    elif answer not in BASE_OPTIONS or answer not in mapping.values():
        raise AppError(
            422,
            "答案字母无法按当前试卷映射反查",
            error_code="CORRECT_OPTION_UNMAPPED",
        )
    else:
        answer_state = "available"
    warnings: list[WarningItem] = []
    dictionary = build_dictionary(db, scope)
    dictionary_skill_by_id = {node.id: node for node in dictionary.skills}
    dictionary_error_by_id = {node.id: node for node in dictionary.error_causes}

    inverse = _inverse(mapping)
    options = [
        OptionDisplay(
            display_letter=display,
            base_letter=mapping[display],
            text=_option_text(question, mapping[display]),
        )
        for display in BASE_OPTIONS
    ]
    correct_option = (
        CorrectOption(display_letter=inverse.get(answer), base_letter=answer)
        if answer_state == "available"
        else None
    )

    if answer_state == "unavailable":
        warnings.append(
            _warning(
                "ANSWER_UNAVAILABLE",
                "答案待补齐，无法确认错误选项；不展示候选错因组",
            )
        )

    batch = db.get(ImportBatch, question.batch_id)
    paper_batch = listening.get_current_batch(db, paper.id)
    audio_allowed = paper_batch is not None and paper_batch.id == question.batch_id
    audio_id = (
        paper.playback_audio_id or (batch.audio_id if batch else None)
    ) if audio_allowed else None
    audio = repo.load_audio_rows(db, [audio_id]).get(audio_id) if audio_id else None
    paper_detail = _paper_detail(
        question, presentation, paper, len(rows), audio, question.batch_id
    )

    passage, segments = repo.load_passage(db, question.passage_id, question.batch_id)
    passage_view = None
    if passage is not None:
        passage_view = PassageView(
            passage_id=passage.id,
            passage_index=passage.passage_index,
            passage_type=passage.passage_type,
            topic=passage.topic,
            start_ms=passage.start_ms,
            body_end_ms=passage.body_end_ms,
            end_ms=passage.end_ms,
            segments=[
                SegmentView(
                    segment_id=segment.id,
                    segment_index=segment.segment_index,
                    segment_type=segment.segment_type,
                    text=segment.text,
                    speaker_code=segment.speaker_code,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                )
                for segment in segments
            ],
        )

    answer_evidence = [
        EvidenceView(
            evidence_id=evidence.id,
            text=evidence.evidence_text,
            start_ms=evidence.start_ms,
            end_ms=evidence.end_ms,
            source=evidence.source,
            support_note=(
                (relation.attributes_json or {}).get("support_note")
                if relation.attributes_json
                else None
            ),
        )
        for relation, evidence in repo.load_answer_evidence(
            db, question.id, question.batch_id
        )
    ]

    skill_relations = repo.load_question_skills(db, [question.id], scope.batch_ids).get(
        question.id, []
    )
    owner_ids = [row.id for row in skill_relations]
    skill_evidence = repo.load_skill_evidence(db, owner_ids, scope.batch_ids)
    skills: list[SkillDetail] = []
    for relation in skill_relations:
        node = dictionary_skill_by_id.get(relation.skill_id)
        if node is None:
            warnings.append(_warning("SKILL_UNAVAILABLE", "技能关联不在当前词典快照中"))
            continue
        evidence_rows = skill_evidence.get(relation.id, [])
        skills.append(
            SkillDetail(
                code=node.code,
                name=node.name,
                role=relation.role,
                definition=node.definition,
                evidence=[
                    EvidenceView(
                        evidence_id=evidence.id,
                        text=evidence.evidence_text,
                        start_ms=evidence.start_ms,
                        end_ms=evidence.end_ms,
                        source=evidence.source,
                        support_note=(
                            (relation.attributes_json or {}).get("support_note")
                            if relation.attributes_json
                            else None
                        ),
                    )
                    for relation, evidence in evidence_rows
                ],
            )
        )

    if sum(1 for skill in skills if skill.role == "PRIMARY") > 1:
        warnings.append(
            _warning(
                "CO_PRIMARY_SKILLS",
                "该题有多个主要技能（共同主要），需结合各技能证据判断",
            )
        )

    error_options: list[ErrorOptionDetail] = []
    if answer_state == "available":
        error_relations = repo.load_question_errors(
            db, [question.id], scope.batch_ids
        ).get(question.id, [])
        error_evidence = repo.load_error_evidence(
            db, [relation.id for relation in error_relations], scope.batch_ids
        )
        inverse = _inverse(mapping)
        grouped: dict[str, ErrorOptionDetail] = {}
        for relation in error_relations:
            if relation.option_letter not in BASE_OPTIONS:
                warnings.append(
                    _warning("OPTION_LETTER_INVALID", "候选错因的基准选项字母无效")
                )
                continue
            if relation.option_letter == answer:
                warnings.append(
                    _warning(
                        "CANDIDATE_ON_CORRECT_OPTION",
                        "候选错因指向正确选项，已从错误选项组排除",
                    )
                )
                continue
            node = dictionary_error_by_id.get(relation.error_cause_id)
            if node is None:
                warnings.append(
                    _warning("ERROR_CAUSE_UNAVAILABLE", "候选错因不在当前词典快照中")
                )
                continue
            base_letter = relation.option_letter
            group = grouped.get(base_letter)
            if group is None:
                group = ErrorOptionDetail(
                    display_letter=inverse.get(base_letter),
                    base_letter=base_letter,
                    text=_option_text(question, base_letter),
                    candidate_causes=[],
                )
                grouped[base_letter] = group
            rationale = ""
            if relation.attributes_json:
                rationale = str(
                    relation.attributes_json.get("trigger_mechanism")
                    or relation.attributes_json.get("rationale")
                    or ""
                )
            group.candidate_causes.append(
                CandidateCauseDetail(
                    code=node.code,
                    name=node.name,
                    rationale=rationale,
                    evidence=[
                        EvidenceView(
                            evidence_id=evidence.id,
                            text=evidence.evidence_text,
                            start_ms=evidence.start_ms,
                            end_ms=evidence.end_ms,
                            source=evidence.source,
                            support_note=(
                                (ev_relation.attributes_json or {}).get("support_note")
                                if ev_relation.attributes_json
                                else None
                            ),
                        )
                        for ev_relation, evidence in error_evidence.get(relation.id, [])
                    ],
                )
            )
        error_options = list(grouped.values())

    return QuestionDetailData(
        scope_version=scope.scope_version,
        question=QuestionContent(
            id=question.id,
            code=question.question_code,
            text=question.question_text,
            content_state=question.content_state,
            review_status=question.review_status,
            explanation_text=question.explanation_text,
            explanation_source=question.explanation_source,
        ),
        paper=paper_detail,
        papers=[
            PaperOptionRef(
                exam_paper_id=row_paper.id,
                exam_paper_code=row_paper.exam_paper_code,
                question_no=row_presentation.question_no,
                option_mapping_state=_mapping_state(row_presentation)[0],
                option_mapping_reordered=_mapping_state(row_presentation)[2],
                is_default=(
                    row_presentation.id == presentation.id and row_paper.id == paper.id
                ),
            )
            for row_presentation, row_paper in rows
        ],
        options=options,
        correct_option=correct_option,
        answer_state=answer_state,
        passage=passage_view,
        answer_evidence=answer_evidence,
        skills=skills,
        error_options=error_options,
        personal_error=PersonalError(
            state="not_in_scope",
            message="未确认个人错因（本查询不涉及个人）",
            explanation=(
                "题目候选错因只描述错误选项的可能机制；学生答错某题不等于确认其个人错因；"
                "不得根据作答结果自动生成个人错因；个人错因需在错题本（需求二）按本人作答确认后查看。"
            ),
        ),
        warnings=warnings,
    )
