import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.base_exceptions import PipelexConfigError, PipelexError, PipelexSetupError
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
    find_inference_error_category_in_chain,
)
from pipelex.core.stuffs.exceptions import DateContentError
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.problem import ProblemView
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

# A message naming a path on the host, which no caller may read whatever the class.
_HOST_MESSAGE = "boom at /srv/pipelex/internal/library.mthds"

_PIPELINE_EXEC_ERROR = PipelineExecutionError(
    message="boom",
    run_mode=PipeRunMode.LIVE,
    pipe_code="some_pipe",
    output_name=None,
    pipe_stack=[],
)


class TestClassLevelMetadata:
    """Key exceptions self-describe their code, their advice and their error_category at the class level."""

    @pytest.mark.builds_problems_without_required_params(reason="builds each class with a message alone, to check the code it decides")
    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_code", "expected_domain"),
        [
            # The run's wrapper takes its cause's code, and with no cause its fallback.
            ("pipeline_execution", _PIPELINE_EXEC_ERROR, CoreCode.RUNTIME_UNEXPECTED, ProblemDomain.RUNTIME),
            ("pipe_execution", PipeExecutionError("boom"), CoreCode.RUNTIME_UNEXPECTED, ProblemDomain.RUNTIME),
            ("validate_bundle", ValidateBundleError("boom"), CoreCode.METHOD_INVALID, ProblemDomain.METHOD),
            ("pipeline_input_content", PipelineInputContentError("boom"), PipelexErrorCode.STORAGE_URI_INVALID, ProblemDomain.INPUT),
            # The entry-shaped lookups report a pipe_code the caller supplied, so a typo is theirs
            # to fix — 422, never the 500 a runtime fault renders as.
            ("entry_pipe_not_found", EntryPipeNotFoundError("boom"), CoreCode.REQUEST_PIPE_NOT_FOUND, ProblemDomain.INPUT),
            ("entry_pipe_ambiguous", EntryPipeAmbiguousError("boom"), CoreCode.REQUEST_PIPE_AMBIGUOUS, ProblemDomain.INPUT),
            ("interpreter", MthdsParserError("boom"), CoreCode.METHOD_INVALID, ProblemDomain.METHOD),
            ("setup", PipelexSetupError("boom"), CoreCode.RUNTIME_MISCONFIGURED, ProblemDomain.OPERATOR),
            ("config", PipelexConfigError("boom"), PipelexErrorCode.CONFIG_INVALID, ProblemDomain.OPERATOR),
            ("env_var_not_found", EnvVarNotFoundError("boom"), PipelexErrorCode.CONFIG_VARIABLE_MISSING, ProblemDomain.OPERATOR),
        ],
    )
    def test_error_code(self, _topic: str, exc: PipelexError, expected_code: ErrorCode, expected_domain: ProblemDomain) -> None:
        """The targeted exceptions' problem carries their class's code, and the domain it decides."""
        problem = exc.to_problem(view=ProblemView.CALLER)
        assert problem.code == expected_code
        assert problem.domain == expected_domain

    @pytest.mark.builds_problems_without_required_params(reason="builds each class with a message alone, to check the advice it carries")
    @pytest.mark.parametrize(
        ("_topic", "exc", "expected_detail"),
        [
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
    def test_advised_action(self, _topic: str, exc: PipelexError, expected_detail: str) -> None:
        """The targeted exceptions carry their advice, the local CLI's tip, which no problem carries."""
        advice = exc.advised_action()
        assert advice is not None
        assert advice.detail == expected_detail
        assert expected_detail not in str(exc.to_problem(view=ProblemView.OPERATOR).to_wire())

    def test_a_run_wrapper_with_no_cause_advises_nothing(self) -> None:
        """No fallback advice is invented: the problem's next step, from the code, is what the reader follows."""
        assert _PIPELINE_EXEC_ERROR.advised_action() is None
        assert _PIPELINE_EXEC_ERROR.to_problem(view=ProblemView.CALLER).next_step.detail == "Report this to whoever runs the runtime."

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
        """The previously-uncategorized CogtError subclasses carry a class-level error_category, which the chain walk finds."""
        assert exc.error_category is expected_category
        assert find_inference_error_category_in_chain(exc) is expected_category

    @pytest.mark.builds_problems_without_required_params(reason="builds each class with a message alone, to check where the message goes")
    @pytest.mark.parametrize(
        ("_topic", "exc"),
        [
            ("interpreter", MthdsParserError(_HOST_MESSAGE)),
            # A `ValidateBundleError` is left out: its items are the verdict about the caller's own bundle, which the caller
            # reads, a message with no categorized data riding as its residual item.
            ("pipeline_input_url_missing", PipelineInputUrlMissingError(_HOST_MESSAGE)),
            # Security pin: this class's message names the resolved local path and the OSError subclass that
            # rejected it, which would answer "does this server-side path exist, and may the runner read it?".
            ("pipeline_input_content", PipelineInputContentError(_HOST_MESSAGE)),
            ("entry_pipe_not_found", EntryPipeNotFoundError(_HOST_MESSAGE)),
            ("entry_pipe_ambiguous", EntryPipeAmbiguousError(_HOST_MESSAGE)),
            ("pipe_not_found", PipeNotFoundError(_HOST_MESSAGE)),
            ("pipe_library", PipeLibraryError(_HOST_MESSAGE)),
            ("csv", CsvError(_HOST_MESSAGE)),
            ("date_content", DateContentError(_HOST_MESSAGE)),
            ("config", PipelexConfigError(_HOST_MESSAGE)),
            ("pipe_execution", PipeExecutionError(_HOST_MESSAGE)),
            ("cogt", CogtError(_HOST_MESSAGE)),
        ],
    )
    def test_a_message_reaches_the_operator_alone(self, _topic: str, exc: PipelexError) -> None:
        """Whatever the class, its message rides the operator's diagnostics and never the caller's view.

        The caller reads the sentences its code renders, so no class has to vouch that its message is safe to show.
        """
        caller = exc.to_problem(view=ProblemView.CALLER)
        operator = exc.to_problem(view=ProblemView.OPERATOR)
        assert _HOST_MESSAGE not in str(caller.to_wire())
        assert "/srv/pipelex" not in str(caller.to_wire())
        assert operator.diagnostics is not None
        assert operator.diagnostics.message == _HOST_MESSAGE

    @pytest.mark.parametrize(
        ("_topic", "exc"),
        [
            ("unknown_storage_method", UnknownStorageMethodError(method="bogus", registered_methods=["local", "s3"])),
            ("unknown_secrets_method", UnknownSecretsMethodError(method="bogus", registered_methods=["env"])),
        ],
    )
    def test_a_plugin_choice_refusal_names_its_value_to_the_operator(self, _topic: str, exc: PipelexError) -> None:
        operator = exc.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert "bogus" in operator.diagnostics.message
