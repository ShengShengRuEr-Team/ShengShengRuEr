"""Initialize a missing local dictionary without replacing an existing snapshot."""

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db import models_annotations as a
from app.db import models_processing as p
from app.db.base import SessionLocal
from app.services.processing.persistence import ensure_dictionary


def initialize_dictionary() -> dict:
    if get_settings().app_env not in {"development", "test"}:
        raise RuntimeError("本地词典初始化仅允许在 development/test 环境运行")
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(3913343199)"))
        snapshot = db.scalar(
            select(p.DictionarySnapshot)
            .order_by(
                p.DictionarySnapshot.created_at.desc(), p.DictionarySnapshot.id.desc()
            )
            .limit(1)
        )
        created = snapshot is None
        if created:
            snapshot = ensure_dictionary(db)
        summary = {
            "snapshot_id": snapshot.id,
            "version": snapshot.version,
            "created": created,
            "skills": db.scalar(
                select(func.count())
                .select_from(a.Skill)
                .where(a.Skill.snapshot_id == snapshot.id)
            ),
            "error_causes": db.scalar(
                select(func.count())
                .select_from(a.ErrorCause)
                .where(a.ErrorCause.snapshot_id == snapshot.id)
            ),
        }
        db.commit()
        return summary


def main() -> None:
    summary = initialize_dictionary()
    state = "已创建" if summary["created"] else "已存在，保持原样"
    print(
        f"词典{state}：snapshot={summary['snapshot_id']}, "
        f"skills={summary['skills']}, error_causes={summary['error_causes']}"
    )


if __name__ == "__main__":
    main()
