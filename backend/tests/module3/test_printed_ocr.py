"""Printed spacing/rules must be inferred from pixels, not an answer fixture."""

import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("cv2"), "OCR environment only")
class PrintedOcrTests(unittest.TestCase):
    def image(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (100, 35), "white")
        draw = ImageDraw.Draw(image)
        for x in [10, 20, 70, 80]:
            draw.rectangle((x, 3, x + 7, 22), fill="black")
        draw.line((0, 26, 99, 26), fill="black", width=2)
        return image

    def test_rule_removal_preserves_original_image_and_glyphs(self):
        import numpy as np

        from app.module3.ocr_refinement import clean_printed_crop

        original = self.image()
        before = np.asarray(original).copy()
        clean = np.asarray(clean_printed_crop(original))
        self.assertTrue(np.array_equal(np.asarray(original), before))
        self.assertTrue((clean[26] == 255).all())
        self.assertTrue((clean[10, 12] == 0).all())

    def test_ctc_columns_restore_word_boundary_without_changing_letters(self):
        from app.module3.ocr_refinement import clean_printed_crop, recognize_printed

        class Recognizer:
            def predict(self, image, return_word_box):
                self.asserted = return_word_box
                yield SimpleNamespace(
                    json={
                        "res": {
                            "rec_text": [
                                "ABCD",
                                [
                                    10,
                                    [["A", "B", "C", "D"]],
                                    [[1, 2, 7, 8]],
                                    ["en&num"],
                                ],
                            ],
                            "rec_score": 0.99,
                        }
                    }
                )

        recognizer = Recognizer()
        result = recognize_printed(recognizer, clean_printed_crop(self.image()))
        self.assertEqual(result["rec_text"], "AB CD")
        self.assertEqual(result["raw_text"], "ABCD")
        self.assertTrue(recognizer.asserted)

    def test_answer_box_does_not_join_question_and_options(self):
        from PIL import Image, ImageDraw

        from app.module3.reference_document_scan import printed_line_boxes

        image = Image.new("RGB", (400, 180), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 31, 300, 88), outline="black", width=2)
        for top in [10, 60]:
            for x in range(20, 240, 20):
                draw.rectangle((x, top, x + 8, top + 18), fill="black")
        boxes = printed_line_boxes(image)
        self.assertEqual(len(boxes), 2)
        self.assertLess(boxes[0][3], boxes[1][1])

    def test_question_number_disagreement_requires_source_crop_vote(self):
        from app.module3.ocr_refinement import verify_question_number

        with (
            patch("app.module3.ocr_refinement.word_spans", return_value=[(5, 20)]),
            patch(
                "app.module3.ocr_refinement.recognize_printed",
                return_value={"rec_text": "17 How did", "raw_text": "17 How did"},
            ),
        ):
            text, evidence = verify_question_number(
                "17.Howdid", "7.How did it happen?", self.image(), None
            )
        self.assertEqual(text, "17. How did it happen?")
        self.assertEqual(len(evidence), 3)

    def test_question_number_without_consensus_stops(self):
        from app.module3.contracts import ProcessingError
        from app.module3.ocr_refinement import verify_question_number

        with (
            patch("app.module3.ocr_refinement.word_spans", return_value=[(5, 20)]),
            patch(
                "app.module3.ocr_refinement.recognize_printed",
                return_value={"rec_text": "8. How", "raw_text": "8. How"},
            ),
            self.assertRaises(ProcessingError) as caught,
        ):
            verify_question_number("17.How", "7.How?", self.image(), None)
        self.assertEqual(caught.exception.code, "REFERENCE_NUMBER_AMBIGUOUS")

    def test_small_broken_rule_is_not_a_source_text_row(self):
        from PIL import Image, ImageDraw

        from app.module3.reference_document_scan import printed_line_boxes

        image = Image.new("RGB", (400, 160), "white")
        draw = ImageDraw.Draw(image)
        for x in range(20, 260, 25):
            draw.rectangle((x, 20, x + 12, 50), fill="black")
            draw.rectangle((x, 65, x + 15, 72), fill="black")
        boxes = printed_line_boxes(image)
        self.assertEqual(len(boxes), 1)
        self.assertLess(boxes[0][3], 60)

    def test_missing_number_in_long_read_uses_two_independent_source_votes(self):
        from app.module3.ocr_refinement import verify_question_number

        with (
            patch("app.module3.ocr_refinement.word_spans", return_value=[(5, 20)]),
            patch(
                "app.module3.ocr_refinement.recognize_printed",
                return_value={"rec_text": "4. Why", "raw_text": "4. Why"},
            ),
        ):
            text, evidence = verify_question_number(
                "4.Why did", "Why did the person leave?", self.image(), None
            )
        self.assertEqual(text, "4. Why did the person leave?")
        self.assertEqual(len(evidence), 3)


if __name__ == "__main__":
    unittest.main()
