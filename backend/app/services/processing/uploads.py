"""Reserved streaming uploads with progress leases and commit-time fencing."""

import asyncio
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from sqlalchemy import func, select, update

from app.core.config import BASE_DIR
from app.core.errors import AppError
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.db.base import SessionLocal
from app.db.models_listening import ExamPaper
from app.module3.contracts import controlled_path, file_hash, media_type
from app.services.processing import workflows as w


def selected_upload(db, revision_id, kind, *, lock=False):
    stmt = (
        select(m.ProcessingWorkflowMaterial)
        .join(
            m.ProcessingMaterialSelection,
            m.ProcessingMaterialSelection.upload_id == m.ProcessingWorkflowMaterial.id,
        )
        .where(
            m.ProcessingMaterialSelection.revision_id == revision_id,
            m.ProcessingMaterialSelection.kind == kind,
        )
    )
    if lock:
        stmt = stmt.with_for_update(of=m.ProcessingWorkflowMaterial)
    return db.scalar(stmt.execution_options(populate_existing=True))


def upload_data(row):
    return {
        "upload_id": str(row.id),
        "upload_version": row.upload_version,
        "kind": row.kind,
        "state": row.state,
        "material_id": row.material_id,
        "failure_code": row.failure_code,
    }


def reserve(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "reserve_upload", key, workflow_id, payload
    )
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if revision.materials_frozen_at:
        raise w.conflict("VERSION_CONFLICT", "材料已冻结，请先创建子修订")
    if payload.declared_size > settings.m3_upload_max_bytes:
        raise AppError(422, "文件超过上传上限", error_code="MATERIAL_INVALID")
    name = payload.filename
    extensions = {
        "paper": {".pdf"},
        "answer": {".pdf"},
        "audio": {".m4a", ".mp3", ".wav", ".flac", ".ogg"},
    }
    if (
        PureWindowsPath(name).name != name
        or Path(name).suffix.lower() not in extensions[payload.kind]
    ):
        raise AppError(422, "文件名或格式不支持", error_code="MATERIAL_INVALID")
    current = selected_upload(db, revision.id, payload.kind, lock=True)
    version = current.upload_version if current else 0
    if version != payload.expected_upload_version:
        raise w.conflict(
            "UPLOAD_VERSION_CONFLICT", "该类文件已更新，请读取当前上传状态"
        )
    if current:
        current.state, current.execution_token, current.lease_expires_at = (
            "superseded",
            None,
            None,
        )
        current.updated_at = func.now()
    now = db.scalar(select(func.now()))
    row = m.ProcessingWorkflowMaterial(
        id=uuid4(),
        revision_id=revision.id,
        kind=payload.kind,
        upload_version=version + 1,
        original_filename=name,
        declared_size=payload.declared_size,
        declared_sha256=payload.declared_sha256,
        state="reserved",
        lease_expires_at=now + timedelta(seconds=settings.m3_upload_lease_seconds),
    )
    db.add(row)
    db.flush()
    selection = db.get(m.ProcessingMaterialSelection, (revision.id, payload.kind))
    if selection:
        selection.upload_id = row.id
    else:
        db.add(
            m.ProcessingMaterialSelection(
                revision_id=revision.id, kind=payload.kind, upload_id=row.id
            )
        )
    workflow.row_version += 1
    workflow.updated_at, workflow.updated_by = func.now(), user_id
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "reserve_upload",
        key,
        digest,
        body,
        {**upload_data(row), "row_version": workflow.row_version},
    )


def cancel(db, workflow_id, upload_id, payload, user_id, key):
    action = "cancel_upload"
    old, digest, body = w.begin_command(
        db, user_id, action, key, f"{workflow_id}/{upload_id}", payload.model_copy()
    )
    if old:
        if old.result.get("upload_id") != str(upload_id):
            raise w.conflict("IDEMPOTENCY_CONFLICT", "操作键已用于其他文件")
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    row = db.get(m.ProcessingWorkflowMaterial, upload_id)
    if not row or row.revision_id != revision.id:
        raise AppError(404, "上传记录不存在")
    current = selected_upload(db, revision.id, row.kind, lock=True)
    if (
        not current
        or current.id != row.id
        or row.upload_version != payload.expected_upload_version
        or row.state not in {"reserved", "uploading", "validating"}
    ):
        raise w.conflict("UPLOAD_NOT_WRITABLE", "当前上传不能取消，请读取实际状态")
    row.state, row.execution_token, row.lease_expires_at = "cancelled", None, None
    workflow.row_version += 1
    workflow.updated_at, workflow.updated_by = func.now(), user_id
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        action,
        key,
        digest,
        body,
        {**upload_data(row), "row_version": workflow.row_version},
    )


