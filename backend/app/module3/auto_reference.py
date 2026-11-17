"""Prepare fixed source sentences directly from registered PDF/audio materials."""

from app.module3.contracts import ProcessingError
from app.module3.document_reference import paper_structure, parse_groups, split_groups
from app.module3.reference_locator import locate
from app.schemas_processing import ReferenceSegment


def prepare(extracted, materials, normalized, settings, output):
    structure = paper_structure(extracted["pages"])
    for group in structure["groups"]:
        material = next(
            m for m in materials if m["material_id"] == group["source_material_id"]
        )
        group.update(
            source_storage_key=material["storage_key"], source_sha256=material["sha256"]
        )
    groups = parse_groups(extracted["pages"], structure, materials)
    rows = split_groups(groups, settings.nltk_data)
    if not rows:
        raise ProcessingError("REFERENCE_TEXT_REQUIRED", "原件中没有完整听力原文")
    located = locate(normalized, rows, settings, output)
    segments = [
        ReferenceSegment.model_validate(row).model_dump() for row in located["segments"]
    ]
    return {
        "schema_version": "m3.reference.v2",
        "text_source": "source_documents",
        "preparation": "automatic_pdf_and_acoustic_locator",
        "trusted_question_structure": structure,
        "groups": groups,
        **located,
        "segments": segments,
        "asr_calls": 0,
        "llm_calls": 0,
        "manual_reference_files_used": False,
        "search_windows_are_final_timestamps": False,
    }
