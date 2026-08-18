import unittest

from nlm_ingestor.ingestor.line_parser import Word
from nlm_ingestor.ingestor.visual_ingestor.visual_ingestor import Doc


def make_line(text, top=100.0, left=0.0, word_class="cls_1"):
    return {
        "text": text,
        # box_style: [top, left, right, width, height]
        "box_style": [top, left, left + 50.0, 50.0, 10.0],
        # line_style index 2 = font size, index 5 = space width
        "line_style": (0, 0, 10.0, 0, 0, 2.0),
        "word_classes": [word_class],
        "page_idx": 0,
        "class": word_class,
        "line_parser": {
            "word_count": 1,
            "last_word_number": False,
            "numbered_line": False,
            "is_table_row": False,
            "is_list_item": False,
            "words": [],
        },
    }


class TableDetectStub:
    """Stands in for Doc; detect_table_or_list only needs gap info,
    page width and list-item lookup from self."""

    page_styles = {0: (None, 1000.0, None, None)}

    def get_gaps_from_vls(self, vl, prev_vl):
        # gap > normal_gap so the table-row detection branch is entered
        return 100.0, 10.0, 10.0, False

    def is_list_item(self, line_info):
        return line_info["line_parser"].get("is_list_item", False)


def detect(group_buf, line_info, prev_line_info):
    return Doc.detect_table_or_list(
        TableDetectStub(), group_buf, False, line_info, prev_line_info, True, []
    )


class DetectTableOrListDegenerateTest(unittest.TestCase):
    # Regression tests for IndexError on empty / whitespace-only visual line
    # text inside detect_table_or_list.

    def test_empty_current_line_text(self):
        # line_info['text'][0] crashed on empty text
        is_list, is_table_row = detect(
            [make_line("Data")], make_line(""), make_line("Data")
        )
        self.assertFalse(is_list)
        self.assertFalse(is_table_row)

    def test_empty_prev_line_text_multi_line_group(self):
        # prev_line_info['text'][-1] crashed on empty text (period check)
        group_buf = [make_line("Data", top=100.0), make_line("More", top=200.0)]
        is_list, is_table_row = detect(group_buf, make_line("100"), make_line(""))
        self.assertFalse(is_list)
        self.assertTrue(is_table_row)

    def test_empty_prev_line_text_section_group(self):
        # prev_line_info['text'][-1] crashed on empty text (continuing-chars check)
        is_list, is_table_row = detect(
            [make_line("section 5")], make_line("100"), make_line("")
        )
        self.assertFalse(is_list)
        self.assertTrue(is_table_row)

    def test_whitespace_prev_line_text_section_group(self):
        # prev text strips to '' -> strip().split()[-1] crashed (section number check)
        is_list, is_table_row = detect(
            [make_line("section 5")], make_line("100"), make_line("   ")
        )
        self.assertFalse(is_list)
        self.assertTrue(is_table_row)

    def test_prev_line_ending_with_period_still_blocks_table_row(self):
        # Original behavior preserved for non-empty text
        group_buf = [make_line("Data", top=100.0), make_line("More", top=200.0)]
        is_list, is_table_row = detect(
            group_buf, make_line("100"), make_line("Ends.", top=200.0)
        )
        self.assertFalse(is_list)
        self.assertFalse(is_table_row)

    def test_section_number_prev_still_blocks_table_row(self):
        # Original behavior preserved for non-empty text
        is_list, is_table_row = detect(
            [make_line("section Overview")], make_line("100"), make_line("1.1")
        )
        self.assertFalse(is_list)
        self.assertFalse(is_table_row)


class MergeGapStub:
    """Stands in for Doc in merge_vls_if_needed; gap below normal_gap so the
    merge branch (and its currency adjacency check) is reached."""

    def get_gaps_from_vls(self, vl, prev_vl):
        return 1.0, 10.0, None, False


def merge(vls):
    return Doc.merge_vls_if_needed(MergeGapStub(), vls)


class MergeVlsCurrencyAdjacencyTest(unittest.TestCase):
    # Regression tests for IndexError in the currency adjacency check of
    # merge_vls_if_needed (prev/current text empty after strip).

    def test_whitespace_vl_after_currency_ending_prev(self):
        # vl strips to '' -> vl['text'].strip()[0] crashed
        good_vl, _, _ = merge([make_line("Total €"), make_line("   ")])
        self.assertEqual(len(good_vl), 1)

    def test_adjacent_currency_symbols_still_block_merge(self):
        # Original behavior preserved: '%' next to '%' stays unmerged
        good_vl, _, _ = merge([make_line("5%"), make_line("%20")])
        self.assertEqual(len(good_vl), 2)


class BlocksStub:
    def __init__(self, blocks):
        self.blocks = blocks


class DivideParaToHeadersDegenerateTest(unittest.TestCase):
    # Regression test for IndexError on empty block_text in
    # divide_para_to_headers.

    def test_letter_list_item_with_empty_text(self):
        # blk["block_text"][0].isupper() crashed on empty text
        blk = {
            "block_type": "list_item",
            "list_type": "letter",
            "block_text": "",
            "visual_lines": [{}, {}],
        }
        stub = BlocksStub([blk])
        Doc.divide_para_to_headers(stub)
        self.assertEqual(stub.blocks, [blk])

    def test_letter_list_item_with_normal_text_unchanged(self):
        # Original behavior preserved: single-visual-line block passes through
        blk = {
            "block_type": "list_item",
            "list_type": "letter",
            "block_text": "Apple Pie",
            "visual_lines": [{}],
        }
        stub = BlocksStub([blk])
        Doc.divide_para_to_headers(stub)
        self.assertEqual(stub.blocks, [blk])


class WordDegenerateTest(unittest.TestCase):
    # Regression tests for IndexError in Word.__init__ (is_noun on empty text).

    def test_empty_token(self):
        self.assertFalse(Word("").is_noun)

    def test_whitespace_token(self):
        self.assertFalse(Word(" ").is_noun)

    def test_single_char_tokens(self):
        self.assertTrue(Word("A").is_noun)
        self.assertFalse(Word("a").is_noun)

    def test_normal_tokens(self):
        self.assertTrue(Word("Total").is_noun)
        self.assertFalse(Word("total").is_noun)
        self.assertTrue(Word("(Amount)").is_noun)


if __name__ == "__main__":
    unittest.main()
