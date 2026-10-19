from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from mthds.protocol.problem.registry import CoreCode, ModelContextExceededLimit, ModelUnavailableReason
from typing_extensions import override

from pipelex.base_exceptions import PipelexError, ProblemFacts, iter_cause_chain
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReferenceKind
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet, InheritsCause, declared_error_codes
from pipelex.errors.problem import ProviderDiagnostics, cap_problem_text
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode

if TYPE_CHECKING:
    from pipelex.errors.error_codes import ErrorCode


class InferenceErrorCategory(StrEnum):
    """The runtime's own classification of an inference failure, which picks its registry code.

    It stays inside the runtime: a report's domain and retry verdict are its code's, and the category is
    what the classification (``pipelex.cogt.inference.error_classify``) reads to pick that code, and what the
    Temporal activity reads to decide whether a provider call may be repeated within the run, since a call
    whose outcome is unknown must not be, though a new run may succeed (the census's question 6).
    """

    TRANSIENT = "transient"
    CONFIGURATION = "configuration"
    CONTENT = "content"
    CAPACITY = "capacity"
    # The error type is known, but the outcome is not: the operation may or may not have committed
    # (e.g. a connection dropped mid-request). A blind retry is unsafe for a non-idempotent
    # operation, so this is non-retryable — distinct from UNKNOWN, which means "could not classify".
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"

    @property
    def is_retryable(self) -> bool:
        match self:
            case InferenceErrorCategory.TRANSIENT:
                return True
            case (
                InferenceErrorCategory.CONFIGURATION
                | InferenceErrorCategory.CONTENT
                | InferenceErrorCategory.CAPACITY
                | InferenceErrorCategory.AMBIGUOUS
                | InferenceErrorCategory.UNKNOWN
            ):
                return False

    @property
    def is_outcome_unknown(self) -> bool:
        """Whether the failed call may have taken effect, so it must not be repeated within the run."""
        match self:
            case InferenceErrorCategory.AMBIGUOUS:
                return True
            case (
                InferenceErrorCategory.TRANSIENT
                | InferenceErrorCategory.CONFIGURATION
                | InferenceErrorCategory.CONTENT
                | InferenceErrorCategory.CAPACITY
                | InferenceErrorCategory.UNKNOWN
            ):
                return False

    @property
    def default_error_code(self) -> ErrorCode | None:
        """The code an error naming this category and no code reports, ``None`` where the category alone names none.

        The classification picks a code with every category it reads. This serves an error a worker or a plugin builds
        by hand with a category alone, whose report must agree with what the category says: a transient failure invites
        a retry, which ``runtime.unexpected`` does not, and a configuration failure is the operator's to fix. A content
        failure may be the caller's input or a request the runtime built, so it names no code, and neither does an
        unknown one: such an error keeps its class's fallback.
        """
        match self:
            case InferenceErrorCategory.TRANSIENT:
                return CoreCode.PROVIDER_UNAVAILABLE
            case InferenceErrorCategory.CONFIGURATION:
                return CoreCode.RUNTIME_MISCONFIGURED
            case InferenceErrorCategory.CAPACITY:
                return CoreCode.PROVIDER_QUOTA_EXHAUSTED
            case InferenceErrorCategory.AMBIGUOUS:
                return CoreCode.PROVIDER_OUTCOME_UNKNOWN
            case InferenceErrorCategory.CONTENT | InferenceErrorCategory.UNKNOWN:
                return None


# Every code the inference classification picks for a failed provider call (``pipelex.cogt.inference.error_classify``),
# from the status ladder, the status-less type tables and the service error vocabulary a plugin contributes. Each
# family's failure class declares them all, so that the Render step constructs it with the code the classification
# chose, and the vocabulary refuses an entry naming a code outside them. ``model.unavailable`` is also the code of the
# families' not-found classes.
INFERENCE_FAILURE_CODES: tuple[ErrorCode, ...] = (
    CoreCode.RUNTIME_UNEXPECTED,
    CoreCode.RUNTIME_MISCONFIGURED,
    CoreCode.PROVIDER_RATE_LIMITED,
    CoreCode.PROVIDER_UNAVAILABLE,
    CoreCode.PROVIDER_TIMEOUT,
    CoreCode.PROVIDER_FAILED,
    CoreCode.PROVIDER_RESPONSE_INVALID,
    CoreCode.PROVIDER_CREDENTIAL_REFUSED,
    CoreCode.PROVIDER_QUOTA_EXHAUSTED,
    CoreCode.PROVIDER_OUTCOME_UNKNOWN,
    CoreCode.MODEL_UNAVAILABLE,
    CoreCode.MODEL_CAPABILITY_UNSUPPORTED,
    CoreCode.MODEL_CONTEXT_EXCEEDED,
    CoreCode.MODEL_CONTENT_REFUSED,
    CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH,
    CoreCode.MODEL_NO_RESULT,
    CoreCode.INPUT_TOO_LARGE,
    CoreCode.INPUT_FILE_TYPE_UNSUPPORTED,
    CoreCode.INPUT_FILE_UNREADABLE,
    CoreCode.INPUT_REFERENCE_NOT_FOUND,
    CoreCode.INPUT_URL_UNREACHABLE,
    CoreCode.SECURITY_INPUT_URL_REFUSED,
    CoreCode.SECURITY_METHOD_URL_REFUSED,
    PipelexErrorCode.CONFIG_INVALID,
    PipelexErrorCode.CONFIG_CREDENTIAL_MISSING,
    PipelexErrorCode.BILLING_CREDIT_EXHAUSTED,
)


