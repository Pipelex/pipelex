import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ErrorDomain, PipelexConfigError, PipelexError, PipelexSetupError
from pipelex.cogt.exceptions import (
    CogtError,
    ImgGenParameterError,
    ImgGenPromptError,
    InferenceBackendLibraryError,
    InferenceErrorCategory,
    LLMPromptParameterError,
    PromptDocumentFactoryError,
    PromptImageFactoryError,
    PromptImageFormatError,
    SdkTypeError,
)
from pipelex.core.stuffs.exceptions import DateContentError
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.pipe.exceptions import EntryPipeAmbiguousError, EntryPipeNotFoundError, PipeLibraryError, PipeNotFoundError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.pipeline.exceptions import (
    PipeExecutionError,
    PipelineExecutionError,
    PipelineInputContentError,
    PipelineInputUrlMissingError,
    ValidateBundleError,
)
from pipelex.plugins.exceptions import UnknownSecretsMethodError, UnknownStorageMethodError
from pipelex.system.exceptions import EnvVarNotFoundError
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.tabular.exceptions import CsvError

_PIPELINE_EXEC_ERROR = PipelineExecutionError(
    message="boom",
    run_mode=PipeRunMode.LIVE,
    pipe_code="some_pipe",
    output_name=None,
    pipe_stack=[],
)


