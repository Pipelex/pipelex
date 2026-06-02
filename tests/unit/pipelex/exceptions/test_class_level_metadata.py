import pytest

from pipelex.base_exceptions import ErrorDomain, PipelexConfigError, PipelexError, PipelexSetupError
from pipelex.cogt.exceptions import (
    CogtError,
    ImageContentError,
    ImgGenParameterError,
    ImgGenPromptError,
    InferenceBackendLibraryError,
    InferenceErrorCategory,
    LLMPromptParameterError,
    LLMPromptSpecError,
    LLMPromptTemplateInputsError,
    PromptDocumentFactoryError,
    PromptImageFactoryError,
    PromptImageFormatError,
    SdkTypeError,
)
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError, ValidateBundleError
from pipelex.system.exceptions import EnvVarNotFoundError
from pipelex.system.pipelex_service.exceptions import (
    GatewayTermsNotAcceptedError,
    PipelexServiceConfigValidationError,
    PipelexServiceError,
    RemoteConfigFetchError,
)
from pipelex.tools.tabular.exceptions import CsvError

_PIPELINE_EXEC_ERROR = PipelineExecutionError(
    message="boom",
    run_mode=PipeRunMode.LIVE,
    pipe_code="some_pipe",
    output_name=None,
    pipe_stack=[],
)


class TestClassLevelMetadata:
    """Key exceptions self-describe error_domain / user_action / error_category at the class level."""

    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_domain"),
        [
            ("pipeline_execution", _PIPELINE_EXEC_ERROR, ErrorDomain.RUNTIME),
            ("pipe_execution", PipeExecutionError("boom"), ErrorDomain.RUNTIME),
            ("validate_bundle", ValidateBundleError("boom"), ErrorDomain.INPUT),
            ("interpreter", PipelexInterpreterError("boom"), ErrorDomain.INPUT),
            ("setup", PipelexSetupError("boom"), ErrorDomain.CONFIG),
            ("config", PipelexConfigError("boom"), ErrorDomain.CONFIG),
            ("service_base", PipelexServiceError("boom"), ErrorDomain.CONFIG),
            ("service_config_validation", PipelexServiceConfigValidationError("boom"), ErrorDomain.CONFIG),
            ("remote_config_fetch", RemoteConfigFetchError("boom"), ErrorDomain.CONFIG),
            ("gateway_terms", GatewayTermsNotAcceptedError(), ErrorDomain.CONFIG),
            ("env_var_not_found", EnvVarNotFoundError("boom"), ErrorDomain.CONFIG),
        ],
    )
    def test_error_domain(self, _topic: str, exc: PipelexError, expected_domain: ErrorDomain) -> None:
        """The targeted exceptions carry their expected error_domain in to_error_report()."""
        report = exc.to_error_report()
        assert report.error_domain == expected_domain

    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_detail"),
        [
            ("pipeline_execution", _PIPELINE_EXEC_ERROR, "Check pipe_stack to identify which pipe failed"),
            ("validate_bundle", ValidateBundleError("boom"), "Check the validation_errors array for specific issues"),
        ],
    )
    def test_user_action(self, _topic: str, exc: PipelexError, expected_detail: str) -> None:
        """The targeted exceptions carry their expected user_action detail in to_error_report()."""
        report = exc.to_error_report()
        assert report.user_action is not None
        assert report.user_action.detail == expected_detail

    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_category"),
        [
            ("prompt_spec", LLMPromptSpecError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_template", LLMPromptTemplateInputsError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_parameter", LLMPromptParameterError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_image_factory", PromptImageFactoryError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_image_format", PromptImageFormatError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_document_factory", PromptDocumentFactoryError("x"), InferenceErrorCategory.CONTENT),
            ("imggen_prompt", ImgGenPromptError("x"), InferenceErrorCategory.CONTENT),
            ("imggen_parameter", ImgGenParameterError("x"), InferenceErrorCategory.CONTENT),
            ("image_content", ImageContentError("x"), InferenceErrorCategory.CONTENT),
            ("sdk_type", SdkTypeError("x"), InferenceErrorCategory.CONFIGURATION),
            ("backend_library", InferenceBackendLibraryError("x"), InferenceErrorCategory.CONFIGURATION),
        ],
    )
    def test_error_category(self, _topic: str, exc: CogtError, expected_category: InferenceErrorCategory) -> None:
        """The previously-uncategorized CogtError subclasses now report a class-level error_category."""
        report = exc.to_error_report()
        assert exc.error_category is expected_category
        assert report.error_category == expected_category

    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_caller_facing"),
        [
            ("interpreter", PipelexInterpreterError("boom"), True),
            ("validate_bundle", ValidateBundleError("boom"), True),
            ("csv", CsvError("boom"), True),
            ("config", PipelexConfigError("boom"), False),
            ("pipe_execution", PipeExecutionError("boom"), False),
            ("cogt", CogtError("boom"), False),
        ],
    )
    def test_caller_facing_message(self, _topic: str, exc: PipelexError, expected_caller_facing: bool) -> None:
        """Only classes whose message describes the caller's own input carry caller_facing_message in to_error_report().

        ``PipelexInterpreterError`` / ``ValidateBundleError`` author caller-facing
        copy (.mthds syntax, bundle validation); every other class defaults to
        False so STRICT disclosure redacts its message.
        """
        report = exc.to_error_report()
        assert report.caller_facing_message is expected_caller_facing

    def test_caller_facing_message_inherits_for_interpreter_subclass(self) -> None:
        """A subclass of ``PipelexInterpreterError`` stays caller-facing.

        Pins the deliberate inheritance contract on ``_authors_caller_facing_message``
        (plain attribute access — see ``base_exceptions.py``): a future refactor
        swapping the flag to ``cls.__dict__`` lookup (the path used by
        ``_declared_title`` / ``_declared_type_uri``) would silently downgrade
        STRICT disclosure for every subclass and let internal messages leak under
        STRICT — or, more likely, silently redact authored caller-facing copy.
        """

        class _SubInterpreterError(PipelexInterpreterError):
            pass

        report = _SubInterpreterError("boom").to_error_report()
        assert report.caller_facing_message is True

    def test_caller_facing_message_inherits_for_validate_bundle_subclass(self) -> None:
        """A subclass of ``ValidateBundleError`` stays caller-facing — same contract as the interpreter case."""

        class _SubValidateBundleError(ValidateBundleError):
            pass

        report = _SubValidateBundleError("boom").to_error_report()
        assert report.caller_facing_message is True