def _inference_failure_declaration(*, fallback: ErrorCode) -> InheritsCause:
    """The declaration of a family's failure class: its cause's code, else the fallback, or any classified code chosen."""
    return InheritsCause(fallback=fallback, others=tuple(code for code in INFERENCE_FAILURE_CODES if code is not fallback))


class CogtError(PipelexError):
    """The base of the inference layer's errors, which carry the provider facts a classification reads.

    Never raised directly: a subclass declares its code, or the set the classification picks from
    (``pipelex.cogt.inference.error_classify``), where ``error_category`` stays the runtime's own reading of
    the failure.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR
    error_category: InferenceErrorCategory | None = None
    user_action: UserAction | None = None
    provider_metadata: ProviderErrorMetadata | None = None
    model_handle: str | None = None
    backend_name: str | None = None

    def __init__(
        self,
        message: str,
        error_category: InferenceErrorCategory | None = None,
        user_action: UserAction | None = None,
        provider_metadata: ProviderErrorMetadata | None = None,
        backend_name: str | None = None,
    ):
        super().__init__(message)
        if error_category is not None:
            self.error_category = error_category
        if user_action is not None:
            self.user_action = user_action
        if provider_metadata is not None:
            self.provider_metadata = provider_metadata
        if backend_name is not None:
            self.backend_name = backend_name

    @property
    @override
    def implied_error_code(self) -> ErrorCode | None:
        """The code its category names, when its class declares it, ``None`` otherwise.

        A failure class takes its cause's code, or its fallback with no coded cause. An error built by hand with a
        category and no code, by a worker or by a plugin, reports its category's code instead
        (``InferenceErrorCategory.default_error_code``), when its class declares it and no Pipelex error along its
        cause chain carries a code of its own, so that its report's retry verdict agrees with the category's. Which
        of the chain's codes wins is ``PipelexError.resolve_error_code``'s one walk, so a cyclic chain cannot recurse.
        """
        if self.error_category is None:
            return None
        category_code = self.error_category.default_error_code
        if category_code is None or category_code not in declared_error_codes(type(self).error_code):
            return None
        return category_code

    def fill_model_and_provider(self, model_handle: str | None, *, backend_name: str | None) -> None:
        """Fill ``model_handle`` / ``backend_name`` from the worker, only when still unset.

        Inference-failure leaf errors raised deep inside a provider plugin
        (``LLMCompletionError``, ``ImgGenGenerationError``, ...) carry no model
        or provider of their own. Each worker family calls this at its
        public-method chokepoint — where model and provider are unambiguously
        known — so the eventual problem can attribute the failure.

        Never overwrites a value an inner error already set (e.g.
        ``LLMModelNotFoundError`` setting its own ``model_handle``), and skips
        the ``"unknown"`` placeholder a worker returns when it does not know
        its own provider/model (external plugins not overriding the getters).
        """
        if self.model_handle is None and model_handle is not None and model_handle != "unknown":
            self.model_handle = model_handle
        if self.backend_name is None and backend_name is not None and backend_name != "unknown":
            self.backend_name = backend_name

    @override
    def problem_params(self) -> dict[str, Any]:
        # The backend the failure was met on is the component an operator configures (`runtime.misconfigured`, operator-only).
        return {"component": self.backend_name} if self.backend_name is not None else {}

    @override
    def problem_facts(self) -> ProblemFacts:
        """The model and the provider this failure names, what the provider answered, and how long it asked to wait.

        Each fact is the nearest one set along the cause chain (``PipelexError.chain_facts``), so a wrapper that
        set a fact overrides its cause's, and one that did not leaves the cause's in place; the provider is merged
        member by member, so a wrapper naming the backend keeps the status its cause recorded. The provider's answer
        rides only the operator's diagnostics, its message capped, since it is the provider's text and may quote
        anything the request held.
        """
        provider: ProviderDiagnostics | None = None
        metadata = self.provider_metadata
        if metadata is not None:
            provider = ProviderDiagnostics(
                name=self.backend_name,
                status=metadata.status_code,
                code=metadata.provider_error_code,
                request_id=metadata.request_id,
                message=cap_problem_text(text=metadata.message) if metadata.message else None,
            )
        elif self.backend_name is not None:
            provider = ProviderDiagnostics(name=self.backend_name)
        return ProblemFacts(
            model=self.model_handle,
            provider=provider,
            retry_after=metadata.retry_after_seconds if metadata is not None else None,
        )


def find_inference_error_category_in_chain(exc: BaseException) -> InferenceErrorCategory | None:
    """Return the first ``InferenceErrorCategory`` found on the exception's ``__cause__`` chain.

    By the time a retry decision is made, the categorized ``CogtError`` a worker raised is
    usually buried: operators wrap it into a ``PipeRunError``, the ``PipeRouter`` into a
    ``PipeRouterError``, the pipeline runner into a ``PipelineExecutionError`` — none of
    which are ``CogtError`` subclasses. Walking ``__cause__`` recovers the category
    regardless of wrapper depth.

    The Temporal activity error boundary calls this to derive its retry decision
    (``non_retryable``) from the underlying failure's category. A ``CogtError`` carrying no
    category is skipped — the walk continues to the first one that actually classifies the failure.

    Walks via ``iter_cause_chain``, which owns the cyclic-``__cause__`` guard so a cycle
    terminates the walk instead of hanging the error path.
    """
    for node in iter_cause_chain(exc):
        if isinstance(node, CogtError) and node.error_category is not None:
            return node.error_category
    return None


class LLMConfigError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION


class CostRegistryError(CogtError):
    """An accounting invariant of the cost registry that did not hold."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class SdkTypeError(CogtError):
    """A worker handed an SDK client of the wrong type: wiring code of ours, not a file an operator edits."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelChoiceNotFoundError(CogtError):
    """Raised when a model reference names a handle, alias, preset or waterfall the model deck does not define,
    or a bare handle the deck serves only as another model type: by the deck check a pipe runs when it is
    built, and by the deck when a run resolves a reference. When a pipe is built, the pipe operator raises it
    again as a ``PipeOperatorModelChoiceError`` located on the pipe and the field, so a bundle naming an unknown
    model is an invalid validation verdict (error type ``unknown_model``), never a failure of the validator.

    Includes available options and migration hints in error message.

    The reference is the method's, so the fault is its author's: ``model.unknown`` for a reference the deck does not
    define, with the deck's close matches as its ``suggestions``, and ``model.capability_unsupported`` for a bare handle
    the deck serves only as another model type, which the deck chooses where it raises it. A bare handle a catalog of
    this deployment declares as the type the step needs, on a backend that is not enabled, names a model that exists:
    the deck chooses ``model.unavailable`` for it, with the reason ``not_served``, whose fix is the deployment's. A
    reference the deck itself names, as a default or an override, is the deployment's fault too: the deck re-raises its
    miss as a ``ModelDeckChoiceUnresolvedError``.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.MODEL_UNKNOWN,
        others=(CoreCode.MODEL_CAPABILITY_UNSUPPORTED, CoreCode.MODEL_UNAVAILABLE),
    )
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(
        self,
        message: str,
        model_type: ModelType,
        model_choice: str,
        reference_kind: ModelReferenceKind | None = None,
        available_options: list[str] | None = None,
        suggestions: list[str] | None = None,
        wrong_sigil_hints: list[str] | None = None,
        cross_collection_suggestions: list[str] | None = None,
    ):
        self.model_type = model_type
        self.model_choice = model_choice
        self.reference_kind = reference_kind
        self.available_options = available_options or []
        self.suggestions = suggestions or []
        self.wrong_sigil_hints = wrong_sigil_hints or []
        self.cross_collection_suggestions = cross_collection_suggestions or []

        full_message = message

        all_suggestions = self.suggestions + self.cross_collection_suggestions
        if all_suggestions:
            full_message += "\n\nDid you mean: " + ", ".join(all_suggestions)

        for hint in self.wrong_sigil_hints:
            full_message += f"\nNote: {hint}"

        if not all_suggestions and not self.wrong_sigil_hints and self.available_options:
            options_str = ", ".join(sorted(self.available_options)[:10])
            if len(self.available_options) > 10:
                options_str += f" ... and {len(self.available_options) - 10} more"
            full_message += f"\n\nAvailable {reference_kind or 'options'}: {options_str}"

        super().__init__(message=full_message)

    @override
    def problem_params(self) -> dict[str, Any]:
        # Each of the class's codes reads its own: `model.unknown` the close matches, an empty list when the deck has
        # none, `model.capability_unsupported` the use the step needs the model for, `model.unavailable` its reason.
        return {
            **super().problem_params(),
            "model": self.model_choice,
            "model_type": self.model_type,
            "suggestions": self.suggestions + self.cross_collection_suggestions,
            "capability": f"use as {self.model_type.indefinite_description}",
            "reason": ModelUnavailableReason.NOT_SERVED,
        }