class TestClassLevelMetadata:
    """Key exceptions self-describe their code, user_action and error_category at the class level."""

    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_code", "expected_domain"),
        [
            # The run's wrapper takes its cause's code, and with no cause its fallback.
            ("pipeline_execution", _PIPELINE_EXEC_ERROR, CoreCode.RUNTIME_UNEXPECTED, ErrorDomain.RUNTIME),
            ("pipe_execution", PipeExecutionError("boom"), CoreCode.RUNTIME_UNEXPECTED, ErrorDomain.RUNTIME),
            ("validate_bundle", ValidateBundleError("boom"), CoreCode.METHOD_INVALID, ErrorDomain.INPUT),
            ("pipeline_input_content", PipelineInputContentError("boom"), PipelexErrorCode.STORAGE_URI_INVALID, ErrorDomain.INPUT),
            # The entry-shaped lookups report a pipe_code the caller supplied, so a typo is theirs
            # to fix — 422, never the 500 a runtime fault renders as.
            ("entry_pipe_not_found", EntryPipeNotFoundError("boom"), CoreCode.REQUEST_PIPE_NOT_FOUND, ErrorDomain.INPUT),
            ("entry_pipe_ambiguous", EntryPipeAmbiguousError("boom"), CoreCode.REQUEST_PIPE_AMBIGUOUS, ErrorDomain.INPUT),
            ("interpreter", MthdsParserError("boom"), CoreCode.METHOD_INVALID, ErrorDomain.INPUT),
            ("setup", PipelexSetupError("boom"), CoreCode.RUNTIME_MISCONFIGURED, ErrorDomain.CONFIG),
            ("config", PipelexConfigError("boom"), PipelexErrorCode.CONFIG_INVALID, ErrorDomain.CONFIG),
            ("env_var_not_found", EnvVarNotFoundError("boom"), PipelexErrorCode.CONFIG_VARIABLE_MISSING, ErrorDomain.CONFIG),
        ],
    )
    def test_error_code(self, _topic: str, exc: PipelexError, expected_code: ErrorCode, expected_domain: ErrorDomain) -> None:
        """The targeted exceptions report their class's code, and the domain it decides, in to_error_report()."""
        report = exc.to_error_report()
        assert report.code == expected_code
        assert report.error_domain == expected_domain

    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_detail"),
        [
            ("pipeline_execution", _PIPELINE_EXEC_ERROR, "The run of 'some_pipe' failed: the message gives the cause."),
            (
                "validate_bundle",
                ValidateBundleError("boom"),
                "Edit the bundle as each validation error says: apply its suggested fix where it has one, after confirming an unsafe one",
            ),
            (
                "entry_pipe_not_found",
                EntryPipeNotFoundError("boom"),
                "Check the pipe code for typos and make sure the bundle in scope for this operation declares it.",
            ),
            (
                "entry_pipe_ambiguous",
                EntryPipeAmbiguousError("boom"),
                "Name one candidate explicitly: 'domain.pipe_code', or 'alias->domain.pipe_code' for a cross-package code.",
            ),
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
            ("prompt_parameter", LLMPromptParameterError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_image_factory", PromptImageFactoryError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_image_format", PromptImageFormatError("x"), InferenceErrorCategory.CONTENT),
            ("prompt_document_factory", PromptDocumentFactoryError("x"), InferenceErrorCategory.CONTENT),
            ("imggen_prompt", ImgGenPromptError("x"), InferenceErrorCategory.CONTENT),
            ("imggen_parameter", ImgGenParameterError("x"), InferenceErrorCategory.CONTENT),
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
            ("interpreter", MthdsParserError("boom"), True),
            ("validate_bundle", ValidateBundleError("boom"), True),
            # Regression pin: this class declared the *report field* name (``caller_facing_message``)
            # instead of the class-level flag (``_authors_caller_facing_message``), so its
            # caller-facing message was silently redacted under STRICT disclosure.
            ("pipeline_input_url_missing", PipelineInputUrlMissingError("boom"), True),
            # Security pin, and the reason the family is split: this class's message names the
            # resolved local path and the OSError subclass that rejected it. Flagging it
            # caller-facing would let STRICT disclosure answer "does this server-side path exist,
            # and may the runner read it?" for any authenticated caller.
            ("pipeline_input_content", PipelineInputContentError("boom"), False),
            # The entry-lookup messages name the caller's own pipe_code and the qualified pipe_refs
            # of bundles they loaded themselves — nothing server-side — and the candidate list is
            # the only thing that makes an ambiguity actionable, so redacting it would gut the error.
            ("entry_pipe_not_found", EntryPipeNotFoundError("boom"), True),
            ("entry_pipe_ambiguous", EntryPipeAmbiguousError("boom"), True),
            # The in-body doors stay redacted: their refs come from a bundle, not from the caller.
            ("pipe_not_found", PipeNotFoundError("boom"), False),
            ("pipe_library", PipeLibraryError("boom"), False),
            ("csv", CsvError("boom"), True),
            ("unknown_storage_method", UnknownStorageMethodError(method="bogus", registered_methods=["local", "s3"]), True),
            ("unknown_secrets_method", UnknownSecretsMethodError(method="bogus", registered_methods=["env"]), True),
            ("date_content", DateContentError("boom"), True),
            ("config", PipelexConfigError("boom"), False),
            ("pipe_execution", PipeExecutionError("boom"), False),
            ("cogt", CogtError("boom"), False),
        ],
    )
    def test_caller_facing_message(self, _topic: str, exc: PipelexError, expected_caller_facing: bool) -> None:
        """Only classes whose message describes the caller's own input carry caller_facing_message in to_error_report().

        ``MthdsParserError`` / ``ValidateBundleError`` author caller-facing
        copy (.mthds syntax, bundle validation); every other class defaults to
        False so STRICT disclosure redacts its message.
        """
        report = exc.to_error_report()
        assert report.caller_facing_message is expected_caller_facing

    def test_caller_facing_message_inherits_for_interpreter_subclass(self) -> None:
        """A subclass of ``MthdsParserError`` stays caller-facing.

        Pins the deliberate inheritance contract on ``_authors_caller_facing_message``
        (plain attribute access — see ``base_exceptions.py``): a future refactor
        swapping the flag to ``cls.__dict__`` lookup (the path the error-code gate
        uses for ``error_code``) would silently downgrade
        STRICT disclosure for every subclass and let internal messages leak under
        STRICT — or, more likely, silently redact authored caller-facing copy.
        """

        class _SubInterpreterError(MthdsParserError):
            pass

        report = _SubInterpreterError("boom").to_error_report()
        assert report.caller_facing_message is True

    def test_caller_facing_message_inherits_for_validate_bundle_subclass(self) -> None:
        """A subclass of ``ValidateBundleError`` stays caller-facing — same contract as the interpreter case."""

        class _SubValidateBundleError(ValidateBundleError):
            pass

        report = _SubValidateBundleError("boom").to_error_report()
        assert report.caller_facing_message is True
