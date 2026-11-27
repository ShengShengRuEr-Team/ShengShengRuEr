"""Library editing uses the existing paper and workflow identities."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.config import Settings, get_settings
from app.core.errors import ok
from app.db.base import get_db
from app.schemas_library import (
    AdoptCandidates,
    ArchivePaper,
    EditOpen,
    GenerateCandidates,
    ManualAnnotation,
    PaperCreate,
    PrepareReview,
    RestoreDraft,
    SaveDraft,
)
from app.services.processing import library_annotations as annotations
from app.services.processing import library_candidates as candidates
from app.services.processing import library_editing as editing
from app.services.processing import library_papers as papers
from app.services.processing import library_review as review
from app.services.processing import library_versions as versions
from app.services.processing.workflows import command_data

router = APIRouter(tags=["题库编辑与版本"])
Admin = Annotated[CurrentUser, Depends(require_admin)]
Database = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
W = "/admin/processing-workflows/{workflow_id}"
P = "/admin/listening-papers/{exam_paper_id}"


@router.get("/admin/library-providers")
def library_providers(user: Admin, settings: Config):
    from app.module3.providers import availability

    return ok(availability(settings))


@router.get("/admin/library-dictionary")
def library_dictionary(user: Admin):
    from app.services.processing.validation import load_dictionary

    tables = {t["name"]: t["rows"] for t in load_dictionary()["tables"]}
    return ok(
        {
            "skills": [
                {"code": r["skill_code"], "name": r["skill_name"]}
                for r in tables["skill"]
                if r.get("skill_level") == 3
                and r.get("status") == "启用"
                and r.get("usage_scope") == "题目标注"
            ],
            "errors": [
                {"code": r["error_cause_code"], "name": r["cause_name"]}
                for r in tables["error_cause"]
                if r.get("cause_level") == 3 and r.get("status") == "启用"
            ],
        }
    )


@router.get("/admin/listening-papers")
def list_papers(
    user: Admin,
    db: Database,
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    exam_level: str | None = Query(None, pattern="^CET[46]$"),
    exam_year: int | None = Query(None, ge=1980, le=2200),
    exam_month: int | None = Query(None, ge=1, le=12),
    paper_set: int | None = Query(None, ge=1, le=3),
    archived: bool = False,
    keyword: str | None = Query(None, max_length=100),
    processing_state: str | None = Query(None, max_length=32),
    review_state: str | None = Query(None, max_length=32),
    visible: bool | None = None,
):
    return ok(
        papers.list_papers(
            db,
            page=page,
            page_size=page_size,
            exam_level=exam_level,
            exam_year=exam_year,
            exam_month=exam_month,
            paper_set=paper_set,
            archived=archived,
            keyword=keyword,
            processing_state=processing_state,
            review_state=review_state,
            visible=visible,
        )
    )


@router.post("/admin/listening-papers", status_code=201)
def create_paper(payload: PaperCreate, user: Admin, db: Database, key: Key):
    return ok(command_data(editing.create(db, payload, user.id, key)), "已登记试卷")


@router.post(P + "/edit-draft")
def open_draft(
    exam_paper_id: int,
    payload: EditOpen,
    user: Admin,
    db: Database,
    key: Key,
    settings: Config,
):
    return ok(
        command_data(
            editing.open_draft(db, exam_paper_id, payload, user.id, key, settings)
        )
    )


@router.get(W + "/edit-draft")
def get_draft(
    workflow_id: UUID, user: Admin, db: Database, save_version_id: UUID | None = None
):
    return ok(
        versions.detail(db, workflow_id, save_version_id)
        if save_version_id
        else editing.draft_data(db, workflow_id)
    )


@router.post(W + "/edit-draft/preview")
def preview_draft(workflow_id: UUID, payload: SaveDraft, user: Admin, db: Database):
    return ok(editing.preview(db, workflow_id, payload))


@router.put(W + "/edit-draft")
def save_draft(
    workflow_id: UUID, payload: SaveDraft, user: Admin, db: Database, key: Key
):
    return ok(
        command_data(editing.save(db, workflow_id, payload, user.id, key)),
        "草稿已保存，正式批次尚未切换",
    )


@router.get(W + "/versions")
def list_versions(
    workflow_id: UUID,
    user: Admin,
    db: Database,
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(versions.versions(db, workflow_id, page, page_size))


@router.get(W + "/versions/{version_id}")
def version_detail(workflow_id: UUID, version_id: UUID, user: Admin, db: Database):
    return ok(versions.detail(db, workflow_id, version_id))


@router.get(W + "/versions/{version_id}/diff")
def version_diff(
    workflow_id: UUID,
    version_id: UUID,
    user: Admin,
    db: Database,
    against_version_id: UUID | None = None,
):
    return ok(versions.diff(db, workflow_id, version_id, against_version_id))


@router.post(W + "/source-adoption-preview")
def preview_source_adoption(
    workflow_id: UUID,
    payload: PrepareReview,
    user: Admin,
    db: Database,
    settings: Config,
):
    from app.services.processing.library_source_adoption import adopt_source

    return ok(adopt_source(db, workflow_id, payload, user.id, settings))


@router.post(W + "/source-adoptions")
def source_adoption(
    workflow_id: UUID,
    payload: PrepareReview,
    user: Admin,
    db: Database,
    key: Key,
    settings: Config,
):
    from app.services.processing.library_source_adoption import adopt_source

    return ok(
        command_data(adopt_source(db, workflow_id, payload, user.id, settings, key))
    )


@router.post(W + "/candidate-generations", status_code=202)
def generate_candidates(
    workflow_id: UUID,
    payload: GenerateCandidates,
    user: Admin,
    db: Database,
    key: Key,
    settings: Config,
):
    from app.services.processing.library_generation import generate

    return ok(command_data(generate(db, workflow_id, payload, user.id, key, settings)))


@router.post(W + "/prepare-source-review")
def prepare_source(
    workflow_id: UUID,
    payload: PrepareReview,
    user: Admin,
    db: Database,
    key: Key,
    settings: Config,
):
    return ok(
        command_data(review.prepare(db, workflow_id, payload, user.id, key, settings))
    )


@router.post(W + "/prepare-final-review")
def prepare_final(
    workflow_id: UUID,
    payload: PrepareReview,
    user: Admin,
    db: Database,
    key: Key,
    settings: Config,
):
    return ok(
        command_data(
            review.prepare(db, workflow_id, payload, user.id, key, settings, final=True)
        )
    )


@router.post(W + "/manual-annotations")
def manual_annotation(
    workflow_id: UUID, payload: ManualAnnotation, user: Admin, db: Database, key: Key
):
    return ok(
        command_data(annotations.manual_save(db, workflow_id, payload, user.id, key))
    )


@router.get(W + "/candidates")
def list_candidates(workflow_id: UUID, user: Admin, db: Database):
    return ok(candidates.candidates(db, workflow_id))


@router.post(W + "/candidate-adoption-preview")
def adoption_preview(
    workflow_id: UUID,
    payload: AdoptCandidates,
    user: Admin,
    db: Database,
    settings: Config,
):
    return ok(candidates.adopt(db, workflow_id, payload, user.id, settings))


@router.post(W + "/candidate-adoptions")
def adopt_candidates(
    workflow_id: UUID,
    payload: AdoptCandidates,
    user: Admin,
    db: Database,
    settings: Config,
    key: Key,
):
    return ok(
        command_data(candidates.adopt(db, workflow_id, payload, user.id, settings, key))
    )


@router.post(W + "/restore-preview")
def preview_restore(
    workflow_id: UUID, payload: RestoreDraft, user: Admin, db: Database
):
    return ok(versions.restore(db, workflow_id, payload, user.id))


@router.post(W + "/restores")
def restore_draft(
    workflow_id: UUID, payload: RestoreDraft, user: Admin, db: Database, key: Key
):
    return ok(
        command_data(versions.restore(db, workflow_id, payload, user.id, key)),
        "已追加回退版本，须重新审核",
    )


@router.post(P + "/archive-preview")
def archive_preview(exam_paper_id: int, user: Admin, db: Database):
    return ok(papers.archive_preview(db, exam_paper_id))


@router.post(P + "/archive")
def archive_paper(
    exam_paper_id: int, payload: ArchivePaper, user: Admin, db: Database, key: Key
):
    return ok(
        command_data(papers.archive(db, exam_paper_id, payload, user.id, key)),
        "已移入回收站",
    )


@router.post(P + "/restore")
def restore_paper(
    exam_paper_id: int, payload: ArchivePaper, user: Admin, db: Database, key: Key
):
    return ok(
        command_data(
            papers.archive(db, exam_paper_id, payload, user.id, key, restore=True)
        ),
        "已恢复，须重新独立开放",
    )
