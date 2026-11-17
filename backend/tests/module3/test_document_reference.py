"""Document-only preparation derives structure from sources, not fixed samples."""

import pytest


def sample_pages():
    return [
        {
            "material_id": 1,
            "page": 1,
            "source_kind": "paper_text",
            "text": (
                "Part II Listening Comprehension\n"
                "Questions 1 and 2 are based on the news report you have just heard.\n"
                "Questions 3 to 5 are based on the conversation you have just heard.\n"
                "Part III Reading Comprehension\n"
                "Questions 6 to 9 are based on the passage."
            ),
        },
        {
            "material_id": 2,
            "page": 4,
            "source_kind": "answer_explanation",
            "text": (
                "News Report One\n"
                "·听力原文·\n"
                "Cats run. Dogs jump.\n"
                "·答案详解·\n"
                "1. Who runs?谁在跑？\n"
                "2. Who jumps?谁在跳？\n"
                "Conversation One\n"
                "·听力原文·\n"
                "M: Hello.\n"
                "W: Good morning.\n"
                "·答案详解·\n"
                "3. What did the man say?男士说了什么？\n"
                "4. What did the woman say?女士说了什么？\n"
                "5. When did they speak?何时交谈？\n"
            ),
        },
    ]


def test_question_structure_is_independent_of_generated_output():
    from app.module3.document_reference import paper_structure

    structure = paper_structure(sample_pages())
    assert structure["question_count"] == 5
    assert [g["key"] for g in structure["groups"]] == ["news1", "conversation1"]
    assert [(g["start"], g["end"]) for g in structure["groups"]] == [(1, 2), (3, 5)]


def test_source_parser_keeps_speakers_pages_and_question_text():
    from app.module3.document_reference import paper_structure, parse_groups

    pages = sample_pages()
    groups = parse_groups(
        pages,
        paper_structure(pages),
        [{"material_id": 2, "storage_key": "unseen-answer.pdf", "sha256": "a" * 64}],
    )
    assert groups[0]["parts"][0]["text"] == "Cats run. Dogs jump."
    assert groups[0]["questions"][0]["text"] == "Who runs?"
    assert [p["speaker"] for p in groups[1]["parts"]] == ["M", "W"]
    assert groups[1]["source_storage_key"] == "unseen-answer.pdf"
    assert groups[1]["parts"][0]["pages"] == [4]


def test_missing_question_refuses_partial_reference():
    from app.module3.contracts import ProcessingError
    from app.module3.document_reference import paper_structure, parse_groups

    pages = sample_pages()
    pages[1]["text"] = pages[1]["text"].replace("5. When did they speak?何时交谈？", "")
    with pytest.raises(ProcessingError) as caught:
        parse_groups(
            pages,
            paper_structure(pages),
            [{"material_id": 2, "storage_key": "answer.pdf", "sha256": "b" * 64}],
        )
    assert caught.value.code == "REFERENCE_QUESTIONS_INCOMPLETE"


@pytest.mark.parametrize("label", ["案详解·", "·案详解·", "· 答 案 详 解 ·"])
def test_clipped_answer_label_does_not_turn_questions_into_body(label):
    import copy

    from app.module3.document_reference import paper_structure, parse_groups

    pages = sample_pages()
    pages[1]["text"] = pages[1]["text"].replace("·答案详解·", label)
    before = copy.deepcopy(pages)
    groups = parse_groups(
        pages,
        paper_structure(pages),
        [{"material_id": 2, "storage_key": "answer.pdf", "sha256": "b" * 64}],
    )
    assert pages == before  # Region classification never rewrites original OCR.
    assert [q["question_no"] for g in groups for q in g["questions"]] == [1, 2, 3, 4, 5]
    assert groups[0]["parts"][0]["text"] == "Cats run. Dogs jump."
    assert not any("Who runs?" in p["text"] for g in groups for p in g["parts"])


@pytest.mark.parametrize(
    "prose", ["这段案详解说明原因", "案详解不完整", "案详", "详解"]
)
def test_incomplete_label_exception_does_not_classify_prose(prose):
    from app.module3.document_reference import reference_section

    assert reference_section(prose) is None


