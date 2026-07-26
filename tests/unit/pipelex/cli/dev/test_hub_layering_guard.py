"""Unit tests for the `pipelex-dev check-hub-layering` AST guard."""

from __future__ import annotations

import textwrap

from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    HubLayeringViolation,
    HubLayeringViolationKind,
    find_violations_in_source,
    is_low_layer,
)

#: A low-layer module path, and a high-layer one, for the same snippet.
LOW_PATH = "pipelex/cogt/sample/worker.py"
HIGH_PATH = "pipelex/pipeline/sample/runner.py"
TEST_PATH = "tests/helpers/sample_helpers.py"

#: The deleted single hub. This line *declares* the dead path as test data rather than referencing it,
#: so it carries the guard's own escape hatch — without it, the guard flags its own test suite.
DEAD_HUB = "pipelex.hub"  # hub-layering: ignore


def _violate(source: str, *, relative_path: str = LOW_PATH) -> list[HubLayeringViolation]:
    """Run the guard over an inline snippet and return its violations."""
    return find_violations_in_source(source=textwrap.dedent(source), relative_path=relative_path)


def _kinds(violations: list[HubLayeringViolation]) -> set[HubLayeringViolationKind]:
    return {violation.kind for violation in violations}


class TestHubLayeringGuard:
    def test_low_layer_membership(self) -> None:
        """The declared low layer is matched on package boundaries, and `core`/`pipeline` are outside it."""
        assert is_low_layer(module_qname="pipelex.cogt.llm.llm_worker_abstract")
        assert is_low_layer(module_qname="pipelex.tools")
        assert not is_low_layer(module_qname="pipelex.core.stuffs.stuff_factory")
        assert not is_low_layer(module_qname="pipelex.pipeline.runner")
        # A package whose name merely starts with a low-layer name is not in the low layer.
        assert not is_low_layer(module_qname="pipelex.toolsmith.thing")

    def test_low_layer_may_import_service_hub(self) -> None:
        """The permitted direction is never flagged — the low layer lives on `service_hub`."""
        violations = _violate(
            """
            from pipelex.service_hub import get_console, get_model_deck
            """
        )
        assert violations == []

    def test_low_layer_importing_method_hub_is_a_violation(self) -> None:
        """`from pipelex.method_hub import …` in the low layer is the forbidden arrow."""
        violations = _violate(
            """
            from pipelex.method_hub import get_pipe_router
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}
        assert violations[0].relative_path == LOW_PATH
        assert violations[0].lineno == 2

    def test_plain_import_and_from_package_forms_are_caught(self) -> None:
        """`import pipelex.method_hub` and `from pipelex import method_hub` both resolve to the high hub."""
        assert _kinds(_violate("import pipelex.method_hub\n")) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}
        assert _kinds(_violate("import pipelex.method_hub as hub\n")) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}
        assert _kinds(_violate("from pipelex import method_hub\n")) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}

    def test_relative_import_of_method_hub_is_caught(self) -> None:
        """A relative import is resolved against the file's own package, not taken at face value."""
        violations = _violate(
            """
            from ...method_hub import get_library_manager
            """,
            relative_path="pipelex/cogt/sample/worker.py",
        )
        assert _kinds(violations) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}

    def test_multi_name_import_reports_one_violation(self) -> None:
        """One offending statement yields one violation, not one per imported name."""
        violations = _violate(
            """
            from pipelex.method_hub import get_library_manager, get_pipe_library, get_required_pipe
            """
        )
        assert len(violations) == 1

    def test_string_literal_import_module_form_is_caught(self) -> None:
        """The `importlib.import_module` string form — invisible to every import-graph tool — is a violation."""
        violations = _violate(
            """
            import importlib

            def resolve():
                return importlib.import_module("pipelex.method_hub")
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.METHOD_HUB_REFERENCE}

    def test_string_literal_attribute_path_is_caught(self) -> None:
        """A dotted attribute path under the high hub — a `mocker.patch` target's shape — is a violation."""
        violations = _violate(
            """
            PATCH_TARGET = "pipelex.method_hub.get_pipe_router"
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.METHOD_HUB_REFERENCE}

    def test_prose_mentioning_the_hub_is_not_a_reference(self) -> None:
        """A docstring or message that merely names the module is not a reference — matching is exact-or-boundary."""
        violations = _violate(
            '''
            """The resolver `pipelex.method_hub.set_method_hub` installs at boot."""

            MESSAGE = "see pipelex.method_hub for the high half"
            '''
        )
        assert violations == []

    def test_service_hub_is_not_matched_by_the_dead_hub_rule(self) -> None:
        """`pipelex.service_hub` must not match `pipelex.hub` — boundary matching, not a substring test."""
        violations = _violate(
            """
            PATCH_TARGET = "pipelex.service_hub.get_console"
            """
        )
        assert violations == []

    def test_high_layer_may_import_method_hub(self) -> None:
        """Outside the declared low layer the layer rule does not apply."""
        violations = _violate(
            """
            from pipelex.method_hub import get_pipe_router
            """,
            relative_path=HIGH_PATH,
        )
        assert violations == []

    def test_type_checking_import_is_exempt_from_the_layer_rule(self) -> None:
        """A type-only import loads nothing, so it does not break the property the rule protects."""
        for test_expression in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            violations = _violate(
                f"""
                if {test_expression}:
                    from pipelex.method_hub import MethodHub
                """
            )
            assert violations == []

    def test_runtime_else_branch_of_type_checking_is_not_exempt(self) -> None:
        """The exemption covers the `TYPE_CHECKING` body only — its `else` runs at import time."""
        violations = _violate(
            """
            if TYPE_CHECKING:
                from pipelex.method_hub import MethodHub
            else:
                from pipelex.method_hub import MethodHub
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}
        assert violations[0].lineno == 5

    def test_negated_type_checking_is_not_exempt(self) -> None:
        """`if not TYPE_CHECKING:` guards a runtime branch, so it earns no exemption."""
        violations = _violate(
            """
            if not TYPE_CHECKING:
                from pipelex.method_hub import MethodHub
            """
        )
        assert _kinds(violations) == {HubLayeringViolationKind.METHOD_HUB_IMPORT}

    def test_escape_hatch_suppresses_a_violation(self) -> None:
        """The inline marker suppresses one statement, including across a parenthesized block."""
        assert _violate("from pipelex.method_hub import get_pipe_router  # hub-layering: ignore\n") == []
        assert (
            _violate(
                """
                from pipelex.method_hub import (  # hub-layering: ignore
                    get_pipe_router,
                )
                """
            )
            == []
        )

    def test_dead_hub_import_is_a_violation_in_every_layer(self) -> None:
        """`pipelex.hub` is gone, so an import of it is dead code wherever it sits."""
        source = f"from {DEAD_HUB} import get_console\n"
        for relative_path in (LOW_PATH, HIGH_PATH, TEST_PATH):
            violations = _violate(source, relative_path=relative_path)
            assert _kinds(violations) == {HubLayeringViolationKind.DEAD_HUB_REFERENCE}

    def test_dead_hub_string_literal_is_a_violation_in_tests_too(self) -> None:
        """The `mocker.patch("pipelex.hub.get_console")` landmine: a string an ImportError never catches."""
        violations = _violate(f'mocker.patch("{DEAD_HUB}.get_console")\n', relative_path=TEST_PATH)
        assert _kinds(violations) == {HubLayeringViolationKind.DEAD_HUB_REFERENCE}

    def test_dead_hub_is_not_exempt_inside_type_checking(self) -> None:
        """The `TYPE_CHECKING` carve-out is for the layer rule only — a deleted module exists in no phase."""
        violations = _violate(f"if TYPE_CHECKING:\n    from {DEAD_HUB} import PipelexHub\n", relative_path=HIGH_PATH)
        assert _kinds(violations) == {HubLayeringViolationKind.DEAD_HUB_REFERENCE}

    def test_tests_may_reference_the_method_hub(self) -> None:
        """A test legitimately patches the high hub; `tests.*` is in no declared layer."""
        violations = _violate(
            """
            mocker.patch("pipelex.method_hub.get_pipe_router")
            from pipelex.method_hub import get_library_manager
            """,
            relative_path=TEST_PATH,
        )
        assert violations == []

    def test_every_kind_names_a_remedy(self) -> None:
        """Each violation kind carries an actionable remedy, so a failure needs no re-run to act on."""
        for kind in HubLayeringViolationKind:
            assert kind.remedy
