"""Unit tests for the reusable structures-refusal check."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.methods.exceptions import MethodStructuresRefusedError
from pipelex.methods.structures_check import (
    STRUCTURES_REFUSAL_RULE,
    ensure_no_structured_content_python,
    scan_structured_content_classes,
)

if TYPE_CHECKING:
    from pathlib import Path

STRUCTURES_MODULE = """\
from pipelex.core.stuffs.structured_content import StructuredContent


class Invoice(StructuredContent):
    total: float


class LineItem(StructuredContent):
    label: str
"""

PIPE_FUNC_MODULE = """\
from pipelex.pipe_operators.func.func_registry import pipe_func


@pipe_func()
def compute_total(value: float) -> float:
    return value * 2
"""

PLAIN_MODULE = """\
class Helper:
    pass
"""


class TestStructuresCheck:
    """Tests for the AST-based StructuredContent refusal — never gating on mere .py presence."""

    def test_structures_module_is_detected(self, tmp_path: Path) -> None:
        """A .py file declaring StructuredContent subclasses is a violation naming the classes."""
        (tmp_path / "structures.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        violations = scan_structured_content_classes(package_dir=tmp_path)

        assert len(violations) == 1
        assert violations[0].relative_path == "structures.py"
        assert violations[0].class_names == ["Invoice", "LineItem"]

    def test_pipe_func_only_python_is_allowed(self, tmp_path: Path) -> None:
        """PipeFunc-only Python is supported: no violation, no refusal."""
        (tmp_path / "funcs.py").write_text(PIPE_FUNC_MODULE, encoding="utf-8")
        (tmp_path / "helper.py").write_text(PLAIN_MODULE, encoding="utf-8")

        assert scan_structured_content_classes(package_dir=tmp_path) == []
        ensure_no_structured_content_python(package_dir=tmp_path, package_address="github.com/acme/funcs-only")

    def test_refusal_names_the_rule(self, tmp_path: Path) -> None:
        """The refusal error names the rule and the offending classes."""
        (tmp_path / "structures.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            ensure_no_structured_content_python(package_dir=tmp_path, package_address="github.com/acme/bad-package")

        message = str(exc_info.value)
        assert STRUCTURES_REFUSAL_RULE in message
        assert "github.com/acme/bad-package" in message
        assert "Invoice" in message
        assert "MTHDS concepts" in message

    def test_unparseable_python_is_skipped(self, tmp_path: Path) -> None:
        """A syntactically invalid .py cannot smuggle a structure class: skipped, like the loader's gate."""
        (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")

        assert scan_structured_content_classes(package_dir=tmp_path) == []

    def test_pycache_and_git_are_skipped(self, tmp_path: Path) -> None:
        """Files under .git/ and __pycache__/ are not scanned."""
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text(STRUCTURES_MODULE, encoding="utf-8")
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        (git_dir / "hook.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        assert scan_structured_content_classes(package_dir=tmp_path) == []

    def test_nested_structures_are_detected(self, tmp_path: Path) -> None:
        """Violations are found recursively, reported with their relative path."""
        nested = tmp_path / "structures"
        nested.mkdir()
        (nested / "models.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        violations = scan_structured_content_classes(package_dir=tmp_path)

        assert len(violations) == 1
        assert violations[0].relative_path == "structures/models.py"
