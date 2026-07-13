"""Tests for lightercore.dev_helpers — shared dev-server CLI infrastructure."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lightercore.dev_helpers import (
    _app_env_prefix,
    cleanup_data_dir,
    find_dot_dev,
    find_dot_prod,
    is_seeded,
    setup_data_dir,
    standard_dev_parser,
    validate_seed_sources,
)


class TestAppEnvPrefix:
    def test_known_apps(self) -> None:
        assert _app_env_prefix("lighterbird") == "LIGHTERBIRD"
        assert _app_env_prefix("semantika") == "SEMANTIKA"
        assert _app_env_prefix("lightercore") == "LIGHTERCORE"

    def test_unknown_app(self) -> None:
        with pytest.raises(ValueError, match="Unknown app name"):
            _app_env_prefix("nonexistent")


class TestFindDotDev:
    def test_find_dot_dev_found(self, tmp_path: Path) -> None:
        """find_dot_dev returns path when .dev exists at project root."""
        (tmp_path / ".dev").write_text("KEY=val\n")
        script = tmp_path / "src" / "myapp" / "scripts" / "dev_cli.py"
        script.parent.mkdir(parents=True)
        script.touch()
        (tmp_path / "pyproject.toml").touch()

        result = find_dot_dev(script)
        assert result == tmp_path / ".dev"

    def test_find_dot_dev_not_found(self, tmp_path: Path) -> None:
        """find_dot_dev returns None when no .dev exists."""
        script = tmp_path / "src" / "myapp" / "scripts" / "dev_cli.py"
        script.parent.mkdir(parents=True)
        script.touch()

        result = find_dot_dev(script)
        assert result is None


class TestFindDotProd:
    def test_find_dot_prod_found(self, tmp_path: Path) -> None:
        (tmp_path / ".prod").write_text("KEY=val\n")
        script = tmp_path / "src" / "myapp" / "scripts" / "dev_cli.py"
        script.parent.mkdir(parents=True)
        script.touch()
        (tmp_path / "pyproject.toml").touch()

        result = find_dot_prod(script)
        assert result == tmp_path / ".prod"

    def test_find_dot_prod_not_found(self, tmp_path: Path) -> None:
        script = tmp_path / "src" / "myapp" / "scripts" / "dev_cli.py"
        script.parent.mkdir(parents=True)
        script.touch()

        result = find_dot_prod(script)
        assert result is None


class TestIsSeeded:
    def test_empty_dir(self, tmp_path: Path) -> None:
        assert is_seeded(tmp_path) is False

    def test_missing_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        assert is_seeded(missing) is False

    def test_with_files(self, tmp_path: Path) -> None:
        (tmp_path / "some.db").write_text("")
        assert is_seeded(tmp_path) is True

    def test_with_subdirs(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        assert is_seeded(tmp_path) is True


class TestSetupDataDir:
    def test_temp_dir_default(self) -> None:
        """setup_data_dir with None creates a temp dir and sets env vars."""
        data_dir, is_temp = setup_data_dir(
            None, app_name="lighterbird",
        )
        try:
            temp_root = data_dir.parent
            assert is_temp is True
            assert temp_root.name.startswith("lighterbird-dev-")
            assert data_dir == temp_root / "data"
            assert data_dir.exists()
            assert os.environ["LIGHTERBIRD_DATA_DIR"] == str(data_dir)
            assert "LIGHTERBIRD_CONFIG_DIR" not in os.environ
            assert os.environ["LIGHTERBIRD_CACHE_DIR"] == str(temp_root / "cache")
            assert os.environ["LIGHTERBIRD_STATE_DIR"] == str(temp_root / "state")
        finally:
            import shutil
            shutil.rmtree(data_dir.parent, ignore_errors=True)

    def test_persistent_dir(self, tmp_path: Path) -> None:
        """setup_data_dir with a persistent path — config dir is a
        completely separate concern, never touched by this function."""
        persist = tmp_path / "mydata"
        data_dir, is_temp = setup_data_dir(
            str(persist), app_name="semantika",
        )
        try:
            assert is_temp is False
            assert data_dir == persist.resolve()
            assert data_dir.exists()
            assert os.environ["SEMANTIKA_DATA_DIR"] == str(data_dir)
            assert "SEMANTIKA_CONFIG_DIR" not in os.environ
            assert os.environ["SEMANTIKA_CACHE_DIR"] == str(data_dir / "cache")
            assert os.environ["SEMANTIKA_STATE_DIR"] == str(data_dir / "state")
        finally:
            import shutil
            shutil.rmtree(data_dir, ignore_errors=True)

    def test_unknown_app_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown app name"):
            setup_data_dir(None, app_name="unknown")

    def test_persistent_dir_expands_home(self, tmp_path: Path) -> None:
        """setup_data_dir expands user home directory in the path."""
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        with patch.dict(os.environ, {"HOME": str(fake_home)}):
            data_dir, is_temp = setup_data_dir(
                "~/myapp-data", app_name="lighterbird",
            )
            try:
                assert is_temp is False
                assert data_dir == fake_home / "myapp-data"
                assert data_dir.exists()
            finally:
                import shutil
                shutil.rmtree(data_dir, ignore_errors=True)


class TestStandardDevParser:
    def test_parser_has_all_flags(self) -> None:
        parser = standard_dev_parser("Test dev server", default_port=6006)
        # Parse empty args to check defaults
        args = parser.parse_args([])
        assert args.seed is None
        assert args.prod is None
        assert args.seed_from is None
        assert args.data_dir is None
        assert args.port is None  # resolved by the caller
        assert args.keep_data is False
        assert args.quiet is False

    def test_parser_accepts_custom_port(self) -> None:
        parser = standard_dev_parser("Test", default_port=6006)
        args = parser.parse_args(["--port", "9999"])
        assert args.port == 9999

    def test_parser_extensible(self) -> None:
        """Projects can add custom flags to the returned parser."""
        parser = standard_dev_parser("Test", default_port=6006)
        parser.add_argument("--my-flag", action="store_true")
        args = parser.parse_args(["--my-flag"])
        assert args.my_flag is True


class TestValidateSeedSources:
    def test_none_allowed(self) -> None:
        args = argparse.Namespace(seed=None, prod=None, seed_from=None)
        validate_seed_sources(args)  # should not raise

    def test_single_allowed(self) -> None:
        args = argparse.Namespace(seed="auto", prod=None, seed_from=None)
        validate_seed_sources(args)  # should not raise

    def test_double_raises(self) -> None:
        args = argparse.Namespace(seed="auto", prod="auto", seed_from=None)
        with pytest.raises(SystemExit):
            validate_seed_sources(args)


class TestCleanupDataDir:
    def test_persistent_dir_not_deleted(self, tmp_path: Path) -> None:
        """cleanup_data_dir never deletes a persistent dir."""
        persist = tmp_path / "persist"
        persist.mkdir()
        cleanup_data_dir(persist, is_temp=False, keep_data=False, quiet=True)
        assert persist.exists()

    def test_temp_dir_kept_when_keep_data(self, tmp_path: Path) -> None:
        """Temp dir is preserved when keep_data=True."""
        tmp_dir = tmp_path / "temp-dev"
        tmp_dir.mkdir()
        cleanup_data_dir(tmp_dir, is_temp=True, keep_data=True, quiet=True)
        assert tmp_dir.exists()

    def test_temp_dir_deleted_when_not_keep(self, tmp_path: Path) -> None:
        """Temp dir is removed when keep_data=False."""
        tmp_dir = tmp_path / "temp-dev"
        tmp_dir.mkdir()
        cleanup_data_dir(tmp_dir, is_temp=True, keep_data=False, quiet=True)
        assert not tmp_dir.exists()



