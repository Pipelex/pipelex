import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, SecurityError, ValidationErrorCategory, ValidationErrorItem
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.exceptions import DryRunFailureErrorData
from pipelex.core.pipes.exceptions import PipeLoadRefusalError, PipeOperatorModelChoiceError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.validation_error_types import PipeValidationErrorType


class _CallerFacingInputRefusalError(PipelexError):
    error_code = CoreCode.METHOD_INVALID
    _authors_caller_facing_message = True


class _InternalInputRefusalError(PipelexError):
    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class _RuntimeFaultError(PipelexError):
    error_code = CoreCode.RUNTIME_UNAVAILABLE


class _UnclassifiedFaultError(PipelexError):
    pass


class _InputSecurityRefusalError(SecurityError):
    error_code = CoreCode.SECURITY_TEMPLATE_REFUSED
    _authors_caller_facing_message = True


# What a non-caller-facing refusal's item reads: its code's title.
_INTERNAL_REFUSAL_TITLE = error_code_spec(CoreCode.METHOD_SCHEMA_VIOLATION).title


def _verdict_items(refusal: BaseException) -> tuple[ValidateBundleError, list[ValidationErrorItem]]:
    with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
        raise refusal
    verdict = raised.value
    assert verdict.__cause__ is refusal
    return verdict, list(verdict.to_error_report().validation_errors or [])


class TestRefusalVerdictArms:
    def test_unlocated_caller_facing_input_refusal_is_one_blueprint_item_keeping_its_message(self) -> None:
        verdict, items = _verdict_items(_CallerFacingInputRefusalError("The tide table names a harbour that does not exist."))

        assert items == [
            ValidationErrorItem(
                category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
                message="The tide table names a harbour that does not exist.",
            )
        ]
        assert verdict.message == "The tide table names a harbour that does not exist."

    def test_non_caller_facing_input_refusal_is_named_by_its_title(self) -> None:
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
                message=f"Pipe 'write_tide_note' could not be loaded: {_INTERNAL_REFUSAL_TITLE}",
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

    def test_a_produced_verdict_passes_through_unwrapped(self) -> None:
        verdict = ValidateBundleError(
            message="already a verdict",
            dry_run_failures=[DryRunFailureErrorData(pipe_code="route_parcel", message="the round has no lane")],
        )

        with pytest.raises(ValidateBundleError) as raised, translate_to_validate_bundle_error():
            raise verdict

        assert raised.value is verdict
