"""Explicitly accept newly assembled source without overwriting prior saved work."""

from app.db import models_processing_workflows as m
from app.module3.contracts import fingerprint
from app.services.processing import library_content as c
from app.services.processing import library_editing as e
from app.services.processing import orchestration as o
from app.services.processing import workflows as w


def adopt_source(db, workflow_id, payload, user_id, settings, key=None):
    if key:
        old, digest, body = w.begin_command(
            db, user_id, "library_source_adopt", key, workflow_id, payload
        )
        if old:
            return old
    paper, workflow, head, current, before = e.context(
        db, workflow_id, lock=key is not None
    )
    e.preconditions(head, before, payload)
    revision = db.get(m.ProcessingWorkflowRevision, head.revision_id)
    source, projection = o.stage_payload(db, revision, "source", settings)
    after = c.canonical_snapshot(c.projection(source))
    for name in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
        "distractor_assessments",
        "language_items",
    ):
        after[name] = []
    issues = c.validate_snapshot(
        after, head.baseline, e.request_for(paper, head.baseline)
    )
    changes = c.differences(before, after)
    effect = c.impact(changes, before, after)
    if not key:
        return {
            "changes": changes,
            "impact": effect,
            "issues": issues,
            "content_hash": fingerprint(after),
        }
    e.available(db, workflow, paper)
    version, _, effect = e.append_save(
        db,
        paper,
        workflow,
        head,
        current,
        before,
        after,
        user_id,
        payload.reason,
        provenance={"type": "SOURCE_ADOPTION", "artifact": projection},
    )
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "library_source_adopt",
        key,
        digest,
        body,
        {
            "save_version_id": str(version.id) if version else None,
            "row_version": head.row_version,
            "impact": effect,
            "issues": issues,
        },
    )
