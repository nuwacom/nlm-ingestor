"""Regression tests for Doc._normalize_table_markers().

A mis-detected or post-merge-mangled table can carry an is_table_start with no
matching is_table_end. Renderers treat the start..end span as the table's rows,
so an unterminated start silently swallows every following block (whole pages of
text) until the next start or end of document. _normalize_table_markers() demotes
any unpaired is_table_start so the content renders normally; genuine closed tables
are left untouched.
"""
from nlm_ingestor.ingestor.visual_ingestor.visual_ingestor import Doc


def _doc(blocks):
    # bypass the heavy __init__/parse(); we only exercise the marker pass
    d = Doc.__new__(Doc)
    d.blocks = blocks
    return d


def test_unterminated_table_start_is_demoted():
    d = _doc([
        {"block_type": "table_row", "is_table_start": True, "is_actual_table_start": True},
        {"block_type": "para"},
        {"block_type": "header"},
    ])
    d._normalize_table_markers()
    assert "is_table_start" not in d.blocks[0]
    assert "is_actual_table_start" not in d.blocks[0]


def test_properly_closed_table_is_untouched():
    d = _doc([
        {"is_table_start": True},
        {"block_type": "table_row"},
        {"is_table_end": True},
    ])
    d._normalize_table_markers()
    assert d.blocks[0].get("is_table_start") is True
    assert d.blocks[2].get("is_table_end") is True


def test_single_block_table_with_both_markers_untouched():
    d = _doc([{"is_table_start": True, "is_table_end": True}])
    d._normalize_table_markers()
    assert d.blocks[0].get("is_table_start") is True
    assert d.blocks[0].get("is_table_end") is True


def test_second_unterminated_start_demotes_first():
    d = _doc([
        {"is_table_start": True},                 # never closed
        {"block_type": "para"},
        {"is_table_start": True},                 # proper table
        {"is_table_end": True},
    ])
    d._normalize_table_markers()
    assert "is_table_start" not in d.blocks[0]
    assert d.blocks[2].get("is_table_start") is True


def test_stray_table_end_is_dropped():
    d = _doc([{"block_type": "para"}, {"is_table_end": True}])
    d._normalize_table_markers()
    assert "is_table_end" not in d.blocks[1]