def fenced_upload(db, workflow_id, revision_id, kind, upload_id, version, token=None):
    workflow = w.get_workflow(db, workflow_id, lock=True)
    revision = db.get(m.ProcessingWorkflowRevision, revision_id)
    row = selected_upload(db, revision_id, kind, lock=True)
    now = db.scalar(select(func.now()))
    if (
        workflow.current_revision_id != revision_id
        or not revision
        or revision.workflow_id != workflow.id
        or revision.materials_frozen_at
        or not row
        or row.id != upload_id
        or row.upload_version != version
    ):
        raise w.conflict("UPLOAD_VERSION_CONFLICT", "当前材料已替换或修订已冻结")
    if row.state not in (
        {"reserved"} if token is None else {"uploading", "validating"}
    ):
        raise w.conflict("UPLOAD_NOT_WRITABLE", "该上传已完成或失效，请读取已有状态")
    if not row.lease_expires_at or row.lease_expires_at <= now:
        raise w.conflict("UPLOAD_EXPIRED", "上传租约已到期，请显式重新预留")
    if token is not None and row.execution_token != token:
        raise w.conflict("LEASE_REVOKED", "旧上传接收权已撤销")
    return workflow, revision, row, now


def renew(
    workflow_id,
    revision_id,
    kind,
    upload_id,
    version,
    token,
    settings,
    validating=False,
):
    with SessionLocal() as db:
        _, _, row, now = fenced_upload(
            db, workflow_id, revision_id, kind, upload_id, version, token
        )
        row.lease_expires_at = now + timedelta(seconds=settings.m3_upload_lease_seconds)
        row.updated_at = now
        if validating:
            row.state = "validating"
        db.commit()


