"""Unit tests for the problem of an invalid verdict — structured errors on the wire.

``ValidateBundleError`` is ``method.invalid``, and its problem lists one item per underlying error under ``errors``,
each with its own code and its location (the file included), so the problem document the API emits carries
machine-mappable per-error diagnostics instead of only a single ``detail`` string. The validation items the shared
``build_validation_error_items`` builds ride beside it, one per problem item.
"""

from mthds.protocol.problem.registry import CoreCode, ProblemDomain, RetryVerdict, StepKind

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView, caller_view_of
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.validation_error_types import PipeValidationErrorType


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


class TestValidateBundleErrorProblem:
    def test_the_problem_lists_one_item_per_underlying_error(self) -> None:
        """Each underlying error is an item with its own code and its file, in the order the validation items list them."""
        error = _error_with_two_categories()
        problem = error.to_problem(view=ProblemView.CALLER)

        assert problem.errors is not None
        assert [(item.code, item.location.file if item.location else None) for item in problem.errors] == [
            (CoreCode.METHOD_IDENTIFIER_INVALID, "main.mthds"),
            (CoreCode.METHOD_INPUT_UNDECLARED, "helpers.mthds"),
        ]
        assert [item.source for item in error.validation_error_items()] == ["main.mthds", "helpers.mthds"]

    def test_the_verdict_is_the_method_s_fault(self) -> None:
        """An invalid verdict is the method's to fix and is never retried; its class is the operator's diagnostics."""
        error = _error_with_two_categories()
        caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.METHOD_INVALID
        assert caller.domain == ProblemDomain.METHOD
        assert caller.retry == RetryVerdict.NO
        assert caller.next_step.kind == StepKind.CHANGE_METHOD
        assert error_code_spec(CoreCode.METHOD_INVALID).status == 422
        assert caller.diagnostics is None
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "ValidateBundleError"

    def test_message_only_error_surfaces_a_residual_item(self) -> None:
        """No categorized errors → a ``blueprint_validation`` residual still rides the verdict (the invariant is total).

        ``validation_error_items`` passes ``fallback_message=self.message``, so a parse-level failure that carries
        only a message (TOML syntax, an empty blueprint, a bundle elaborator) projects one residual item, and its
        problem one ``method.schema_violation`` item, rather than a bare ``detail`` with no items.
        """
        error = ValidateBundleError(message="generic failure")

        items = error.validation_error_items()
        assert [item.category for item in items] == [ValidationErrorCategory.BLUEPRINT_VALIDATION]
        assert items[0].message == "generic failure"
        problem = error.to_problem(view=ProblemView.CALLER)
        assert problem.errors is not None
        assert [item.code for item in problem.errors] == [CoreCode.METHOD_SCHEMA_VIOLATION]

    def test_the_caller_view_of_the_operator_s_record_keeps_the_items(self) -> None:
        """The items are the caller's own bundle diagnostics, so the caller view of the operator's problem keeps every one."""
        operator = _error_with_two_categories().to_problem(view=ProblemView.OPERATOR)

        caller = caller_view_of(problem=operator)

        assert caller.diagnostics is None
        assert caller.errors == operator.errors
        wire_errors = caller.to_wire()["errors"]
        assert {item["location"]["file"] for item in wire_errors} == {"main.mthds", "helpers.mthds"}