class ModelDeckChoiceUnresolvedError(ModelChoiceNotFoundError):
    """A model choice the model deck names itself, a default or an override, that the deck does not resolve.

    The deck is the deployment's configuration, so the fault is the host's, never the caller's input, though the
    reference reaches the deck's lookup as a method's own does: a step that names no model runs on the deck's default
    or override, and a miss there is raised by the same lookup, as a ``ModelChoiceNotFoundError``, which this wraps.
    A bare handle is ``model.unavailable``, a model this deployment serves no backend for as the type the step needs,
    with the reason ``not_served``, whose other step lets the caller name a model the step can use; a preset, an alias
    or a waterfall the deck does not define is ``pipelex.config.invalid``. Its message names the deck's setting and the reference, for the
    operator, so it is not caller-facing.

    It is still a model choice the deck does not resolve, so a handler that skips an unresolvable choice, such as the
    load-time checks that leave a model to the run, skips the deck's own as it skips a method's.
    """

    error_code = ErrorCodeSet(default=PipelexErrorCode.CONFIG_INVALID, others=(CoreCode.MODEL_UNAVAILABLE,))
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, *, deck_setting: str, unresolved: ModelChoiceNotFoundError):
        self.deck_setting = deck_setting
        message = (
            f"The model deck's {deck_setting} names the model '{unresolved.model_choice}', which the deck does not resolve: {unresolved.message}"
        )
        # The lookup's message already carries its suggestions and options, so they are copied rather than appended again.
        super().__init__(
            message=message,
            model_type=unresolved.model_type,
            model_choice=unresolved.model_choice,
            reference_kind=unresolved.reference_kind,
        )
        self.available_options = unresolved.available_options
        self.suggestions = unresolved.suggestions
        self.wrong_sigil_hints = unresolved.wrong_sigil_hints
        self.cross_collection_suggestions = unresolved.cross_collection_suggestions
        if unresolved.reference_kind is None:
            return
        match unresolved.reference_kind:
            case ModelReferenceKind.HANDLE:
                self.with_error_code(CoreCode.MODEL_UNAVAILABLE)
            case ModelReferenceKind.PRESET | ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL:
                pass


