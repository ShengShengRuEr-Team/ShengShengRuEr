"""Exercise source-only global/group location with real synthetic CTC frames."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("torch"), "processing environment only")
class SourceLocatorTests(unittest.TestCase):
    def test_orders_groups_and_absorbs_unrelated_speech(self):
        import numpy as np
        import torch

        from app.module3.reference_locator import locate

        dictionary = {"<pad>": 0, "a": 1, "b": 2, "c": 3, "|": 4}
        values = torch.full((1, 170, 5), -14.0)
        values[:, :, 0] = 0
        for a, b, label in [
            (5, 8, 3),
            (20, 24, 1),
            (27, 31, 2),
            (48, 51, 3),
            (60, 64, 2),
            (68, 72, 3),
            (105, 110, 3),
            (114, 119, 1),
        ]:
            values[:, a:b, 0] = -14
            values[:, a:b, label] = 0
        times = np.stack([np.arange(170) * 20, (np.arange(170) + 1) * 20], 1)
        rows = [
            {
                "segment_id": "first:s001",
                "passage_key": "first",
                "segment_type": "body",
                "text": "ab.",
            },
            {
                "segment_id": "q:1",
                "passage_key": "first",
                "segment_type": "question",
                "text": "bc?",
            },
            {
                "segment_id": "second:s001",
                "passage_key": "second",
                "segment_type": "body",
                "text": "ca.",
            },
        ]
        with patch(
            "app.module3.reference_locator.acoustic_features",
            return_value=(
                values.log_softmax(-1),
                times,
                {"dictionary": dictionary},
                3400,
            ),
        ):
            result = locate(Path("unused.npy"), rows, None, Path("unused"))
        self.assertEqual(
            [r["segment_id"] for r in result["segments"]],
            [r["segment_id"] for r in rows],
        )
        boundaries = result["locator"]["sentences"]
        for coarse, window, (start, end) in zip(
            boundaries,
            result["segments"],
            [(400, 620), (1200, 1440), (2100, 2380)],
            strict=True,
        ):
            # Coarse CTC guards may consume a few repeated character frames.
            # Their search windows must still contain the actual sentence.
            self.assertLessEqual(abs(coarse["coarse_start_ms"] - start), 100)
            self.assertLessEqual(abs(coarse["coarse_end_ms"] - end), 100)
            self.assertLessEqual(window["search_start_ms"], start)
            self.assertGreaterEqual(window["search_end_ms"], end)
        self.assertEqual(result["locator"]["asr_calls"], 0)
        self.assertFalse(result["locator"]["historical_artifacts_used"])


if __name__ == "__main__":
    unittest.main()
