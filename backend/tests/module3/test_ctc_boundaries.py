"""Regression cases for punctuation, blank frames and unrelated context.

Run CPU tensor cases in the frozen processing environment with unittest; the API
environment deliberately does not import torch/WhisperX to serve requests.
"""

import importlib.util
import unittest
from types import SimpleNamespace


class SourceSymbolTests(unittest.TestCase):
    def test_punctuation_is_not_an_acoustic_wildcard(self):
        from app.module3.ctc_alignment import source_symbols

        labels = source_symbols(' "A, b." ', {"a": 1, "b": 2, "|": 3})
        self.assertEqual([symbol for _, symbol in labels], ["a", "|", "b"])

    def test_abbreviation_punctuation_does_not_split_source(self):
        from app.module3.ctc_alignment import source_symbols

        text = "U.S. No. 36"
        labels = source_symbols(text, {"u": 1, "s": 2, "n": 3, "o": 4, "|": 5})
        self.assertEqual("".join(c for _, c in labels), "us|no|36")
        self.assertEqual([text[i] for i, _ in labels][-2:], ["3", "6"])

    def test_apostrophe_and_hyphen_keep_source_offsets(self):
        from app.module3.ctc_alignment import source_symbols

        dictionary = {c: i + 1 for i, c in enumerate("isn't|yearold")}
        text = "isn’t year-old"
        labels = source_symbols(text, dictionary)
        self.assertEqual("".join(c for _, c in labels), "isn't|year|old")
        self.assertEqual(labels[3][0], 3)


@unittest.skipUnless(importlib.util.find_spec("torch"), "processing environment only")
class AcousticBoundaryTests(unittest.TestCase):
    def setUp(self):
        import torch

        self.torch = torch
        self.dictionary = {"<pad>": 0, "a": 1, "b": 2, "c": 3, "|": 4}

    def emission(self, regions, count=28):
        value = self.torch.full((1, count, 5), -14.0)
        value[:, :, 0] = 0.0
        for start, end, label in regions:
            value[:, start:end, 0] = -14.0
            value[:, start:end, label] = 0.0
        return value.log_softmax(-1)

    def decode(self, text, emission):
        from app.module3.ctc_alignment import emission_spans, source_symbols

        return emission_spans(
            emission, source_symbols(text, self.dictionary), self.dictionary, 0
        )

    def test_prefix_context_does_not_steal_first_letter(self):
        value = self.emission([(1, 3, 1), (4, 9, 3), (12, 14, 1), (16, 18, 2)])
        spans = self.decode("ab.", value)
        self.assertEqual([(s.start, s.end) for s in spans], [(12, 14), (16, 18)])

    def test_trailing_silence_and_next_sentence_do_not_extend_end(self):
        value = self.emission([(4, 6, 1), (8, 10, 2), (18, 25, 3)])
        spans = self.decode("ab.", value)
        self.assertEqual(spans[-1].end, 10)

    def test_repeated_letters_keep_required_ctc_blank(self):
        value = self.emission([(4, 6, 1), (8, 10, 1)])
        spans = self.decode("aa", value)
        self.assertEqual([(s.start, s.end) for s in spans], [(4, 6), (8, 10)])

    def test_digit_is_preserved_as_acoustic_wildcard(self):
        value = self.emission([(4, 6, 1), (8, 10, 3), (12, 14, 2)])
        spans = self.decode("a7b.", value)
        self.assertEqual(len(spans), 3)
        self.assertEqual([(s.start, s.end) for s in spans], [(4, 6), (8, 10), (12, 14)])

    def test_too_short_window_fails_without_fabricated_time(self):
        from app.module3.contracts import ProcessingError

        with self.assertRaises(ProcessingError) as caught:
            self.decode("ab", self.emission([], count=3))
        self.assertEqual(caught.exception.code, "ALIGNMENT_WINDOW_TOO_SHORT")

    def test_sentence_boundaries_preserve_absolute_window_offset(self):
        import numpy as np

        from app.module3.ctc_alignment import align_segments

        value = self.emission([(1, 3, 1), (4, 9, 3), (12, 14, 1), (16, 18, 2)])
        def model(waveform):
            return SimpleNamespace(logits=value)
        metadata = {
            "dictionary": self.dictionary,
            "type": "huggingface",
            "language": "en",
        }
        result = align_segments(
            [{"text": "ab.", "start": 1.0, "end": 1.56}],
            model,
            metadata,
            np.zeros(32000, dtype=np.float32),
        )["segments"][0]
        self.assertEqual(result["text"], "ab.")
        self.assertEqual((result["start"], result["end"]), (1.24, 1.36))
        self.assertNotIn("start", result["chars"][-1])


if __name__ == "__main__":
    unittest.main()