class ModelDeckValidationError(CogtError):
    """The model deck as configured is invalid: its files do not validate, or a preset names a model it does not serve."""

    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelDeckPresetValidationError(ModelDeckValidationError):
    """A deck preset names a model this deployment does not serve, refused when the deck is validated at boot."""

    error_code = PipelexErrorCode.CONFIG_INVALID

    def __init__(
        self,
        message: str,
        model_type: ModelType,
        preset_id: str,
        model_handle: str | None,
        enabled_backends: set[str] | None = None,
    ):
        self.model_type = model_type
        self.preset_id = preset_id
        self.model_handle = model_handle
        self.enabled_backends = enabled_backends or set()
        super().__init__(message)


class ModelNotFoundError(CogtError):
    """A model reference that resolves to no model this deployment serves, when a run looks its model up.

    ``model.unavailable`` for a reference the deck itself names (a preset's model, an alias's target, a waterfall)
    on a backend that is not enabled, which is the operator's to fix; ``model.unknown`` for a reference only a
    method's inline model setting names, which the deck chooses where it raises it. The base of the render path's
    not-found classes too, which a provider's answer selects.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(default=CoreCode.MODEL_UNAVAILABLE, others=(CoreCode.MODEL_UNKNOWN,))
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(
        self,
        message: str,
        model_handle: str,
        error_category: InferenceErrorCategory | None = None,
        user_action: UserAction | None = None,
        provider_metadata: ProviderErrorMetadata | None = None,
    ):
        self.model_handle = model_handle
        super().__init__(
            message=message,
            error_category=error_category,
            user_action=user_action,
            provider_metadata=provider_metadata,
        )


class ModelWaterfallError(ModelNotFoundError):
    """A waterfall none of whose models this deployment serves."""

    error_code = CoreCode.MODEL_UNAVAILABLE

    def __init__(self, message: str, model_handle: str, fallback_list: list[str]):
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message=message, model_handle=model_handle)


class LLMHandleNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str, enabled_backends: set[str] | None = None):
        self.preset_id = preset_id
        self.model_handle = model_handle
        self.enabled_backends = enabled_backends or set()
        super().__init__(message)


class ImgGenHandleNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class ExtractHandleNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class SearchHandleNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class DocGenHandleNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class JudgmentHandleNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class GeneratedImageError(CogtError):
    """An image a provider returned that cannot be converted."""

    error_code = CoreCode.PROVIDER_RESPONSE_INVALID


class LLMModelNotFoundError(ModelNotFoundError):
    """A provider that does not know the model the deck resolved, as its answer said: the deployment's to fix."""

    error_code = CoreCode.MODEL_UNAVAILABLE


class LLMCapabilityError(CogtError):
    """A setting or a request the model refuses: the method's choice of model, or of a setting it cannot take.

    ``model.capability_unsupported``, or ``model.context_exceeded`` where the run's inputs carry more images than the
    model takes, which the raise site chooses.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.MODEL_CAPABILITY_UNSUPPORTED, others=(CoreCode.MODEL_CONTEXT_EXCEEDED,)
    )
    error_category = InferenceErrorCategory.CONFIGURATION


class LLMSettingRefusedError(LLMCapabilityError):
    """A worker's refusal of an LLM setting, worded for the caller who wrote the setting.

    Its message names the model by its deck handle, never by the SDK, backend or provider model id a
    worker's own refusal carries, so a validation verdict can show it to whoever wrote the setting.
    """

    error_code = CoreCode.MODEL_CAPABILITY_UNSUPPORTED


class LLMCompletionError(CogtError):
    """A text completion that failed: a provider's failure the classification read, or an answer that cannot be used.

    The Render step constructs it with the code its classification picked, and a worker raising it directly chooses
    one: ``provider.response_invalid`` for an answer with no usable text, ``runtime.unexpected`` for a structured
    generation that failed with no cause to read. A worker wrapping a coded error in it takes that error's code. A
    text or a structured output cut short or refused is one of its subclasses, which carries its own code.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = _inference_failure_declaration(fallback=CoreCode.RUNTIME_UNEXPECTED)


class CompletionTruncationLimit(StrEnum):
    """The limit a truncated text completion hit, which decides what can lift it."""

    # The output limit the request sent: a higher max_tokens, or a shorter input, leaves room for the text
    MAX_TOKENS = "max_tokens"
    # The model's context window, which the input and the output filled together: a higher max_tokens cannot help
    CONTEXT_WINDOW = "context_window"


class CompletionOutputKind(StrEnum):
    """What a completion was writing when it stopped, which its error names: a text, or a structured output."""

    TEXT = "text"
    STRUCTURED = "structured"

    @property
    def desc(self) -> str:
        """The words an error names this output by."""
        match self:
            case CompletionOutputKind.TEXT:
                return "text"
            case CompletionOutputKind.STRUCTURED:
                return "structured output"


class MaxTokensCeiling(NamedTuple):
    """A max_tokens a worker sent below the one it was given, to fit its call's timeout, so a higher one is lowered too."""

    # The max_tokens the call was given: the pipe's setting, or the model's default
    requested_max_tokens: int
    # The call's timeout, which the max_tokens sent fits
    timeout_seconds: int


