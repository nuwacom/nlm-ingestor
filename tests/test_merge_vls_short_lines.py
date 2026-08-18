import unittest

from nlm_ingestor.ingestor.visual_ingestor.visual_ingestor import Doc


def make_vl(text, left=0.0, word_class="cls_1"):
    return {
        "text": text,
        # box_style: [top, left, right, x1, height]
        "box_style": [100.0, left, left + 50.0, 0.0, 10.0],
        # line_style index 5 = space width
        "line_style": (0, 0, 0, 0, 0, 2.0),
        "word_classes": [word_class],
    }


class GapStub:
    """Stands in for Doc; merge_vls_if_needed only touches self in the
    gap-computation branch, which these tests steer away from merging."""

    def get_gaps_from_vls(self, vl, prev_vl):
        # gap far larger than normal_gap -> never merge
        return 100.0, 1.0, None, False


def merge(vls):
    return Doc.merge_vls_if_needed(GapStub(), vls)


class MergeVlsShortLineTest(unittest.TestCase):
    # Regression tests for IndexError on sub-2-char / whitespace lines
    # (visual_ingestor.py:1824, "string index out of range" in production).

    def test_whitespace_plus_lone_currency_prev(self):
        # len(" €") > 1 passed the old guard but strip() is 1 char -> [-2] crashed
        good_vl, _, _ = merge([make_vl(" €"), make_vl("$1", left=60.0, word_class="cls_2")])
        self.assertEqual(len(good_vl), 2)

    def test_whitespace_only_prev(self):
        # strip() is empty -> [-1] crashed
        good_vl, _, _ = merge([make_vl("  "), make_vl("$1", left=60.0, word_class="cls_2")])
        self.assertEqual(len(good_vl), 2)

    def test_lone_currency_prev_with_whitespace_vl(self):
        # prev strips to '€', vl strips to '' -> vl.strip()[0] crashed
        good_vl, _, _ = merge([make_vl("€"), make_vl("   ", left=60.0, word_class="cls_2")])
        self.assertEqual(len(good_vl), 2)

    def test_currency_reattachment_still_works(self):
        # Original behavior preserved: trailing currency symbol moves to the next vl
        good_vl, _, _ = merge([make_vl("Total 5€"), make_vl("100", left=60.0)])
        self.assertEqual(good_vl[0]["text"], "Total 5")
        self.assertEqual(good_vl[1]["text"], "€100")


if __name__ == "__main__":
    unittest.main()
