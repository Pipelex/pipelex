"""Unit tests for the `pipelex-dev check-hub-layering` AST guard."""

from __future__ import annotations

import textwrap
from pathlib import Path

from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    RUNTIME_LAYER_PACKAGES,
    HubLayeringViolation,
    HubLayeringViolationKind,
    find_violations_in_source,
    is_runtime_layer,
)
from tests.unit.pipelex.test_runtime_layer_import_closure import INTERPRETER_PACKAGES

#: Anchored on `tests/` by name rather than by a parent count. A depth index is not merely fragile
#: here, it is *silent*: `parents[6]` is the workspace root, which holds a sibling `pipelex/` checkout,
#: so a module moved one level shallower would validate the declaration against a different repo and
#: pass. That is the failure this track already hit once, in the golden-renderer test.
_REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

#: A runtime-layer module path, and a interpreter-layer one, for the same snippet.
RUNTIME_PATH = "pipelex/cogt/sample/worker.py"
INTERPRETER_PATH = "pipelex/pipeline/sample/runner.py"
TEST_PATH = "tests/helpers/sample_helpers.py"

#: The deleted single hub. This line *declares* the dead path as test data rather than referencing it,
#: so it carries the guard's own escape hatch — without it, the guard flags its own test suite.
DEAD_HUB = "pipelex.hub"  # hub-layering: ignore


def _violate(source: str, *, relative_path: str = RUNTIME_PATH) -> list[HubLayeringViolation]:
    """Run the guard over an inline snippet and return its violations."""
    return find_violations_in_source(source=textwrap.dedent(source), relative_path=relative_path)


def _kinds(violations: list[HubLayeringViolation]) -> set[HubLayeringViolationKind]:
    return {violation.kind for violation in violations}