class LLMCompletionTruncatedError(LLMCompletionError):
    """A completion stopped before the model finished it: it hit its output limit, or its context window.

    A worker raises it when its provider's stop signal says the text was cut (see
    `pipelex.cogt.llm.completion_stop`), instead of handing back the partial or empty text as a result, and when
    instructor reports a structured output cut at its output limit with its `IncompleteOutputException`; its
    `output_kind` says which of the two was cut. It is not retryable: the same request stops at the same limit.
    Its code follows the limit hit: ``model.output_truncated`` at the output limit, the method's token cap, and
    ``model.context_exceeded`` at the context window, which the inputs filled. Which remedy applies depends on the
    limit hit, carried as `truncation_limit`: at the output limit, a higher `max_tokens` on the pipe or a shorter
    input, or, when the request sent no `max_tokens` and the provider's default cut the text, a `max_tokens` set on
    the pipe up to the model's limit, a lower reasoning effort or a shorter input, or, when the worker sent a
    `max_tokens` lowered to fit its call's timeout (`max_tokens_ceiling`), a lower reasoning effort or a smaller
    output, since a higher `max_tokens` is lowered the same way; at the context window, which the input and the
    output filled together, a shorter input, less thinking or a model with a larger window, never a higher
    `max_tokens`. The message names only the pipe, the model's deck handle, the provider's stop value and the token
    counts, never the partial text or the provider's body, so it is kept verbatim for the caller.
    """

    error_code = ErrorCodeSet(default=CoreCode.MODEL_OUTPUT_TRUNCATED, others=(CoreCode.MODEL_CONTEXT_EXCEEDED,))
    error_category = InferenceErrorCategory.CONTENT

    def __init__(
        self,
        *,
        model_handle: str,
        stop_reason: str,
        truncation_limit: CompletionTruncationLimit,
        output_kind: CompletionOutputKind,
        pipe_code: str | None = None,
        max_tokens: int | None = None,
        output_tokens: int | None = None,
        max_tokens_ceiling: MaxTokensCeiling | None = None,
    ):
        """Build the error, its message and its next step from the facts of the cut.

        Args:
            model_handle: The model's deck handle.
            stop_reason: The provider's stop value.
            truncation_limit: The limit the completion hit.
            output_kind: Whether a text or a structured output was cut.
            pipe_code: The pipe whose output it was, None when the job names none.
            max_tokens: The output limit the request sent, None when it sent none.
            output_tokens: The output tokens the provider counted, None when it gave no count.
            max_tokens_ceiling: Set when the worker sent a lower max_tokens than it was given, to fit its call's
                timeout: a higher max_tokens is then lowered the same way, so the next step names what else lifts the
                limit. Read at the output limit only.
        """
        output_desc = output_kind.desc
        subject = f"the {output_desc} of pipe '{pipe_code}'" if pipe_code else f"its {output_desc}"
        details = [f"stop reason '{stop_reason}'"]
        if output_tokens is not None:
            details.append(f"{output_tokens} output tokens used")
        if max_tokens is not None:
            details.append(f"max_tokens set to {max_tokens}")
        what_happened: str
        next_step: str
        # A fact the next step rests on, said between the cut and the next step
        lowered_fact: str | None = None
        match truncation_limit:
            case CompletionTruncationLimit.MAX_TOKENS:
                what_happened = "was cut off"
                if max_tokens is not None and max_tokens_ceiling is not None:
                    # The worker held the limit below the one it was given, so a higher one would be held the same way
                    lowered_fact = (
                        f"Its max_tokens was lowered from {max_tokens_ceiling.requested_max_tokens} to {max_tokens} "
                        f"to fit the call's {max_tokens_ceiling.timeout_seconds}-second timeout."
                    )
                    next_step = (
                        "Lower the pipe's reasoning effort, or ask it for a smaller output, since a higher max_tokens is lowered the same way."
                        if pipe_code
                        else "Lower the reasoning effort, or ask for a smaller output, since a higher max_tokens is lowered the same way."
                    )
                elif max_tokens is not None:
                    next_step = "Raise the pipe's max_tokens, or shorten its input." if pipe_code else "Raise max_tokens, or shorten the input."
                else:
                    # The request left the limit to the provider's default, so there is no max_tokens of the pipe's to raise
                    details.append("no max_tokens sent")
                    next_step = (
                        "Set the pipe's max_tokens up to the model's limit, lower its reasoning effort, or shorten its input."
                        if pipe_code
                        else "Set max_tokens up to the model's limit, lower the reasoning effort, or shorten the input."
                    )
            case CompletionTruncationLimit.CONTEXT_WINDOW:
                what_happened = "filled its context window"
                next_step = (
                    "Shorten the pipe's input, lower its reasoning effort, or choose a model with a larger context window."
                    if pipe_code
                    else "Shorten the input, lower the reasoning effort, or choose a model with a larger context window."
                )
        sentences = [
            f"The model '{model_handle}' {what_happened} before it finished {subject} ({', '.join(details)}), so the {output_desc} is incomplete."
        ]
        if lowered_fact is not None:
            sentences.append(lowered_fact)
        sentences.append(next_step)
        super().__init__(" ".join(sentences), user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail=next_step))
        match truncation_limit:
            case CompletionTruncationLimit.MAX_TOKENS:
                self.with_error_code(CoreCode.MODEL_OUTPUT_TRUNCATED)
            case CompletionTruncationLimit.CONTEXT_WINDOW:
                self.with_error_code(CoreCode.MODEL_CONTEXT_EXCEEDED)
        self.model_handle = model_handle
        self.stop_reason = stop_reason
        self.truncation_limit = truncation_limit
        self.output_kind = output_kind
        self.pipe_code = pipe_code
        self.max_tokens = max_tokens
        self.output_tokens = output_tokens
        self.max_tokens_ceiling = max_tokens_ceiling

    @override
    def problem_params(self) -> dict[str, Any]:
        # At the context window the bound passed is known, and the counts are not: the stop signal carries neither the
        # prompt's size nor the window's.
        return {
            **super().problem_params(),
            "pipe": self.pipe_code,
            "model": self.model_handle,
            "max_tokens": self.max_tokens,
            "output_tokens": self.output_tokens,
            "limit": ModelContextExceededLimit.CONTEXT_WINDOW,
        }


