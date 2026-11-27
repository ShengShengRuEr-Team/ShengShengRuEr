"""Progress is an observation, never an approval or processing command."""

import json
from types import SimpleNamespace
from uuid import uuid4

from tests.module3.test_workflow_pipeline import pipeline  # noqa: F401


def test_ocr_counts_only_complete_selected_pages(tmp_path):
    from app.services.processing.progress import ocr_progress

    task = SimpleNamespace(id=uuid4(), request={"material_ids": [2]})
    settings = SimpleNamespace(m3_path=lambda _: tmp_path)
    root = tmp_path / str(task.id) / "assembly-documents"
    (root / "page-results").mkdir(parents=True)
    (root / "pages").mkdir()
    manifest = {
        "task_id": str(task.id),
        "files": [{"material_id": 2, "page_numbers": [2, 3, 4]}],
    }
    (root / "input-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "page-results/2-2.json").write_text(
        '{"material_id":2,"page":2}', encoding="utf-8"
    )
    # A partial write and an unrelated page must never inflate completion.
    (root / "page-results/2-3.json").write_text('{"material_id":', encoding="utf-8")
    (root / "page-results/2-99.json").write_text(
        '{"material_id":2,"page":99}', encoding="utf-8"
    )
    (root / "pages/2-3.png").write_bytes(b"synthetic image marker")
    value = ocr_progress(task, settings, set())
    assert value["completed_count"] == 1
    assert value["total_count"] == 3
    assert value["current_item"] == "原件第 3 页"
    assert value["stage"] == "assembly_extract"
    assert str(tmp_path) not in json.dumps(value, default=str)
    assert ocr_progress(task, settings, {"assembly_extract"}) is None
    (root / "extracted.json").write_text("{}", encoding="utf-8")
    assert ocr_progress(task, settings, set()) is None


def test_ocr_progress_rejects_foreign_manifest_and_bad_pages(tmp_path):
    from app.services.processing.progress import ocr_progress

    task = SimpleNamespace(id=uuid4(), request={"material_ids": [2]})
    settings = SimpleNamespace(m3_path=lambda _: tmp_path)
    root = tmp_path / str(task.id) / "documents"
    root.mkdir(parents=True)
    for manifest in (
        {"task_id": str(uuid4()), "files": []},
        {"task_id": str(task.id), "files": [{"material_id": 9, "page_numbers": [1]}]},
        {
            "task_id": str(task.id),
            "files": [{"material_id": 2, "page_numbers": ["../other"]}],
        },
    ):
        (root / "input-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        assert ocr_progress(task, settings, set()) is None


def test_automatic_ocr_page_selection_reports_observed_work_without_a_fake_total(
    tmp_path,
):
    from app.services.processing.progress import ocr_progress

    task = SimpleNamespace(id=uuid4(), request={"material_ids": [2]})
    settings = SimpleNamespace(m3_path=lambda _: tmp_path)
    root = tmp_path / str(task.id) / "documents"
    (root / "reference-pages").mkdir(parents=True)
    (root / "pages").mkdir()
    (root / "input-manifest.json").write_text(
        json.dumps(
            {
                "task_id": str(task.id),
                "files": [{"material_id": 2, "page_numbers": None}],
            }
        ),
        encoding="utf-8",
    )
    for identity, number in [(2, 1), (2, 2), (9, 3), (2, 501)]:
        (root / f"reference-pages/{identity}-{number}.json").write_text(
            json.dumps({"material_id": identity, "page": number}),
            encoding="utf-8",
        )
    (root / "reference-pages/2-3.json").write_text('{"material_id":', encoding="utf-8")
    (root / "reference-pages/2-4.json").write_text(
        '{"material_id":9,"page":4}', encoding="utf-8"
    )
    (root / "pages/2-3.png").write_bytes(b"synthetic render only")
    value = ocr_progress(task, settings, set())
    assert value["completed_count"] == 2
    assert value["total_count"] is None
    assert value["current_item"] == "原件第 3 页"
    assert value["last_progress_at"] is not None
    assert str(tmp_path) not in json.dumps(value, default=str)


def test_mixed_explicit_and_automatic_page_selections_keep_the_total_unknown(tmp_path):
    from app.services.processing.progress import ocr_progress

    task = SimpleNamespace(id=uuid4(), request={"material_ids": [2, 3]})
    settings = SimpleNamespace(m3_path=lambda _: tmp_path)
    root = tmp_path / str(task.id) / "documents"
    (root / "reference-pages").mkdir(parents=True)
    (root / "input-manifest.json").write_text(
        json.dumps(
            {
                "task_id": str(task.id),
                "files": [
                    {"material_id": 2, "page_numbers": [2]},
                    {"material_id": 3, "page_numbers": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    for identity, number in [(2, 2), (2, 99), (3, 4)]:
        (root / f"reference-pages/{identity}-{number}.json").write_text(
            json.dumps({"material_id": identity, "page": number}),
            encoding="utf-8",
        )
    value = ocr_progress(task, settings, set())
    assert value["completed_count"] == 2
    assert value["total_count"] is None