def test_extraction_failure_diagnostic_requires_matching_input(tmp_path):
    import json

    from app.module3.contracts import file_hash
    from app.module3.ocr_worker import extraction_failure

    manifest = tmp_path / "input-manifest.json"
    manifest.write_text('{"files":[]}', encoding="utf-8")
    failure = tmp_path / "extraction-failure.json"
    assert extraction_failure(tmp_path).code == "OCR_PROCESS_FAILED"
    diagnostic = {
        "code": "REFERENCE_OCR_UNCERTAIN",
        "message": "第9页第6行正文识别可信度不足",
        "manifest_sha256": file_hash(manifest),
    }
    failure.write_text(json.dumps(diagnostic), encoding="utf-8")
    assert extraction_failure(tmp_path).code == "REFERENCE_OCR_UNCERTAIN"
    assert "第9页第6行" in str(extraction_failure(tmp_path))
    manifest.write_text('{"files":[1]}', encoding="utf-8")
    assert extraction_failure(tmp_path).code == "OCR_PROCESS_FAILED"
    failure.write_text("not JSON", encoding="utf-8")
    assert extraction_failure(tmp_path).code == "OCR_PROCESS_FAILED"


def test_ocr_child_records_specific_failure_before_exit(tmp_path, monkeypatch):
    import json
    import sys

    from app.module3 import ocr_worker
    from app.module3.contracts import ProcessingError, file_hash

    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"files":[]}', encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ocr_worker", "--manifest", str(manifest), "--output", str(output)],
    )

    def uncertain(*args):
        raise ProcessingError("REFERENCE_OCR_UNCERTAIN", "第9页第6行正文识别可信度不足")

    monkeypatch.setattr(ocr_worker, "extract", uncertain)
    with pytest.raises(ProcessingError) as caught:
        ocr_worker.main()
    assert caught.value.code == "REFERENCE_OCR_UNCERTAIN"
    diagnostic = json.loads((output / "extraction-failure.json").read_text("utf-8"))
    assert diagnostic["manifest_sha256"] == file_hash(manifest)
    assert diagnostic["code"] == caught.value.code
    assert "第9页第6行" in diagnostic["message"]
    assert not (output / "extracted.json").exists()


def test_spacing_recovery_never_changes_source_letters():
    from app.module3.document_reference import restore_word_gaps

    vocabulary = {
        "he": 1,
        "knew": 1,
        "corn": 1,
        "south": 1,
        "dakota": 1,
        "the": 1,
        "office": 1,
    }
    assert (
        restore_word_gaps("Heknew SouthDakota theoffice Tariq", vocabulary)
        == "He knew South Dakota the office Tariq"
    )


def test_crop_consensus_restores_missing_letter_and_printed_spaces():
    from app.module3.ocr_refinement import reconcile_line

    assert (
        reconcile_line("DepartmentofJustic.", ["Department", "of", "Justice."])
        == "Department of Justice."
    )


def test_reference_text_does_not_need_recognition_words():
    from app.module3.document_reference import parse_groups

    assert "asr" not in parse_groups.__code__.co_names


def test_repeated_or_skipped_paper_groups_fail():
    from app.module3.contracts import ProcessingError
    from app.module3.document_reference import paper_structure

    pages = sample_pages()
    pages[0]["text"] = pages[0]["text"].replace("Questions 3 to 5", "Questions 4 to 5")
    with pytest.raises(ProcessingError) as caught:
        paper_structure(pages)
    assert caught.value.code == "REFERENCE_QUESTION_RANGES_INVALID"


def test_sentence_preparation_preserves_native_word_boundaries(monkeypatch):
    import sys
    from types import SimpleNamespace

    from app.module3.document_reference import split_groups

    text = "They stole leftover stock while loading the ecosystem."
    splitter = SimpleNamespace(
        _params=SimpleNamespace(
            abbrev_types=set(),
            ortho_context=dict.fromkeys(
                ["sto", "le", "left", "over", "load", "ing", "eco", "system"], 1
            ),
        ),
        tokenize=lambda value: [value],
    )
    monkeypatch.setitem(
        sys.modules,
        "nltk",
        SimpleNamespace(data=SimpleNamespace(path=[], load=lambda _: splitter)),
    )
    rows = split_groups(
        [
            {
                "key": "unseen",
                "parts": [{"text": text, "speaker": None, "pages": [2]}],
                "questions": [],
                "source_storage_key": "unseen.pdf",
                "source_sha256": "a" * 64,
            }
        ],
        "unused",
    )
    assert rows[0]["text"] == text