class LLMCompletionRefusedError(LLMCompletionError):
    """A text completion the model declined to write, or that a provider's safety filter stopped.

    A worker raises it when its provider's stop signal says the model refused or a filter cut the text (see
    `pipelex.cogt.llm.completion_stop`), instead of handing back the partial or empty text as a result. It
    is ``model.content_refused``, and not retryable: what a model declines or a filter blocks is
    the prompt and the input it was given, so the remedy is to revise them. The message names only the pipe,
    the model's deck handle and the provider's stop value, never the partial text or the provider's body, so
    it is kept verbatim for the caller.
    """

    error_code = CoreCode.MODEL_CONTENT_REFUSED
    error_category = InferenceErrorCategory.CONTENT

    def __init__(self, *, model_handle: str, stop_reason: str, pipe_code: str | None = None):
        subject = f"the text of pipe '{pipe_code}'" if pipe_code else "its text"
        next_step = "Revise the pipe's prompt or its input." if pipe_code else "Revise the prompt or the input."
        message = (
            f"The model '{model_handle}' declined to finish {subject}, or a content filter stopped it (stop reason '{stop_reason}'), "
            f"so the text cannot be used. {next_step}"
        )
        super().__init__(message, user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail=next_step))
        self.model_handle = model_handle
        self.stop_reason = stop_reason
        self.pipe_code = pipe_code


class LLMPromptParameterError(CogtError):
    """A rendered prompt that holds no text, usually because an input it renders was empty."""

    error_code = CoreCode.PIPE_PROMPT_EMPTY
    error_category = InferenceErrorCategory.CONTENT


class LLMSettingValueError(PipelexError, ValueError):
    """An LLM setting whose values contradict each other, refused by its validator.

    A ``ValueError`` as well, so that pydantic wraps it into the validation error of the model being built: the
    method's bundle, or the model deck, whose boundary then reads the fault as its own.
    """

    error_code = CoreCode.METHOD_MODEL_SETTING_INVALID


class PromptImageFactoryError(CogtError):
    """A prompt image with none of a URI, base64 data or bytes: an invariant of ours."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
    error_category = InferenceErrorCategory.CONTENT


class PromptImageFormatError(CogtError):
    """A prompt image of a known format the model does not read."""

    error_code = CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
    error_category = InferenceErrorCategory.CONTENT


class PromptDocumentFactoryError(CogtError):
    """A prompt document with none of a URI, base64 data or bytes: an invariant of ours."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
    error_category = InferenceErrorCategory.CONTENT


class PromptDocumentFormatError(CogtError):
    """A prompt document's known format is one the LLM does not read.

    The input's fault, ``input.file_type_unsupported``: the model is fixed by the method and reads the
    formats it declares, while the file changes from run to run. A model that reads no documents at
    all is the author's choice of model, which stays an `LLMCapabilityError`.
    """

    error_code = CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
    error_category = InferenceErrorCategory.CONTENT


class ImgGenModelNotFoundError(ModelNotFoundError):
    """An image provider that does not know the model the deck resolved, as its answer said."""

    error_code = CoreCode.MODEL_UNAVAILABLE


class ImgGenPromptError(CogtError):
    """An image generation prompt that holds no text."""

    error_code = CoreCode.PIPE_PROMPT_EMPTY
    error_category = InferenceErrorCategory.CONTENT


class ImgGenParameterError(CogtError):
    """An image generation setting that cannot reach the model.

    ``model.capability_unsupported`` for a setting the method asks of a model that does not take it (an aspect ratio,
    a size, a background, a format); ``pipelex.config.invalid`` for a model spec with no image rules, or rules the
    worker cannot apply; ``runtime.unexpected`` for a prepared file of a type the worker never receives. The raise
    site chooses.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.MODEL_CAPABILITY_UNSUPPORTED,
        others=(PipelexErrorCode.CONFIG_INVALID, CoreCode.RUNTIME_UNEXPECTED),
    )
    error_category = InferenceErrorCategory.CONTENT


class ImgGenGenerationError(CogtError):
    """An image generation that failed: a provider's failure the classification read, or an answer that cannot be used.

    The Render step constructs it with the code its classification picked, and a worker raising it directly chooses
    one: ``provider.response_invalid`` for an answer with no usable image, ``model.content_refused`` for an answer
    whose finish or block reason says the provider refused the request on policy grounds, ``provider.outcome_unknown``
    for a call that failed after it was sent, which may have generated, and billed, the image. With no code chosen and
    no coded cause, it is ``provider.outcome_unknown``, since an image generation is a call no one may blindly repeat.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = _inference_failure_declaration(fallback=CoreCode.PROVIDER_OUTCOME_UNKNOWN)


class ImgGenOutputTruncatedError(ImgGenGenerationError):
    """An image generation the model's output token limit cut before it produced the image.

    A worker raises it when its provider's answer, a success all the same, says its output stopped at that limit and
    holds no image (a Gemini candidate whose finish reason is `MAX_TOKENS`), instead of reading it as an empty answer.
    It is ``model.output_truncated``, and not retryable: the same request stops at the same limit. The worker sends no
    output limit of its own, so the limit is the model's, which the image and the model's thinking share, and the
    advice its `user_action` gives is a simpler prompt or another model, never a setting of the pipe's. The message,
    for the operator, names only the model's deck handle and the provider's stop value.
    """

    error_code = CoreCode.MODEL_OUTPUT_TRUNCATED
    error_category = InferenceErrorCategory.CONTENT

    def __init__(self, *, model_handle: str, stop_reason: str):
        next_step = "Simplify the image prompt, or choose another image model."
        message = (
            f"The model '{model_handle}' reached its output token limit before it generated the image (finish reason '{stop_reason}'). {next_step}"
        )
        super().__init__(message, user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail=next_step))
        self.model_handle = model_handle
        self.stop_reason = stop_reason


