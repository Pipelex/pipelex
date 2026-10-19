import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, SecurityError, ValidationErrorCategory, ValidationErrorItem
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.exceptions import DryRunFailureErrorData
from pipelex.core.pipes.exceptions import PipeLoadRefusalError, PipeOperatorModelChoiceError, PipeRunError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType


class _InternalInputRefusalError(PipelexError):
    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class _RuntimeFaultError(PipelexError):
    error_code = CoreCode.RUNTIME_UNAVAILABLE


class _UnclassifiedFaultError(PipelexError):
    pass


class _InputSecurityRefusalError(SecurityError):
    error_code = CoreCode.SECURITY_TEMPLATE_REFUSED


# What the item of a refusal whose raise site gave no parameters reads: its code's title.
_INTERNAL_REFUSAL_TITLE = error_code_spec(CoreCode.METHOD_SCHEMA_VIOLATION).title


def _verdict_items(refusal: BaseException) -> tuple[ValidateBundleError, list[ValidationErrorItem]]:
    with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
        raise refusal
    verdict = raised.value
    assert verdict.__cause__ is refusal
    return verdict, list(verdict.validation_error_items() or [])


class TestRefusalVerdictArms:
    def test_unlocated_input_refusal_is_one_blueprint_item_reading_its_code_s_sentence(self) -> None:
        """The item reads the sentence the refusal's code renders from the parameters its raise site gave, never its message."""
        refusal = _InternalInputRefusalError("internal detail: registry slot 7 is stale").with_params(
            field_path="pipe.tide_table", finding="the tide table names a harbour that does not exist"
        )

        verdict, items = _verdict_items(refusal)

        sentence = "The declaration at 'pipe.tide_table' breaks a rule of the language (the tide table names a harbour that does not exist)."
        assert items == [ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message=sentence)]
        assert verdict.message == sentence
        problem = verdict.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        (problem_item,) = problem.errors or []
        assert problem_item.code == CoreCode.METHOD_SCHEMA_VIOLATION
        assert "registry slot 7" not in str(problem.to_wire())

    @pytest.mark.builds_problems_without_required_params(
        reason="builds a refusal with no parameters, to check that its item is named by its code's title"
    )
    def test_an_input_refusal_with_no_parameters_is_named_by_its_title(self) -> None:
        _, items = _verdict_items(_InternalInputRefusalError("internal detail: registry slot 7 is stale"))

        assert [item.message for item in items] == [_INTERNAL_REFUSAL_TITLE]

    def test_located_refusal_is_one_pipe_item_with_pipe_domain_and_source(self) -> None:
        cause = _InternalInputRefusalError("internal detail: registry slot 7 is stale")
        located = PipeLoadRefusalError.make_from_refusal(refusal=cause, pipe_code="write_tide_note", domain_code="tide_tables", source="tides.mthds")

        _, items = _verdict_items(located)

        assert items == [
            ValidationErrorItem(
                category=ValidationErrorCategory.PIPE_VALIDATION,
                pipe_code="write_tide_note",
                domain_code="tide_tables",
                source="tides.mthds",
                message=(
                    "The declaration at 'pipe.write_tide_note' breaks a rule of the language (the pipe could not be built from its declaration)."
                ),
            )
        ]

    def test_unknown_model_is_one_unknown_model_item(self) -> None:
        refusal = PipeOperatorModelChoiceError(
            "Pipe 'write_tide_note' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck",
            pipe_type="PipeLLM",
            pipe_code="write_tide_note",
            domain_code="tide_tables",
            field_name="model",
            model_type=ModelType.LLM,
            model_choice="gpt-5.1",
            suggestions=["gpt-5.5", "gpt-5.4"],
            source="tides.mthds",
        )

        _, items = _verdict_items(refusal)

        assert items == [
            ValidationErrorItem(
                category=ValidationErrorCategory.PIPE_VALIDATION,
                error_type=PipeValidationErrorType.UNKNOWN_MODEL,
                pipe_code="write_tide_note",
                domain_code="tide_tables",
                source="tides.mthds",
                field_path="pipe.write_tide_note.model",
                field_name="model",
                model_reference="gpt-5.1",
                model_type="llm",
                suggestions=["gpt-5.5", "gpt-5.4"],
                message="Pipe 'write_tide_note' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck",
            )
        ]

    @pytest.mark.parametrize(
        "fault",
        [
            _RuntimeFaultError("the worker lost its connection"),
            _UnclassifiedFaultError("something nobody classified"),
            _InputSecurityRefusalError("a fetch was blocked"),
            LibraryError("the library manager lost a library it had opened"),
            LibraryError("one PipeFunc source sits in two library directories").with_error_code(PipelexErrorCode.CONFIG_INVALID),
        ],
        ids=["runtime", "unclassified", "security", "library_invariant", "library_configuration"],
    )
    def test_no_verdict_faults_propagate_unchanged(self, fault: PipelexError) -> None:
        """A failure of the tool or its environment, and a security refusal, are never reported as the bundle's fault."""
        with pytest.raises(type(fault)) as raised, translate_to_validate_bundle_error():
            raise fault
        assert raised.value is fault

    def test_a_pipe_run_failure_wrapping_a_security_refusal_is_no_verdict(self) -> None:
        """The refusal is the method's to act on, yet a security rule made it: the wrapper keeps its code, never a verdict."""
        refusal = _InputSecurityRefusalError("a template read a private name")
        wrapper = PipeRunError("Pipe 'say' failed", run_mode=PipeRunMode.DRY, pipe_code="say")
        wrapper.__cause__ = refusal

        with pytest.raises(PipeRunError) as raised, translate_to_validate_bundle_error():
            raise wrapper

        assert raised.value is wrapper
        assert wrapper.resolve_error_code() == CoreCode.SECURITY_TEMPLATE_REFUSED

    @pytest.mark.builds_problems_without_required_params(reason="builds dry-run failures in the test, without the parameters a sweep records")
    def test_a_sweep_with_a_security_refusal_among_its_failures_is_no_verdict(self) -> None:
        """One method fault beside one security refusal: the sweep answers the refusal's code, never an invalid verdict."""
        sweep = DryRunError(
            "Dry run failed for 2 pipe(s)",
            failures=[
                DryRunFailureErrorData(pipe_code="route_parcel", message="the round has no lane", code=CoreCode.PIPE_CONDITION_UNMATCHED),
                DryRunFailureErrorData(pipe_code="say", message="a template was refused", code=CoreCode.SECURITY_TEMPLATE_REFUSED),
            ],
        )

        with pytest.raises(DryRunError) as raised, translate_to_validate_bundle_error():
            raise sweep

        assert raised.value is sweep
        assert sweep.resolve_error_code() == CoreCode.SECURITY_TEMPLATE_REFUSED
        assert [item.code for item in sweep.to_problem(view=ProblemView.CALLER).errors or []] == [
            CoreCode.PIPE_CONDITION_UNMATCHED,
            CoreCode.SECURITY_TEMPLATE_REFUSED,
        ]

    def test_a_produced_verdict_passes_through_unwrapped(self) -> None:
        verdict = ValidateBundleError(
            message="already a verdict",
            dry_run_failures=[
                DryRunFailureErrorData(pipe_code="route_parcel", message="the round has no lane", code=CoreCode.PIPE_CONDITION_UNMATCHED)
            ],
        )

        with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
            raise verdict

        assert raised.value is verdict
