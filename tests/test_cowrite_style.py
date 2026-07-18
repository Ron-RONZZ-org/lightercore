"""Tests for lightercore/cowrite/style.py — cascade co-writing style loading.

Covers:
- General cowrite_style.md auto-seed and loading
- Per-domain files auto-seed and cascade (general + domain)
- ``cowrite_style_domain_path()`` returns correct paths
- Error handling (OSError, empty files, whitespace-only)
"""

from __future__ import annotations

from pathlib import Path

from lightercore.cowrite.style import (
    cowrite_style_domain_path,
    cowrite_style_path,
    load_cowrite_style,
)

_DEFAULT_GENERAL = "# General\n- Use active voice\n- Be concise"
_DEFAULT_NODE = "# Node\n- Use clear labels\n- Include source"
_DEFAULT_TRIPLE = "# Triple\n- Use consistent pattern"


class TestCowriteStylePath:
    def test_general_path(self):
        path = cowrite_style_path("/tmp/test-config")
        assert isinstance(path, str)
        assert path.endswith("cowrite_style.md")
        assert path.startswith("/tmp/test-config")

    def test_domain_path(self):
        path = cowrite_style_domain_path("/tmp/test-config", "node")
        assert isinstance(path, str)
        assert path.endswith("cowrite_style_node.md")
        assert path.startswith("/tmp/test-config")

    def test_domain_path_triple(self):
        path = cowrite_style_domain_path("/tmp/test-config", "triple")
        assert path.endswith("cowrite_style_triple.md")


class TestLoadCowriteStyleGeneral:
    """Test the general cowrite_style.md loading (no form_type)."""

    def test_loads_default_on_first_run(self, tmp_path: Path):
        """When no file exists, default is written and returned."""
        content = load_cowrite_style(
            config_dir=tmp_path,
            defaults={"general": _DEFAULT_GENERAL},
        )
        assert content == _DEFAULT_GENERAL
        assert (tmp_path / "cowrite_style.md").exists()

    def test_reads_existing_file(self, tmp_path: Path):
        """When file exists with content, it's read and returned."""
        existing = "Custom style content"
        (tmp_path / "cowrite_style.md").write_text(existing, encoding="utf-8")
        content = load_cowrite_style(config_dir=tmp_path)
        assert content == existing

    def test_empty_file_seeds_default(self, tmp_path: Path):
        """When file exists but is empty, it's treated as first run."""
        (tmp_path / "cowrite_style.md").write_text("", encoding="utf-8")
        content = load_cowrite_style(
            config_dir=tmp_path,
            defaults={"general": _DEFAULT_GENERAL},
        )
        assert content == _DEFAULT_GENERAL

    def test_whitespace_only_file(self, tmp_path: Path):
        """Whitespace-only file is treated as first run."""
        (tmp_path / "cowrite_style.md").write_text("   \n\n", encoding="utf-8")
        content = load_cowrite_style(
            config_dir=tmp_path,
            defaults={"general": _DEFAULT_GENERAL},
        )
        assert content == _DEFAULT_GENERAL

    def test_oserror_on_read_returns_none(self, tmp_path: Path):
        """When read fails, return None."""
        style_file = tmp_path / "cowrite_style.md"
        style_file.write_text("content", encoding="utf-8")
        tmp_path.chmod(0o000)
        try:
            content = load_cowrite_style(config_dir=tmp_path)
            assert content is None
        finally:
            tmp_path.chmod(0o755)

    def test_oserror_on_write_returns_none(self, tmp_path: Path):
        """When the default cannot be written, return None."""
        tmp_path.chmod(0o444)
        content = load_cowrite_style(
            config_dir=tmp_path,
            defaults={"general": _DEFAULT_GENERAL},
        )
        assert content is None
        tmp_path.chmod(0o755)

    def test_returns_none_when_no_defaults_and_no_file(self, tmp_path: Path):
        """No file exists and no defaults → None."""
        content = load_cowrite_style(config_dir=tmp_path)
        assert content is None

    def test_returns_general_without_domain(self, tmp_path: Path):
        """When general exists but no domain file, only general is returned."""
        (tmp_path / "cowrite_style.md").write_text("General rules", encoding="utf-8")
        content = load_cowrite_style(config_dir=tmp_path)
        assert content == "General rules"
        assert not (tmp_path / "cowrite_style_node.md").exists()


class TestCowriteStyleCascade:
    """Test the cascade model: general + per-domain files."""

    def test_domain_appended(self, tmp_path: Path):
        """When a form_type resolves to a domain, both files are loaded."""
        custom_node = "# Custom node rules"
        (tmp_path / "cowrite_style.md").write_text(_DEFAULT_GENERAL, encoding="utf-8")
        (tmp_path / "cowrite_style_node.md").write_text(custom_node, encoding="utf-8")

        content = load_cowrite_style(
            config_dir=tmp_path,
            form_type="node-add",
            form_type_to_domain={"node-add": "node"},
        )
        assert _DEFAULT_GENERAL in content
        assert custom_node in content
        assert "Domain-specific Guide" in content

    def test_domain_auto_seeded(self, tmp_path: Path):
        """Domain file is auto-seeded when it doesn't exist."""
        content = load_cowrite_style(
            config_dir=tmp_path,
            form_type="node-add",
            form_type_to_domain={"node-add": "node"},
            defaults={
                "general": _DEFAULT_GENERAL,
                "node": _DEFAULT_NODE,
            },
        )
        assert _DEFAULT_GENERAL in content
        assert _DEFAULT_NODE in content
        assert (tmp_path / "cowrite_style_node.md").exists()

    def test_domain_content_read_from_existing_file(self, tmp_path: Path):
        """Existing domain file is read, not overwritten."""
        custom_node = "# My custom node rules"
        (tmp_path / "cowrite_style.md").write_text(_DEFAULT_GENERAL, encoding="utf-8")
        (tmp_path / "cowrite_style_node.md").write_text(custom_node, encoding="utf-8")

        content = load_cowrite_style(
            config_dir=tmp_path,
            form_type="node-add",
            form_type_to_domain={"node-add": "node"},
            defaults={"node": _DEFAULT_NODE},
        )
        assert _DEFAULT_GENERAL in content
        assert custom_node in content
        assert _DEFAULT_NODE not in content  # Not overwritten

    def test_unknown_form_type_falls_back_to_general(self, tmp_path: Path):
        """An unknown form_type only loads the general file."""
        (tmp_path / "cowrite_style.md").write_text(_DEFAULT_GENERAL, encoding="utf-8")
        content = load_cowrite_style(
            config_dir=tmp_path,
            form_type="unknown-form",
            form_type_to_domain={"node-add": "node"},
        )
        assert content == _DEFAULT_GENERAL

    def test_domain_without_general_works(self, tmp_path: Path):
        """If general file doesn't exist, domain file still loads."""
        (tmp_path / "cowrite_style_node.md").write_text("# My node rules", encoding="utf-8")
        content = load_cowrite_style(
            config_dir=tmp_path,
            form_type="node-add",
            form_type_to_domain={"node-add": "node"},
        )
        assert "# My node rules" in content
        assert "Domain-specific Guide" in content

    def test_no_form_type_only_general(self, tmp_path: Path):
        """Calling without form_type only loads general."""
        (tmp_path / "cowrite_style.md").write_text(_DEFAULT_GENERAL, encoding="utf-8")
        content = load_cowrite_style(config_dir=tmp_path)
        assert content == _DEFAULT_GENERAL
        assert not (tmp_path / "cowrite_style_node.md").exists()
