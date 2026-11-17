"""Reject invalid page selection and untrustworthy alignment boundaries."""

import sys
from types import SimpleNamespace

import pytest


def test_text_pdf_rejects_out_of_range_page_before_extracting(tmp_path, monkeypatch):
    from app.module3 import ocr_worker
    from app.module3.contracts import ProcessingError, file_hash

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"fake PDF; parser replaced below")

    class Document:
        def __init__(self):
            self.pages = [object()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setitem(
        sys.modules, "pdfplumber", SimpleNamespace(open=lambda _: Document())
    )
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace())
    manifest = {
        "model_root": str(tmp_path),
        "files": [
            {
                "path": str(source),
                "sha256": file_hash(source),
                "source_kind": "paper_text",
                "material_id": 1,
                "page_numbers": [2],
            }
        ],
    }
    with pytest.raises(ProcessingError) as error:
        ocr_worker.extract(manifest, tmp_path)
    assert error.value.code == "PAGE_RANGE_INVALID"


@pytest.mark.parametrize("start,end", [(0.0, 2.0), (float("nan"), 0.5)])
def test_alignment_rejects_boundary_outside_audio_or_nonfinite(
    tmp_path, monkeypatch, start, end
):
    from app.module3 import audio

    # One second of synthetic audio; this exercises validation, not model accuracy.
    monkeypatch.setitem(
        sys.modules, "numpy", SimpleNamespace(load=lambda *a, **k: [0] * 16000)
    )
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        SimpleNamespace(
            load_align_model=lambda **k: (object(), {}),
            align=lambda *a, **k: {
                "segments": [
                    {
                        "text": "Alpha",
                        "start": start,
                        "end": end,
                        "chars": [{"char": "A", "start": start, "end": end}],
                    }
                ]
            },
        ),
    )
    monkeypatch.setattr(audio, "prepare_native", lambda _: None)
    monkeypatch.setattr(audio, "local_model", lambda *a: tmp_path)
    result = audio.align(
        tmp_path / "synthetic.npy", {"segments": [{"text": "Alpha"}]}, object()
    )
    segment = result["segments"][0]
    assert segment["alignment_status"] == "requires_review"
    assert segment["start_ms"] is segment["end_ms"] is None
    assert result["issues"][0]["issue_code"] == "ALIGNMENT_SEGMENTS_UNVERIFIED"