class TestHubLayeringGuard:
    def test_runtime_layer_membership(self) -> None:
        """The declared runtime layer is matched on package boundaries, and `pipeline` is outside it."""
        assert is_runtime_layer(module_qname="pipelex.cogt.llm.llm_worker_abstract")
        assert is_runtime_layer(module_qname="pipelex.tools")
        assert not is_runtime_layer(module_qname="pipelex.pipeline.runner")
        # A package whose name merely starts with a runtime-layer name is not in the runtime layer.
        assert not is_runtime_layer(module_qname="pipelex.toolsmith.thing")

    def test_core_is_declared_as_one_whole_package(self) -> None:
        """`core/` is declared wholesale — one entry, no sub-entries — because nothing interpreter-layer
        is left inside it.

        Stated as a property of the declaration rather than as a list of member modules. Once
        `pipelex.core` is a single prefix entry, `is_runtime_layer` answers True for *any* string
        under it, so asserting ten real module names would carry the same one bit as asserting ten
        invented ones — an inventory, not an invariant. What is worth pinning is the shape that took
        the whole M1 track to reach: re-introducing a `pipelex.core.<sub>` entry would mean core has
        split again, and that is what fails here.
        """
        assert "pipelex.core" in RUNTIME_LAYER_PACKAGES
        resplit = [package for package in RUNTIME_LAYER_PACKAGES if package.startswith("pipelex.core.")]
        assert not resplit, (
            f"`pipelex.core` is declared wholesale, but these sub-package entries are declared too: {resplit}. "
            "A sub-entry means some of `core/` is being carved out again — either move the interpreter-layer "
            "module to `pipe_machinery`/`mthds_parsing` as M1 did, or record why the split is back."
        )

    def test_no_interpreter_package_is_declared_runtime_layer(self) -> None:
        """The two layer declarations are disjoint — derived from both, so neither can drift alone.

        `RUNTIME_LAYER_PACKAGES` (this guard) and `INTERPRETER_PACKAGES` (the import-closure test) are
        the two halves of one partition, maintained in separate modules and never previously compared.
        Declaring a package in both would make the guard vouch for a package the closure test flags —
        each check would keep passing while contradicting the other.
        """
        for package in INTERPRETER_PACKAGES:
            qname = f"pipelex.{package}"
            assert not is_runtime_layer(module_qname=qname), (
                f"{qname} is named by the import-closure test's INTERPRETER_PACKAGES *and* matched by "
                "this guard's RUNTIME_LAYER_PACKAGES. The two declarations describe opposite layers."
            )
            assert not is_runtime_layer(module_qname=f"{qname}.some_module")

    def test_declared_runtime_layer_names_only_real_packages(self) -> None:
        """Every declared entry resolves on disk — `is_runtime_layer` is a string predicate that cannot tell.

        A renamed or deleted package leaves its entry matching nothing, which makes the declaration
        quietly *narrower* than it reads: the transitive rule filters its domain through this predicate,
        so an entry that matches nothing removes modules from the check rather than adding them.
        """
        source_root = _REPO_ROOT / "pipelex"
        for package in RUNTIME_LAYER_PACKAGES:
            relative = package.removeprefix("pipelex.").replace(".", "/")
            target = source_root / relative
            assert target.is_dir() or target.with_suffix(".py").is_file(), (
                f"RUNTIME_LAYER_PACKAGES names {package!r}, which resolves to neither a package directory "
                f"nor a module file under {source_root}. A declared entry that matches nothing silently "
                f"shrinks the layer rule's domain instead of failing."
            )

    def test_runtime_layer_may_import_runtime_hub(self) -> None:
        """The permitted direction is never flagged — the runtime layer lives on `runtime_hub`."""
        violations = _violate(
            """
            from pipelex.runtime_hub import get_console, get_model_deck
            """
        )
        assert violations == []

    def test_runtime_layer_importing_interpreter_hub_is_a_violation(self) -> None:
        """`from pipelex.interpreter_hub import …` in the runtime layer is the forbidden arrow."""
        violations = _violate(
            """
            from pipelex.interpreter_hub import get_pipe_router
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}
        assert violations[0].relative_path == RUNTIME_PATH
        assert violations[0].lineno == 2

    def test_plain_import_and_from_package_forms_are_caught(self) -> None:
        """`import pipelex.interpreter_hub` and `from pipelex import interpreter_hub` both resolve to the interpreter hub."""
        assert _kinds(_violate("import pipelex.interpreter_hub\n")) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}
        assert _kinds(_violate("import pipelex.interpreter_hub as hub\n")) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}
        assert _kinds(_violate("from pipelex import interpreter_hub\n")) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}

    def test_relative_import_of_interpreter_hub_is_caught(self) -> None:
        """A relative import is resolved against the file's own package, not taken at face value."""
        violations = _violate(
            """
            from ...interpreter_hub import get_library_manager
            """,
            relative_path="pipelex/cogt/sample/worker.py",
        )
        assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}

    def test_multi_name_import_reports_one_violation(self) -> None:
        """One offending statement yields one violation, not one per imported name."""
        violations = _violate(
            """
            from pipelex.interpreter_hub import get_library_manager, get_pipe_library, get_required_pipe
            """
        )
        assert len(violations) == 1

    def test_string_literal_import_module_form_is_caught(self) -> None:
        """The `importlib.import_module` string form — invisible to every import-graph tool — is a violation."""
        violations = _violate(
            """
            import importlib

            def resolve():
                return importlib.import_module("pipelex.interpreter_hub")
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_REFERENCE}

    def test_string_literal_attribute_path_is_caught(self) -> None:
        """A dotted attribute path under the interpreter hub — a `mocker.patch` target's shape — is a violation."""
        violations = _violate(
            """
            PATCH_TARGET = "pipelex.interpreter_hub.get_pipe_router"
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_REFERENCE}

    def test_prose_mentioning_the_hub_is_not_a_reference(self) -> None:
        """A docstring or message that merely names the module is not a reference — matching is exact-or-boundary."""
        violations = _violate(
            '''
            """The resolver `pipelex.interpreter_hub.set_interpreter_hub` installs at boot."""

            MESSAGE = "see pipelex.interpreter_hub for the interpreter half"
            '''
        )
        assert violations == []

    def test_runtime_hub_is_not_matched_by_the_dead_hub_rule(self) -> None:
        """`pipelex.runtime_hub` must not match `pipelex.hub` — boundary matching, not a substring test."""
        violations = _violate(
            """
            PATCH_TARGET = "pipelex.runtime_hub.get_console"
            """
        )
        assert violations == []

    def test_interpreter_layer_may_import_interpreter_hub(self) -> None:
        """Outside the declared runtime layer the layer rule does not apply."""
        violations = _violate(
            """
            from pipelex.interpreter_hub import get_pipe_router
            """,
            relative_path=INTERPRETER_PATH,
        )
        assert violations == []

    def test_type_checking_import_is_exempt_from_the_layer_rule(self) -> None:
        """A type-only import loads nothing, so it does not break the property the rule protects."""
        for test_expression in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            violations = _violate(
                f"""
                if {test_expression}:
                    from pipelex.interpreter_hub import InterpreterHub
                """
            )
            assert violations == []

    def test_runtime_else_branch_of_type_checking_is_not_exempt(self) -> None:
        """The exemption covers the `TYPE_CHECKING` body only — its `else` runs at import time."""
        violations = _violate(
            """
            if TYPE_CHECKING:
                from pipelex.interpreter_hub import InterpreterHub
            else:
                from pipelex.interpreter_hub import InterpreterHub
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}
        assert violations[0].lineno == 5

    def test_type_checking_on_an_unrelated_receiver_is_not_exempt(self) -> None:
        """The attributed form must be rooted at `typing` — any other receiver is a runtime condition.

        Matching the attribute name alone would let `settings.TYPE_CHECKING:` or a stub module's flag
        open an exempt block, which is a real import at runtime.
        """
        for receiver in ("settings", "compat", "not_typing"):
            violations = _violate(
                f"""
                if {receiver}.TYPE_CHECKING:
                    from pipelex.interpreter_hub import InterpreterHub
                """
            )
            assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}, receiver

    def test_negated_type_checking_is_not_exempt(self) -> None:
        """`if not TYPE_CHECKING:` guards a runtime branch, so it earns no exemption."""
        violations = _violate(
            """
            if not TYPE_CHECKING:
                from pipelex.interpreter_hub import InterpreterHub
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.INTERPRETER_HUB_IMPORT}

    def test_escape_hatch_suppresses_a_violation(self) -> None:
        """The inline marker suppresses one statement, including across a parenthesized block."""
        assert _violate("from pipelex.interpreter_hub import get_pipe_router  # hub-layering: ignore\n") == []
        assert (
            _violate(
                """
                from pipelex.interpreter_hub import (  # hub-layering: ignore
                    get_pipe_router,
                )
                """
            )
            == []
        )

    def test_dead_hub_import_is_a_violation_in_every_layer(self) -> None:
        """`pipelex.hub` is gone, so an import of it is dead code wherever it sits."""
        source = f"from {DEAD_HUB} import get_console\n"
        for relative_path in (RUNTIME_PATH, INTERPRETER_PATH, TEST_PATH):
            violations = _violate(source, relative_path=relative_path)
            assert _kinds(violations) == {HubLayeringViolationKind.DEAD_HUB_REFERENCE}

    def test_dead_hub_string_literal_is_a_violation_in_tests_too(self) -> None:
        """The `mocker.patch("pipelex.hub.get_console")` landmine: a string an ImportError never catches."""
        violations = _violate(f'mocker.patch("{DEAD_HUB}.get_console")\n', relative_path=TEST_PATH)
        assert _kinds(violations) == {HubLayeringViolationKind.DEAD_HUB_REFERENCE}

    def test_dead_hub_is_not_exempt_inside_type_checking(self) -> None:
        """The `TYPE_CHECKING` carve-out is for the layer rule only — a deleted module exists in no phase."""
        violations = _violate(f"if TYPE_CHECKING:\n    from {DEAD_HUB} import PipelexHub\n", relative_path=INTERPRETER_PATH)
        assert _kinds(violations) == {HubLayeringViolationKind.DEAD_HUB_REFERENCE}

    def test_tests_may_reference_the_interpreter_hub(self) -> None:
        """A test legitimately patches the interpreter hub; `tests.*` is in no declared layer."""
        violations = _violate(
            """
            mocker.patch("pipelex.interpreter_hub.get_pipe_router")
            from pipelex.interpreter_hub import get_library_manager
            """,
            relative_path=TEST_PATH,
        )
        assert violations == []

    def test_every_kind_names_a_remedy(self) -> None:
        """Each violation kind carries an actionable remedy, so a failure needs no re-run to act on."""
        for kind in HubLayeringViolationKind:
            assert kind.remedy