async def validate_file(path, kind, settings, heartbeat):
    interpreter = settings.m3_asr_python if kind == "audio" else settings.m3_ocr_python
    if not interpreter or not Path(interpreter).is_file():
        raise AppError(409, "文件验证环境未配置", error_code="ENVIRONMENT_BLOCKED")
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() != "DATABASE_URL"
        and not k.upper().startswith(("DEEPSEEK", "JWT", "PG"))
    }
    process = await asyncio.create_subprocess_exec(
        interpreter,
        "-m",
        "app.module3.file_validation",
        "--path",
        str(path),
        "--kind",
        kind,
        cwd=BASE_DIR,
        env={**env, "PYTHONIOENCODING": "utf-8"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    communication = asyncio.create_task(process.communicate())
    try:
        for _ in range(max(1, 600 // settings.m3_upload_heartbeat_seconds)):
            done, _ = await asyncio.wait(
                {communication}, timeout=settings.m3_upload_heartbeat_seconds
            )
            if done:
                stdout, _ = communication.result()
                if process.returncode or not json.loads(stdout).get("valid"):
                    raise AppError(
                        422,
                        "文件损坏、加密或无法完整解码",
                        error_code="MATERIAL_INVALID",
                    )
                return
            await heartbeat()
        raise AppError(422, "文件验证超时", error_code="MATERIAL_INVALID")
    finally:
        if process.returncode is None:
            process.kill()
        await communication


async def receive(
    request, workflow_id, revision_id, kind, upload_id, version, user_id, settings
):
    token = uuid4()
    with SessionLocal() as db:
        _, _, row, now = fenced_upload(
            db, workflow_id, revision_id, kind, upload_id, version
        )
        declared_size, declared_hash = row.declared_size, row.declared_sha256
        row.state, row.execution_token = "uploading", token
        row.lease_expires_at = now + timedelta(seconds=settings.m3_upload_lease_seconds)
        filename = row.original_filename
        db.commit()
    root = settings.m3_path("m3_materials_dir")
    staging = root / ".receiving"
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"{upload_id}-{token}.part"
    size, digest, last_progress = 0, hashlib.sha256(), asyncio.get_running_loop().time()

    async def heartbeat(validating=False):
        await asyncio.to_thread(
            renew,
            workflow_id,
            revision_id,
            kind,
            upload_id,
            version,
            token,
            settings,
            validating,
        )

    try:
        with path.open("xb") as output:
            iterator = request.stream().__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        iterator.__anext__(), timeout=settings.m3_upload_lease_seconds
                    )
                except StopAsyncIteration:
                    break
                size += len(chunk)
                if size > settings.m3_upload_max_bytes or size > declared_size:
                    raise AppError(
                        422, "文件实际大小超出声明或上限", error_code="MATERIAL_INVALID"
                    )
                digest.update(chunk)
                output.write(chunk)
                if (
                    chunk
                    and asyncio.get_running_loop().time() - last_progress
                    >= settings.m3_upload_heartbeat_seconds
                ):
                    await heartbeat()
                    last_progress = asyncio.get_running_loop().time()
        sha = digest.hexdigest()
        if size != declared_size or (declared_hash and sha != declared_hash):
            raise AppError(422, "文件大小或哈希不匹配", error_code="MATERIAL_INVALID")
        await heartbeat(True)
        await validate_file(path, kind, settings, heartbeat)
        # A short lock covers only local content publication and registration.
        # A receiver replaced during validation cannot publish or register late.
        with SessionLocal() as db:
            workflow, revision, row, _ = fenced_upload(
                db, workflow_id, revision_id, kind, upload_id, version, token
            )
            key = f"objects/{workflow_id}/{sha}{Path(filename).suffix.lower()}"
            target = controlled_path(root, key, must_exist=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if file_hash(target) != sha:
                    raise AppError(
                        409, "内容寻址文件完整性异常", error_code="ARTIFACT_CHANGED"
                    )
            else:
                # Atomic link fails rather than replacing any existing object.
                os.link(path, target)
            paper = (
                db.get(ExamPaper, workflow.exam_paper_id)
                if workflow.exam_paper_id
                else None
            )
            code = (
                paper.exam_paper_code
                if paper
                else (
                    f"{workflow.exam_level}_{workflow.exam_year}_"
                    f"{workflow.exam_month}_{workflow.paper_set}"
                )
            )
            source_kind = (
                ("paper_" + revision.document_mode)
                if kind == "paper"
                else ("answer_explanation" if kind == "answer" else "audio")
            )
            material = db.scalar(
                select(p.MaterialSource).where(
                    p.MaterialSource.storage_key == key,
                    p.MaterialSource.source_kind == source_kind,
                    p.MaterialSource.sha256 == sha,
                )
            )
            if material is None:
                material = p.MaterialSource(
                    exam_paper_code=code,
                    source_kind=source_kind,
                    storage_key=key,
                    sha256=sha,
                    size_bytes=size,
                    media_type=media_type(target),
                    source_locator=f"workflow:{workflow_id};upload:{upload_id}",
                    registered_by=user_id,
                )
                db.add(material)
                db.flush()
            row.material_id, row.actual_size, row.actual_sha256 = material.id, size, sha
            row.state, row.execution_token, row.lease_expires_at = "ready", None, None
            row.updated_at = func.now()
            workflow.row_version += 1
            workflow.updated_at, workflow.updated_by = func.now(), user_id
            result = {**upload_data(row), "row_version": workflow.row_version}
            db.commit()
            return result
    except BaseException as error:
        with SessionLocal() as db:
            db.execute(
                update(m.ProcessingWorkflowMaterial)
                .where(
                    m.ProcessingWorkflowMaterial.id == upload_id,
                    m.ProcessingWorkflowMaterial.execution_token == token,
                )
                .values(
                    state="failed",
                    failure_code=getattr(error, "error_code", None)
                    or "UPLOAD_INTERRUPTED",
                    execution_token=None,
                    lease_expires_at=None,
                    updated_at=func.now(),
                )
            )
            db.commit()
        # Keep uncertain published files for recovery; never remove a reusable
        # content object after an ambiguous commit. Only this receiver's staging
        # path is removed here.
        raise
    finally:
        path.unlink(missing_ok=True)


def expire_uploads(db):
    now = db.scalar(select(func.now()))
    rows = db.scalars(
        select(m.ProcessingWorkflowMaterial)
        .where(
            m.ProcessingWorkflowMaterial.state.in_(
                ["reserved", "uploading", "validating"]
            ),
            m.ProcessingWorkflowMaterial.lease_expires_at <= now,
        )
        .order_by(m.ProcessingWorkflowMaterial.id)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.state, row.failure_code = "failed", "UPLOAD_EXPIRED"
        row.execution_token, row.lease_expires_at, row.updated_at = None, None, now
    db.flush()
    return len(rows)


def recover_uploads():
    """Expire abandoned receivers and remove only their old owned staging files."""
    import re
    import time
    from uuid import UUID

    from app.core.config import get_settings

    settings = get_settings()
    with SessionLocal() as db:
        expire_uploads(db)
        db.commit()
        directory = settings.m3_path("m3_materials_dir") / ".receiving"
        if not directory.is_dir() or directory.is_symlink():
            return
        root = directory.resolve()
        for path in directory.glob("*.part"):
            match = re.fullmatch(r"([0-9a-f-]{36})-([0-9a-f-]{36})\.part", path.name)
            if (
                not match
                or path.is_symlink()
                or not path.resolve().is_relative_to(root)
                or time.time() - path.stat().st_mtime
                < settings.m3_upload_lease_seconds * 2
            ):
                continue
            row = db.get(m.ProcessingWorkflowMaterial, UUID(match[1]))
            if (
                row
                and row.state in {"uploading", "validating"}
                and str(row.execution_token) == match[2]
            ):
                continue
            path.unlink(missing_ok=True)
