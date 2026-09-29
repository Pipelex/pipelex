"""Unit tests for the reusable structures-refusal check."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest

from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.stamp import apply_stamp
from pipelex.methods.exceptions import MethodStructuresRefusedError
from pipelex.methods.structures_check import (
    STRUCTURES_REFUSAL_RULE,
    StructuredContentViolation,
    ensure_no_structured_content_in_library_sources,
    ensure_no_structured_content_python,
    is_generated_structures_module,
    scan_structured_content_classes,
    scan_structured_content_sources,
    structured_content_class_names_in_source,
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

ALIASED_IMPORT_MODULE = """\
from pipelex.core.stuffs.structured_content import StructuredContent as SC


class Invoice(SC):
    total: float
"""

ATTRIBUTE_BASE_MODULE = """\
import pipelex.core.stuffs.structured_content as sc_module


class Invoice(sc_module.StructuredContent):
    total: float
"""

UNRELATED_ALIAS_MODULE = """\
from some.other.module import OtherBase as SC


class Helper(SC):
    pass
"""


def _stamped(body: str, *, target: CodegenTarget) -> str:
    return apply_stamp(
        body,
        crate_fingerprint="0" * 64,
        engine_version="0.0.0-test",
        kind=CodegenKind.TYPES,
        target=target,
        pipe_ref=None,
        options={},
        comment_prefix="#",
    )


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

    def test_from_import_alias_is_detected(self, tmp_path: Path) -> None:
        """`from ... import StructuredContent as SC` does not bypass the refusal."""
        (tmp_path / "aliased.py").write_text(ALIASED_IMPORT_MODULE, encoding="utf-8")

        violations = scan_structured_content_classes(package_dir=tmp_path)

        assert len(violations) == 1
        assert violations[0].relative_path == "aliased.py"
        assert violations[0].class_names == ["Invoice"]

    def test_attribute_base_is_detected(self, tmp_path: Path) -> None:
        """A base reached as `module.StructuredContent` (whatever the module alias) is caught."""
        (tmp_path / "attribute_base.py").write_text(ATTRIBUTE_BASE_MODULE, encoding="utf-8")

        violations = scan_structured_content_classes(package_dir=tmp_path)

        assert len(violations) == 1
        assert violations[0].relative_path == "attribute_base.py"
        assert violations[0].class_names == ["Invoice"]

    def test_unrelated_alias_is_not_flagged(self, tmp_path: Path) -> None:
        """An alias named `SC` bound to some other class is not a violation — bindings are tracked, not guessed."""
        (tmp_path / "unrelated.py").write_text(UNRELATED_ALIAS_MODULE, encoding="utf-8")

        assert scan_structured_content_classes(package_dir=tmp_path) == []

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

    def test_source_walk_matches_the_directory_scan(self, tmp_path: Path) -> None:
        """Both refusals run one walk, so a directory and its captured sources yield the same violations."""
        modules = {
            "structures/invoice.py": STRUCTURES_MODULE,
            "aliased.py": ALIASED_IMPORT_MODULE,
            "attribute_base.py": ATTRIBUTE_BASE_MODULE,
            "funcs.py": PIPE_FUNC_MODULE,
            "unrelated.py": UNRELATED_ALIAS_MODULE,
        }
        for relative_path, source in modules.items():
            file_path = tmp_path / PurePosixPath(relative_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")

        assert scan_structured_content_sources(sources=modules) == scan_structured_content_classes(package_dir=tmp_path)

    def test_unparseable_source_declares_nothing(self) -> None:
        assert structured_content_class_names_in_source(source="def broken(:\n", filename="broken.py") == []
        assert structured_content_class_names_in_source(source="x = 1\0\n", filename="nul.py") == []

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("x = a" + ".a" * 200_000 + "\n", id="attribute_chain_exhausts_recursion"),
            pytest.param("x = " + "-" * 200_000 + "1\n", id="unary_run_overflows_parser_stack"),
        ],
    )
    def test_source_too_deep_to_parse_declares_nothing(self, source: str) -> None:
        # Every sandbox-hosted load scans every customer `.py`, so a source that exhausts the parser
        # must read as declaring nothing, not escape the load as a RecursionError or MemoryError.
        assert structured_content_class_names_in_source(source=source, filename="deep.py") == []

    def test_sources_are_reported_in_path_order(self) -> None:
        violations = scan_structured_content_sources(sources={"z.py": STRUCTURES_MODULE, "a.py": ALIASED_IMPORT_MODULE})

        assert violations == [
            StructuredContentViolation(relative_path="a.py", class_names=["Invoice"]),
            StructuredContentViolation(relative_path="z.py", class_names=["Invoice", "LineItem"]),
        ]

    def test_pipe_func_only_sources_load(self, tmp_path: Path) -> None:
        ensure_no_structured_content_in_library_sources(sources_by_dir={tmp_path: {"funcs.py": PIPE_FUNC_MODULE, "helper.py": PLAIN_MODULE}})

    def test_library_refusal_names_files_rule_and_route(self, tmp_path: Path) -> None:
        """The load-time message names each file by its relative path, the rule, and the MTHDS route for a PipeFunc."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"

        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            ensure_no_structured_content_in_library_sources(
                sources_by_dir={
                    dir_a: {"structures/invoice.py": STRUCTURES_MODULE, "funcs.py": PIPE_FUNC_MODULE},
                    dir_b: {"models/receipt.py": ALIASED_IMPORT_MODULE},
                }
            )

        message = str(exc_info.value)
        assert "structures/invoice.py defines Invoice, LineItem; models/receipt.py defines Invoice" in message
        assert STRUCTURES_REFUSAL_RULE in message
        assert "MTHDS concepts with inline structures" in message
        assert "from structures import <domain>__<Concept>" in message
        assert "funcs.py" not in message
        assert str(tmp_path) not in message

    def test_the_same_file_in_two_directories_is_listed_once(self, tmp_path: Path) -> None:
        with pytest.raises(MethodStructuresRefusedError) as exc_info:
            ensure_no_structured_content_in_library_sources(
                sources_by_dir={
                    tmp_path / "a": {"structures/invoice.py": STRUCTURES_MODULE},
                    tmp_path / "b": {"structures/invoice.py": STRUCTURES_MODULE},
                }
            )

        assert str(exc_info.value).count("structures/invoice.py") == 1

    def test_generated_structures_module_is_not_a_violation(self, tmp_path: Path) -> None:
        """The `python-structures` projection, left as generated, copies MTHDS concepts: neither scan flags it."""
        generated = _stamped(STRUCTURES_MODULE, target=CodegenTarget.PYTHON_STRUCTURES)
        structures_dir = tmp_path / "structures"
        structures_dir.mkdir()
        (structures_dir / "structures.py").write_text(generated, encoding="utf-8")

        assert is_generated_structures_module(source=generated)
        assert scan_structured_content_classes(package_dir=tmp_path) == []
        assert scan_structured_content_sources(sources={"structures/structures.py": generated}) == []
        ensure_no_structured_content_in_library_sources(sources_by_dir={tmp_path: {"structures/structures.py": generated}})

    @pytest.mark.parametrize(
        "source",
        [
            _stamped(STRUCTURES_MODULE, target=CodegenTarget.PYTHON_STRUCTURES) + "\n\nclass Extra(StructuredContent):\n    note: str\n",
            _stamped(STRUCTURES_MODULE, target=CodegenTarget.PYTHON_PYDANTIC),
            _stamped(STRUCTURES_MODULE, target=CodegenTarget.PYTHON_STRUCTURES).replace("# content_hash: ", "# content_hash: 0"),
            STRUCTURES_MODULE,
        ],
        ids=["edited-below-the-stamp", "another-projection", "mismatched-hash", "unstamped"],
    )
    def test_only_an_unedited_structures_projection_is_exempt(self, source: str) -> None:
        assert not is_generated_structures_module(source=source)
        assert scan_structured_content_sources(sources={"structures/structures.py": source}) != []
