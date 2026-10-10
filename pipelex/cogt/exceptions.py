from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, iter_cause_chain
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_type import ModelType
    from pipelex.cogt.models.model_reference import ModelReferenceKind


class InferenceErrorCategory(StrEnum):
    """Classifies inference errors for retry decisions and error reporting."""

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
    def error_domain(self) -> ErrorDomain | None:
        """The :class:`~pipelex.base_exceptions.ErrorDomain` this category implies — who can fix it.

        The category a worker assigns is already the authoritative statement of *whose fault*
        an inference failure is, so :meth:`CogtError.to_error_report` derives the domain from it
        rather than making every leaf class in the family declare the same fact twice.

        ``CONTENT`` is the one mapping that changes an HTTP answer: a content-policy refusal, a
        malformed prompt image, a bad prompt parameter are all properties of material the caller
        submitted, so they belong in ``INPUT`` and answer 422 rather than 500.

        ``UNKNOWN`` deliberately maps to ``None``. It means classification itself failed, and
        ``RUNTIME`` would be a claim this code cannot support; an absent domain already renders
        500, so the honest answer costs nothing.

        ``CAPACITY -> RUNTIME`` does not disturb the provider-429 passthrough:
        :attr:`~pipelex.base_exceptions.ErrorReport.http_status` checks
        ``provider_metadata.status_code`` before it consults the domain.
        """
        match self:
            case InferenceErrorCategory.CONTENT:
                return ErrorDomain.INPUT
            case InferenceErrorCategory.CONFIGURATION:
                return ErrorDomain.CONFIG
            case InferenceErrorCategory.TRANSIENT | InferenceErrorCategory.CAPACITY | InferenceErrorCategory.AMBIGUOUS:
                return ErrorDomain.RUNTIME
            case InferenceErrorCategory.UNKNOWN:
                return None