class ExtractCapabilityError(CogtError):
    """An extraction the model cannot perform, such as captioning images it does not read."""

    error_code = CoreCode.MODEL_CAPABILITY_UNSUPPORTED
    error_category = InferenceErrorCategory.CONFIGURATION


class ExtractInputFormatError(CogtError):
    """The file given to an extraction has a known format that the extract model does not read.

    The input's fault, ``input.file_type_unsupported``: the model is fixed by the method and reads the
    formats it declares, while the file changes from run to run, and the person who can act is the
    one supplying it.
    """

    error_code = CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
    error_category = InferenceErrorCategory.CONTENT


class ExtractJobFailureError(CogtError):
    """An extraction that failed at its provider, raised by the Render step with the code its classification picked."""

    error_code = _inference_failure_declaration(fallback=CoreCode.RUNTIME_UNEXPECTED)


class ExtractModelNotFoundError(ModelNotFoundError):
    """An extract provider that does not know the model the deck resolved, as its answer said."""

    error_code = CoreCode.MODEL_UNAVAILABLE


class SearchJobFailureError(CogtError):
    """A search that failed at its provider, raised by the Render step with the code its classification picked."""

    error_code = _inference_failure_declaration(fallback=CoreCode.RUNTIME_UNEXPECTED)


class SearchModelNotFoundError(ModelNotFoundError):
    """A search provider that does not know the model the deck resolved, as its answer said."""

    error_code = CoreCode.MODEL_UNAVAILABLE


class JudgmentJobFailureError(CogtError):
    """A judgment that failed at its provider, raised by the Render step with the code its classification picked."""

    error_code = _inference_failure_declaration(fallback=CoreCode.RUNTIME_UNEXPECTED)


class JudgmentAnswerMismatchError(CogtError):
    """A judgment worker answered questions nobody asked, or answered one in the wrong shape: its output does not match its schema."""

    error_code = CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH


class JudgmentCapabilityError(CogtError):
    """A judgment job carries files its model does not read: images to a model without vision, documents to one that reads none.

    The author's choice of model, ``model.capability_unsupported``, as `LLMCapabilityError` is for an LLM; more
    images than the model takes is ``model.context_exceeded``; a model spec claiming files its backend cannot take
    is ``pipelex.config.invalid``. The raise site chooses. A document of a format the model does not read is the
    caller's file, which stays a `PromptDocumentFormatError`.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.MODEL_CAPABILITY_UNSUPPORTED,
        others=(CoreCode.MODEL_CONTEXT_EXCEEDED, PipelexErrorCode.CONFIG_INVALID),
    )
    error_category = InferenceErrorCategory.CONFIGURATION


class JudgmentModelNotFoundError(ModelNotFoundError):
    """A judgment provider that does not know the model the deck resolved, as its answer said."""

    error_code = CoreCode.MODEL_UNAVAILABLE


class JudgmentRefusedError(CogtError):
    """The judging model declined to answer a step's question, whose output cannot hold nothing.

    A refusal is a worker's outcome, never its error: this is the operator's policy for a question
    whose output cannot hold nothing, the one question of a single-question step or a question of
    several whose output field is required or defaulted. It is a content error, in the input domain,
    because what a model declines to judge is the question asked over the evidence given, and the
    remedy is the author's or the caller's: a reworded question, different evidence, or, for a question
    of several, an optional field with no default, which holds nothing on a refusal. The message names only the step, the
    model's deck handle and the question's name, which the author wrote, so it is kept verbatim for the
    caller.
    """

    error_code = CoreCode.MODEL_CONTENT_REFUSED
    error_category = InferenceErrorCategory.CONTENT

    def __init__(self, *, pipe_code: str | None, model_handle: str, question_name: str | None = None):
        step = f"PipeJudge '{pipe_code}'" if pipe_code else "This judgment"
        message: str
        user_action_detail: str
        if question_name is None:
            message = (
                f"{step}: the judgment model '{model_handle}' declined to answer its question. "
                "Try to reword the question so it can be answered from the evidence, or give the step different evidence."
            )
            user_action_detail = "Reword the question, or give the step different evidence."
        else:
            message = (
                f"{step}: the judgment model '{model_handle}' declined to answer the question '{question_name}', and its output field "
                "cannot hold nothing, being required or given a default. Try to reword the question so it can be answered from the "
                "evidence, give the step different evidence, or make its output field optional with no default, so that it holds "
                "nothing on a refusal."
            )
            user_action_detail = (
                "Reword the question, give the step different evidence, or make the question's output field optional with no default."
            )
        super().__init__(
            message,
            user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail=user_action_detail),
        )
        self.pipe_code = pipe_code
        self.model_handle = model_handle
        self.question_name = question_name


class JudgmentModelMissingError(PipelexError):
    """A judgment has no model to run on: the step names none, and the model deck names no default.

    The deck serves no judgment model out of the box, since a judgment backend is one the user brings,
    so a step that names no model is refused when its method loads, before a run spends anything, and
    by the kernel's resolver for a programmatic caller. The message names only the step and the two
    remedies, so it is kept verbatim for the caller.
    """

    error_code = CoreCode.MODEL_UNSPECIFIED

    def __init__(self, *, pipe_code: str | None = None):
        self.pipe_code = pipe_code
        step = f"PipeJudge '{pipe_code}'" if pipe_code else "This judgment"
        message = (
            f"{step} has no judgment model: it names none, and the model deck names no default for judgments. "
            "Name the model in the step's `model` field, or set a `choice_default` under `[judgment]` in the model deck."
        )
        super().__init__(message)

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"pipe": self.pipe_code, "model_type": ModelType.JUDGMENT}


class RoutingProfileLibraryNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID


class RoutingProfileBlueprintValueError(CogtError, ValueError):
    """A routing profile's value its validator refuses; a ``ValueError`` as well, so that pydantic wraps it."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class RoutingProfileLibraryError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID


