"""Tests for lightercore.text_utils — sanitization, normalization, diacritic stripping, diffs."""

from __future__ import annotations

from lightercore.text_utils import (
    compute_diffs,
    normalize_label_to_id,
    sanitize_node_id,
    strip_diacritics,
)


class TestSanitizeNodeId:
    def test_keeps_ascii(self) -> None:
        assert sanitize_node_id("HelloWorld") == "HelloWorld"

    def test_keeps_underscores_and_digits(self) -> None:
        assert sanitize_node_id("node_123") == "node_123"

    def test_strips_zero_width_space(self) -> None:
        # U+200B (Cf category)
        assert sanitize_node_id("node\u200b42") == "node42"

    def test_strips_bom(self) -> None:
        # U+FEFF BOM (Cf category)
        assert sanitize_node_id("\ufeffmynode") == "mynode"

    def test_strips_null_char(self) -> None:
        assert sanitize_node_id("node\x00test") == "nodetest"

    def test_preserves_tab_and_space(self) -> None:
        assert sanitize_node_id("node\tid") == "node\tid"
        assert sanitize_node_id("node id") == "node id"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert sanitize_node_id("  mynode  ") == "mynode"

    def test_empty_string(self) -> None:
        assert sanitize_node_id("") == ""


class TestNormalizeLabelToId:
    def test_basic_ascii(self) -> None:
        assert normalize_label_to_id("Hello") == "HELLO"

    def test_accented_to_ascii(self) -> None:
        assert normalize_label_to_id("Matière") == "MATIERE"
        assert normalize_label_to_id("São Paulo") == "SAO_PAULO"
        assert normalize_label_to_id("François") == "FRANCOIS"

    def test_collapses_non_alphanumeric(self) -> None:
        assert normalize_label_to_id("foo bar baz") == "FOO_BAR_BAZ"
        assert normalize_label_to_id("foo-bar!baz?") == "FOO_BAR_BAZ"

    def test_strips_leading_trailing_separators(self) -> None:
        assert normalize_label_to_id("__hello__") == "HELLO"

    def test_empty_label_falls_back(self) -> None:
        assert normalize_label_to_id("") == "_UNLABELED"
        assert normalize_label_to_id("---") == "_UNLABELED"

    def test_mixed_case_uppercased(self) -> None:
        assert normalize_label_to_id("MiXeD CaSe") == "MIXED_CASE"

    def test_chinese_characters_ignored(self) -> None:
        # CJK characters decompose to non-ASCII in NFKD
        label = "你好world"
        assert normalize_label_to_id(label) == "WORLD"


class TestStripDiacritics:
    def test_removes_acute(self) -> None:
        assert strip_diacritics("Matière") == "Matiere"

    def test_removes_circumflex(self) -> None:
        assert strip_diacritics("forêt") == "foret"
        assert strip_diacritics("â ĵ") == "a j"

    def test_removes_umlaut(self) -> None:
        assert strip_diacritics("über") == "uber"
        assert strip_diacritics("Naïve") == "Naive"

    def test_removes_cedilla(self) -> None:
        assert strip_diacritics("Français") == "Francais"
        assert strip_diacritics("Garçon") == "Garcon"

    def test_keeps_ascii(self) -> None:
        assert strip_diacritics("Hello World 123!") == "Hello World 123!"

    def test_keeps_digits_and_punctuation(self) -> None:
        assert strip_diacritics("test_123!@#") == "test_123!@#"

    def test_empty_string(self) -> None:
        assert strip_diacritics("") == ""

    def test_mixed_diacritics_and_ascii(self) -> None:
        assert strip_diacritics("Café naïve über cool") == "Cafe naive uber cool"


# ── compute_diffs (moved from lightercore.cowrite.engine) ────────────────────


class TestComputeDiffs:
    """Character-level diff computation between original and revised text."""

    def test_no_changes(self):
        diffs = compute_diffs("Hello world", "Hello world")
        assert len(diffs) == 1
        assert diffs[0]["tag"] == "equal"

    def test_simple_replacement(self):
        diffs = compute_diffs("Hello world", "Hello there")
        assert diffs[0]["tag"] == "equal"
        assert diffs[0]["start_orig"] == 0
        assert diffs[0]["end_orig"] == 6
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert len(replace_ops) >= 1

    def test_insertion(self):
        diffs = compute_diffs("Hello", "Hello world")
        insert_ops = [d for d in diffs if d["tag"] == "insert"]
        assert len(insert_ops) >= 1
        assert insert_ops[0]["inserted"] == " world"

    def test_deletion(self):
        diffs = compute_diffs("Hello world", "Hello")
        delete_ops = [d for d in diffs if d["tag"] == "delete"]
        assert len(delete_ops) >= 1
        assert delete_ops[0]["deleted"] == " world"

    def test_complete_replacement(self):
        diffs = compute_diffs("Old text", "New text")
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert any(d["deleted"] and d["inserted"] for d in replace_ops)

    def test_empty_original(self):
        diffs = compute_diffs("", "New content")
        insert_ops = [d for d in diffs if d["tag"] == "insert"]
        assert any(d["inserted"] == "New content" for d in insert_ops)

    def test_empty_revised(self):
        diffs = compute_diffs("Old content", "")
        delete_ops = [d for d in diffs if d["tag"] == "delete"]
        assert any(d["deleted"] == "Old content" for d in delete_ops)

    def test_diffs_contain_position_info(self):
        diffs = compute_diffs("Hello world", "Hello there")
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert len(replace_ops) >= 1
        op = replace_ops[0]
        assert "start_orig" in op
        assert "end_orig" in op
        assert op["start_orig"] <= op["end_orig"]
        assert op["start_orig"] == 6