class CogtError(PipelexError):
    error_category: InferenceErrorCategory | None = None
    user_action: UserAction | None = None
    provider_metadata: ProviderErrorMetadata | None = None
    model_handle: str | None = None
    backend_name: str | None = None
    _declared_title = "AI inference failed"

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

    def fill_model_and_provider(self, model_handle: str | None, *, backend_name: str | None) -> None:
        """Fill ``model_handle`` / ``backend_name`` from the worker, only when still unset.

        Inference-failure leaf errors raised deep inside a provider plugin
        (``LLMCompletionError``, ``ImgGenGenerationError``, ...) carry no model
        or provider of their own. Each worker family calls this at its
        public-method chokepoint — where model and provider are unambiguously
        known — so the eventual ``ErrorReport`` can attribute the failure.

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
    def to_error_report(self) -> ErrorReport:
        # Start from the base report (which already runs cause-chain enrichment
        # over the shared classification fields) and layer the CogtError-specific
        # fields on top with the same wrapper-wins-when-set semantics: a value
        # explicitly set on this CogtError overrides whatever the cause surfaced,
        # otherwise the cause-derived value carried by ``base_report`` stays.
        # Footgun: ``provider_metadata`` uses whole-object OR, and a Pydantic
        # model instance is always truthy — a wrapper that attached
        # attribution-only metadata (no ``status_code`` / ``retry_after_seconds``)
        # discards the cause's actionable hints. Pinned by
        # ``tests/unit/pipelex/cogt/test_cogt_provider_metadata_wrapper_wins.py``.
        base_report = super().to_error_report()
        own_retryable = self.error_category.is_retryable if self.error_category is not None else None
        # ``error_domain`` is derived from this error's own category rather than declared per leaf
        # class, so the two fields can never contradict each other on the wire. Precedence mirrors
        # every other field here — a class-level ``error_domain`` set explicitly on the leaf wins,
        # then the derivation, then whatever ``base_report`` already inherited from the cause chain
        # (which for a ``CogtError`` cause is that cause's own derivation). Deriving from
        # ``self.error_category`` and not from ``base_report.error_category`` is deliberate: the
        # report field is typed ``str``, and the same wrapper-wins precedence on both fields makes
        # the two agree anyway — an inherited category rides in with the domain it derived.
        own_domain = self.error_category.error_domain if self.error_category is not None else None
        return base_report.model_copy(
            update={
                "error_category": self.error_category or base_report.error_category,
                "error_domain": self.error_domain or own_domain or base_report.error_domain,
                "retryable": own_retryable if own_retryable is not None else base_report.retryable,
                "model": self.model_handle or base_report.model,
                "provider": self.backend_name or base_report.provider,
                "provider_metadata": self.provider_metadata or base_report.provider_metadata,
            }
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
    error_category = InferenceErrorCategory.CONFIGURATION


class ImageContentError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class CostRegistryError(CogtError):
    pass


class ReportingManagerError(CogtError):
    pass


class SdkTypeError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelChoiceNotFoundError(CogtError):
    """Raised when a model reference names a handle, alias, preset or waterfall the model deck does not define,
    or a bare handle the deck serves only as another model type: by the deck check a pipe runs when it is
    built, and by the deck when a run resolves a reference. When a pipe is built, the pipe operator raises it
    again as a ``PipeOperatorModelChoiceError`` located on the pipe and the field, so a bundle naming an unknown
    model is an invalid validation verdict (error type ``unknown_model``), never a failure of the validator.

    Includes available options and migration hints in error message.
    """

    error_category = InferenceErrorCategory.CONFIGURATION
    # Declared explicitly, against the grain of the CONFIGURATION category's ``CONFIG`` derivation,
    # because the two fields are answering different questions here. The *category* is right: from
    # the provider call's point of view the setup is wrong and no retry will help. But this class
    # exists to report a mistyped model reference in material the caller authored — its message
    # carries "Did you mean:" suggestions and lists the available options — so the caller is who
    # fixes it, on the hosted API (a submitted method naming an unknown model) as much as in a
    # local ``.mthds`` file. An operator-side deck fault surfaces as
    # ``ModelDeckPresetValidatonError`` instead, which keeps the derived ``CONFIG``.
    error_domain = ErrorDomain.INPUT
    # The message is caller-facing copy for the same reason: it names only the caller's own model
    # reference and the deck's public handles (suggestions, sigil hints, available options). Without
    # the flag, STRICT disclosure on the hosted API replaced it with the generic placeholder, so a
    # method naming an unknown model failed its dry run with no hint of which model or what to use.
    _authors_caller_facing_message = True

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


class LLMSettingsValidationError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ImgGenSettingsValidationError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelDeckValidatonError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelDeckPresetValidatonError(ModelDeckValidatonError):
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
    def __init__(self, message: str, model_handle: str, fallback_list: list[str]):
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message=message, model_handle=model_handle)


class LLMHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str, enabled_backends: set[str] | None = None):
        self.preset_id = preset_id
        self.model_handle = model_handle
        self.enabled_backends = enabled_backends or set()
        super().__init__(message)


class ImgGenHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class ExtractHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class SearchHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class DocGenHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class JudgmentHandleNotFoundError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, message: str, preset_id: str, model_handle: str):
        self.preset_id = preset_id
        self.model_handle = model_handle
        super().__init__(message)


class ExtractOutputError(CogtError):
    pass


class GeneratedImageError(CogtError):
    pass


class LLMModelNotFoundError(ModelNotFoundError):
    pass


class LLMCapabilityError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class LLMSettingRefusedError(LLMCapabilityError):
    """A worker's refusal of an LLM setting, worded for the caller who wrote the setting.

    Its message names the model by its deck handle, never by the SDK, backend or provider model id a
    worker's own refusal carries, so a validation verdict can show it under strict disclosure.
    """

    _authors_caller_facing_message = True


class LLMCompletionError(CogtError):
    pass


class LLMAssignmentError(CogtError):
    pass


class LLMPromptSpecError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class LLMPromptParameterError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptImageFactoryError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptImageFormatError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptDocumentFactoryError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class PromptDocumentFormatError(CogtError):
    """A prompt document's known format is one the LLM does not read.

    A content error, and so in the input domain: the model is fixed by the method and reads the
    formats it declares, while the file changes from run to run. A model that reads no documents at
    all is the author's choice of model, which stays an `LLMCapabilityError`.
    """

    error_category = InferenceErrorCategory.CONTENT


class ImgGenModelNotFoundError(ModelNotFoundError):
    pass


class ImgGenPromptError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class ImgGenParameterError(CogtError):
    error_category = InferenceErrorCategory.CONTENT


class ImgGenGenerationError(CogtError):
    pass


class ImgGenGeneratedTypeError(ImgGenGenerationError):
    pass


class ExtractCapabilityError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ExtractInputFormatError(CogtError):
    """The file given to an extraction has a known format that the extract model does not read.

    A content error, and so in the input domain: the model is fixed by the method and reads the
    formats it declares, while the file changes from run to run, and the person who can act is the
    one supplying it.
    """

    error_category = InferenceErrorCategory.CONTENT


class ExtractJobFailureError(CogtError):
    pass


class ExtractModelNotFoundError(ModelNotFoundError):
    pass


class SearchJobFailureError(CogtError):
    pass


class SearchModelNotFoundError(ModelNotFoundError):
    pass


class JudgmentJobFailureError(CogtError):
    pass


class JudgmentAnswerMismatchError(CogtError):
    """A judgment worker answered questions nobody asked, or answered one in the wrong shape."""


class JudgmentCapabilityError(CogtError):
    """A judgment job carries files its model does not read: images to a model without vision, documents to one that reads none.

    The author's choice of model, and so a configuration error, as `LLMCapabilityError` is for an LLM.
    A document of a format the model does not read is the caller's file, which stays a
    `PromptDocumentFormatError`.
    """

    error_category = InferenceErrorCategory.CONFIGURATION


class JudgmentModelNotFoundError(ModelNotFoundError):
    pass


class JudgmentRefusedError(CogtError):
    """The judging model declined to answer a step's question, whose verdict has nowhere to be left absent.

    A refusal is a worker's outcome, never its error: this is the operator's policy for a question
    whose verdict has nowhere to be left absent, the one question of a single-question step or a
    question of several whose output field is required or defaulted. It is a content error, in the input domain,
    because what a model declines to judge is the question asked over the evidence given, and the
    remedy is the author's or the caller's: a reworded question, different evidence, or, for a question
    of several, an optional field with no default, which a refusal may leave absent. The message names only the step, the
    model's deck handle and the question's name, which the author wrote, so it is kept verbatim for the
    caller.
    """

    error_category = InferenceErrorCategory.CONTENT
    _authors_caller_facing_message = True

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
                "cannot be left absent, being required or given a default. Try to reword the question so it can be answered from the "
                "evidence, give the step different evidence, or make its output field optional with no default, so that a refusal "
                "leaves the field absent."
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

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(self, *, pipe_code: str | None = None):
        self.pipe_code = pipe_code
        step = f"PipeJudge '{pipe_code}'" if pipe_code else "This judgment"
        message = (
            f"{step} has no judgment model: it names none, and the model deck names no default for judgments. "
            "Name the model in the step's `model` field, or set a `choice_default` under `[judgment]` in the model deck."
        )
        super().__init__(message)


class RoutingProfileLibraryNotFoundError(CogtError):
    pass


class RoutingProfileBlueprintValueError(CogtError, ValueError):
    pass


class RoutingProfileLibraryError(CogtError):
    pass


class InferenceModelSpecError(CogtError):
    pass


class InferenceBackendLibraryNotFoundError(CogtError):
    pass


class InferenceBackendLibraryValidationError(CogtError):
    pass


class InferenceBackendCredentialsErrorType(StrEnum):
    VAR_NOT_FOUND = "var_not_found"
    UNKNOWN_VAR_PREFIX = "unknown_var_prefix"
    VAR_FALLBACK_PATTERN = "var_fallback_pattern"
    # The process booted without inference, which loads every backend but resolves no credential,
    # and was then asked for a backend to call.
    NOT_RESOLVED_ON_KEYLESS_BOOT = "not_resolved_on_keyless_boot"


class InferenceBackendCredentialsError(CogtError):
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


class InferenceBackendLibraryError(CogtError):
    """A backend the library cannot load.

    ``backend_name`` is the backend the error is about, stamped by the loader so a caller can charge
    the failure to that backend rather than to one whose name merely appears in the message's prose.
    """

    error_category = InferenceErrorCategory.CONFIGURATION


class RoutingProfileDisabledBackendError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelManagerError(CogtError):
    pass


class PluginModelDeclarationError(CogtError):
    """A model a plugin declares, or a model deck default it sets, cannot be merged into this installation's inference configuration.

    The model manager validates the plugins' declarations when it merges them at boot, since a plugin's ``register``
    only stores them: a model whose name the installation's ``internal.toml`` already declares, a table that is not a
    valid model spec, or a default for a format and source no step composes. The message names the plugin, and the
    file when one is involved.
    """

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

    def __init__(self, *, sdk: str) -> None:
        self.sdk = sdk
        super().__init__(f"The '{sdk}' SDK client does not support remote model listing.")


class ModelDeckNotFoundError(CogtError):
    pass


class ModelDeckValidationError(CogtError):
    pass