class InferenceModelSpecError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID


class InferenceBackendLibraryNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID


class InferenceBackendLibraryValidationError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID


class InferenceBackendCredentialsErrorType(StrEnum):
    VAR_NOT_FOUND = "var_not_found"
    UNKNOWN_VAR_PREFIX = "unknown_var_prefix"
    VAR_FALLBACK_PATTERN = "var_fallback_pattern"
    # The process booted without inference, which loads every backend but resolves no credential,
    # and was then asked for a backend to call.
    NOT_RESOLVED_ON_KEYLESS_BOOT = "not_resolved_on_keyless_boot"


class InferenceBackendCredentialsError(CogtError):
    """A credential a backend needs that this process cannot resolve, coded by why.

    ``pipelex.config.credential_missing`` for a variable or secret this process does not hold, or a fallback pattern
    none of whose candidates resolves; ``pipelex.config.invalid`` for a placeholder whose prefix no secrets provider
    reads, a malformed file rather than a missing key; ``runtime.misconfigured`` for a process booted without
    inference that was asked to call a backend, which is the deployment's wiring.
    """

    error_code = ErrorCodeSet(
        default=PipelexErrorCode.CONFIG_CREDENTIAL_MISSING,
        others=(PipelexErrorCode.CONFIG_INVALID, CoreCode.RUNTIME_MISCONFIGURED),
    )
    error_category = InferenceErrorCategory.CONFIGURATION
    user_action = UserAction(
        kind=UserActionKind.CHECK_CREDENTIALS,
        detail="Check that the required API key environment variable is set",
    )

    def __init__(
        self,
        credentials_error_type: InferenceBackendCredentialsErrorType,
        backend_name: str,
        message: str,
        key_name: str,
        user_action: UserAction | None = None,
    ):
        """A credential a backend needs that this process does not hold.

        Args:
            credentials_error_type: Why the credential is missing.
            backend_name: The backend whose credential it is.
            message: The error's message.
            key_name: The variable the credential is read from, or the field when no variable names it.
            user_action: This error's own next step, when the class's ("set the variable") is not it.
        """
        self.credentials_error_type = credentials_error_type
        self.backend_name = backend_name
        self.key_name = key_name
        if user_action is not None:
            self.user_action = user_action
        super().__init__(message)
        match credentials_error_type:
            case InferenceBackendCredentialsErrorType.VAR_NOT_FOUND | InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN:
                self.with_error_code(PipelexErrorCode.CONFIG_CREDENTIAL_MISSING)
            case InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX:
                self.with_error_code(PipelexErrorCode.CONFIG_INVALID)
            case InferenceBackendCredentialsErrorType.NOT_RESOLVED_ON_KEYLESS_BOOT:
                self.with_error_code(CoreCode.RUNTIME_MISCONFIGURED)

    @override
    def problem_params(self) -> dict[str, Any]:
        # Operator-only parameters of its codes: they reach the operator's step and diagnostics alone.
        return {"variable": self.key_name, "backend": self.backend_name, "component": self.backend_name}


class InferenceBackendLibraryError(CogtError):
    """A backend the library cannot load.

    ``backend_name`` is the backend the error is about, stamped by the loader so a caller can charge
    the failure to that backend rather than to one whose name merely appears in the message's prose.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION


class RoutingProfileDisabledBackendError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelManagerError(CogtError):
    """A route to a backend that is not loaded, or an exact route to a backend that declares no such model."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class PluginModelDeclarationError(CogtError):
    """A model a plugin declares, or a model deck default it sets, cannot be merged into this installation's inference configuration.

    The model manager validates the plugins' declarations when it merges them at boot, since a plugin's ``register``
    only stores them: a model whose name the installation's ``internal.toml`` already declares, a table that is not a
    valid model spec, or a default for a format and source no step composes. The message names the plugin, and the
    file when one is involved.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, *, plugin: str):
        self.plugin = plugin
        super().__init__(message)


class ModelListingUnsupportedError(CogtError):
    """A registered lister cannot enumerate models for an SDK variant at runtime.

    A *soft* control signal for the ``list-models`` loop: it is caught and the SDK
    is reported as unsupported-for-remote-listing rather than failing the command.
    Same outcome as a registry miss (no lister registered for the SDK at all). A
    lister closure raises it when its client variant cannot list (e.g. a
    bedrock-backed Anthropic client), translating any vendor-specific
    "unsupported" exception so core names no integration.
    """

    error_code = CoreCode.RUNTIME_UNSUPPORTED

    def __init__(self, *, sdk: str) -> None:
        self.sdk = sdk
        super().__init__(f"The '{sdk}' SDK client does not support remote model listing.")


class ModelDeckNotFoundError(CogtError):
    error_code = PipelexErrorCode.CONFIG_INVALID
