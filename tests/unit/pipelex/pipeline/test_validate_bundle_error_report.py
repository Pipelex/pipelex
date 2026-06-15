"""Unit tests for ``ValidateBundleError.to_error_report`` — structured errors on the wire.

The override attaches the shared ``build_validation_error_items`` output onto
``ErrorReport.validation_errors``, so the RFC 7807 problem document the API emits
on a 422 carries machine-mappable per-error diagnostics (with ``source``) instead
of only a single ``detail`` string. The cause-chain enrichment from the base
``to_error_report`` is preserved.
"""

from pipelex.base_exceptions import DisclosureMode, ErrorDomain
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError


def _error_with_two_categories() -> ValidateBundleError:
    return ValidateBundleError(
        message="bundle 'main.mthds' failed validation",
        pipelex_bundle_blueprint_validation_errors=[
            PipelexBundleBlueprintValidationErrorData(
                error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
                source="main.mthds",
                message="Invalid main pipe syntax 'Not A Pipe'",
            ),
        ],
        pipe_validation_errors=[
            PipesAndConceptValidationErrorData(
                error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                source="helpers.mthds",
                pipe_code="summarize",
                message="Missing input variable(s): doc.",
                field_path="summarize.inputs.doc",
                variable_names=["doc"],
            ),
        ],
    )


class TestValidateBundleErrorReport:
    def test_to_error_report_populates_validation_errors(self) -> None:
        """``to_error_report`` attaches one structured item per underlying error."""
        report = _error_with_two_categories().to_error_report()
        assert report.validation_errors is not None
        sources = sorted(item.source or "" for item in report.validation_errors)
        assert sources == ["helpers.mthds", "main.mthds"]

    def test_report_keeps_caller_facing_input_classification(self) -> None:
        """The base classification (INPUT domain, caller-facing message) still holds."""
        report = _error_with_two_categories().to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message is True
        assert report.error_type == "ValidateBundleError"

    def test_empty_error_leaves_validation_errors_none(self) -> None:
        """No categorized errors → ``validation_errors`` stays ``None`` (drops from the wire)."""
        report = ValidateBundleError(message="generic failure").to_error_report()
        assert report.validation_errors is None

    def test_problem_document_carries_validation_errors_with_source(self) -> None:
        """The 422 problem document rides ``validation_errors[]`` as an extension member."""
        document = _error_with_two_categories().to_error_report().to_problem_document()
        assert document["status"] == 422
        items = document["validation_errors"]
        assert {item["source"] for item in items} == {"main.mthds", "helpers.mthds"}
        assert {item["category"] for item in items} == {"blueprint_validation", "pipe_validation"}

    def test_strict_problem_document_retains_validation_errors(self) -> None:
        """STRICT disclosure keeps ``validation_errors`` — they are the caller's own bundle diagnostics.

        ``ValidateBundleError`` is a caller-facing INPUT error, so STRICT also
        keeps the ``detail`` message; the structured items ride alongside it.
        """
        document = _error_with_two_categories().to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert "validation_errors" in document
        assert len(document["validation_errors"]) == 2
