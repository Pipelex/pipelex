"""Phase-B pins for the ``💡 Suggested fix:`` surfacing in human ``pipelex validate`` output.

``handle_validate_bundle_error`` now routes through the shared ``ValidationErrorItem``s (the
one builder that attaches ``suggested_fix``), so these tests pin: the per-error suggested-fix
line, the actionable ``pipelex fix bundle`` footer (which replaces the generic tip), the
factory-error section (rendered for the first time by the item routing — a deliberate
behavior change), and the dry-run message staying visible alongside categorized errors.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.error_handlers import handle_validate_bundle_error
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _fixable_pipe_error() -> PipesAndConceptValidationErrorData:
    """An enriched INADEQUATE_OUTPUT_CONCEPT — the fix planner derives ``match-sequence-output`` from it."""
    return PipesAndConceptValidationErrorData(
        error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        domain_code="demo",
        pipe_code="list_ideas",
        message="output concept mismatch",
        field_path="pipes.list_ideas.output",
        expected_output_ref="Idea[]",
    )


def _non_fixable_pipe_error() -> PipesAndConceptValidationErrorData:
    """The same error type without the enrichment — structurally suppressed by the planner."""
    return PipesAndConceptValidationErrorData(
        error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        domain_code="demo",
        pipe_code="other_pipe",
        message="output concept mismatch",
        field_path="pipes.other_pipe.output",
    )


class TestValidateSuggestedFixRendering:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        """Recorded console patched into the error handlers module."""
        recorded_console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=recorded_console)
        return recorded_console

    def test_fixable_error_renders_suggested_fix_line_and_actionable_footer(self, console: Console) -> None:
        exc = ValidateBundleError(message="validation failed", pipe_validation_errors=[_fixable_pipe_error()])

        with pytest.raises(typer.Exit) as exc_info:
            handle_validate_bundle_error(exc, bundle_path=Path("methods/demo.mthds"))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "💡 Suggested fix: Set output of pipe 'list_ideas' to 'Idea[]' to match its last step" in output
        assert "1 of these errors can be fixed automatically" in output
        assert "pipelex fix bundle methods/demo.mthds" in output
        # The actionable footer replaces the generic tip — two stacked 💡 tips would be noise.
        assert "💡 Tip:" not in output

    def test_footer_echoes_library_dirs(self, console: Console) -> None:
        exc = ValidateBundleError(message="validation failed", pipe_validation_errors=[_fixable_pipe_error()])

        with pytest.raises(typer.Exit):
            handle_validate_bundle_error(
                exc,
                bundle_path=Path("methods/demo.mthds"),
                library_dirs=[Path("libs"), Path("shared")],
            )

        output = console.export_text()
        assert "pipelex fix bundle methods/demo.mthds -L libs -L shared" in output

    def test_non_fixable_errors_keep_generic_tip_and_no_fix_line(self, console: Console) -> None:
        exc = ValidateBundleError(message="validation failed", pipe_validation_errors=[_non_fixable_pipe_error()])

        with pytest.raises(typer.Exit):
            handle_validate_bundle_error(exc, bundle_path=Path("methods/demo.mthds"))

        output = console.export_text()
        assert "💡 Suggested fix:" not in output
        assert "can be fixed automatically" not in output
        assert "💡 Tip:" in output

    def test_fixable_count_sums_only_fixable_items(self, console: Console) -> None:
        exc = ValidateBundleError(
            message="validation failed",
            pipe_validation_errors=[_fixable_pipe_error(), _non_fixable_pipe_error()],
        )

        with pytest.raises(typer.Exit):
            handle_validate_bundle_error(exc, bundle_path=Path("methods/demo.mthds"))

        output = console.export_text()
        assert "1 of these errors can be fixed automatically" in output

    def test_factory_errors_are_now_rendered(self, console: Console) -> None:
        """Pinned behavior change: the raw-list renderer silently skipped factory errors; the item routing shows them."""
        factory_error = PipeFactoryErrorData(
            error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
            domain_code="demo",
            pipe_code="say_hi",
            missing_concept_code="MissingConcept",
            declared_concepts=["Idea", "Report"],
            message="concept 'MissingConcept' is not declared in domain 'demo'",
        )
        exc = ValidateBundleError(message="validation failed", pipe_factory_errors=[factory_error])

        with pytest.raises(typer.Exit):
            handle_validate_bundle_error(exc, bundle_path=Path("methods/demo.mthds"))

        output = console.export_text()
        assert "Pipe Factory Errors:" in output
        assert "1. Unknown Concept" in output
        assert "Missing Concept: MissingConcept" in output
        assert "concept 'MissingConcept' is not declared in domain 'demo'" in output
        assert "Declared Concepts: Idea, Report" in output

    def test_dry_run_message_stays_visible_alongside_categorized_errors(self, console: Console) -> None:
        """The wire builder suppresses the dry-run residual when categorized errors exist; the human surface keeps it."""
        exc = ValidateBundleError(
            message="validation failed",
            pipe_validation_errors=[_non_fixable_pipe_error()],
            dry_run_error_message="dry run exploded",
        )

        with pytest.raises(typer.Exit):
            handle_validate_bundle_error(exc, bundle_path=Path("methods/demo.mthds"))

        output = console.export_text()
        assert "Dry Run Error:" in output
        assert "dry run exploded" in output
