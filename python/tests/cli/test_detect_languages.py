"""Tests for _detect_languages(): SDK language detection for stub generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fastn.cli._registry import _detect_languages


@pytest.fixture
def fastn_dir(tmp_path: Path) -> Path:
    """Create a .fastn directory inside a temporary project root."""
    d = tmp_path / ".fastn"
    d.mkdir()
    return d


class TestDetectLanguages:
    """Tests for _detect_languages()."""

    def test_returns_python_when_importable(self, fastn_dir: Path) -> None:
        """Should detect Python when the fastn package is importable."""
        # fastn is importable in the test environment
        result = _detect_languages(fastn_dir)
        assert "python" in result

    def test_returns_python_only_when_no_package_json(self, fastn_dir: Path) -> None:
        """Should return only Python when no package.json exists."""
        result = _detect_languages(fastn_dir)
        assert result == ["python"]

    @patch.dict("sys.modules", {"fastn": None})
    def test_returns_empty_when_fastn_not_importable(self, fastn_dir: Path) -> None:
        """Should return empty list when fastn is not importable and no package.json."""
        # Patching sys.modules to make `import fastn` raise ImportError
        with patch("builtins.__import__", side_effect=_import_blocker("fastn")):
            result = _detect_languages(fastn_dir)
        assert result == []

    def test_never_detects_typescript(self, fastn_dir: Path) -> None:
        """TypeScript stubs are gone: a package.json with fastn deps changes nothing."""
        project_root = fastn_dir.parent
        pkg = {"dependencies": {"@fastn-ai/sdk": "^0.4.0", "@fastn/sdk": "^1.0.0", "fastn": "^1.0.0"}}
        (project_root / "package.json").write_text(json.dumps(pkg))

        result = _detect_languages(fastn_dir)
        assert result == ["python"]


def _import_blocker(blocked_module: str):
    """Create an import function that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _blocked_import(name, *args, **kwargs):
        if name == blocked_module:
            raise ImportError(f"Blocked: {name}")
        return real_import(name, *args, **kwargs)

    return _blocked_import
