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
