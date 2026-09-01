from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, iter_cause_chain
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.system.pipelex_service.types import RemoteConfigSource

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
    ):
        super().__init__(message)
        if error_category is not None:
            self.error_category = error_category
        if user_action is not None:
            self.user_action = user_action
        if provider_metadata is not None:
            self.provider_metadata = provider_metadata

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
    """Error raised when a model choice cannot be found in the model deck.

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


class ExtractOutputError(CogtError):
    pass


class GeneratedImageError(CogtError):
    pass


class LLMModelNotFoundError(ModelNotFoundError):
    pass


class LLMCapabilityError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


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


class ExtractJobFailureError(CogtError):
    pass


class ExtractModelNotFoundError(ModelNotFoundError):
    pass


class SearchJobFailureError(CogtError):
    pass


class SearchModelNotFoundError(ModelNotFoundError):
    pass


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
    ):
        self.credentials_error_type = credentials_error_type
        self.backend_name = backend_name
        self.key_name = key_name
        super().__init__(message)


class InferenceBackendLibraryError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class RoutingProfileDisabledBackendError(CogtError):
    error_category = InferenceErrorCategory.CONFIGURATION


class ModelManagerError(CogtError):
    pass


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


class GatewayUnknownModelError(CogtError):
    """A model handle the active routing profile sends to a managed gateway is absent from its specs.

    Carries the provenance of the gateway config (``FRESH`` vs ``CACHED``) so the message can
    branch: a cached-source failure suggests stale gateway specs and points the user at
    ``pipelex init`` to refresh while online; a fresh-source failure is a genuine
    misconfiguration.

    **And it carries the backend name**, because more than one managed gateway can be live at once
    and "which one" is then a question the message has to answer — the handle may be perfectly
    present in the other service's section, which is a legitimate configuration rather than a
    contradiction.
    """

    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, model_name: str, backend_name: str, source: RemoteConfigSource) -> None:
        self.model_name = model_name
        self.backend_name = backend_name
        self.source = source
        match source:
            case RemoteConfigSource.FRESH:
                msg = (
                    f"Model handle '{model_name}' is routed to backend '{backend_name}' by the active routing profile, "
                    f"but is not present in the model specs we just fetched for it. Either the model name is wrong, that "
                    f"gateway no longer offers it, or your deck overrides need updating.\n"
                    f"  - Run `pipelex doctor` to inspect the active gateway models.\n"
                    f"  - Route this model to another backend in .pipelex/inference/routing_profiles.toml.\n"
                    f"  - Or disable {backend_name} in .pipelex/inference/backends.toml to fall back to BYOK."
                )
            case RemoteConfigSource.CACHED:
                msg = (
                    f"Model handle '{model_name}' is routed to backend '{backend_name}' by the active routing profile, "
                    f"but is not present in the model specs loaded for it from the on-disk cache. The cache may be stale.\n"
                    f"  - Run `pipelex init` while online to refresh the cached gateway config.\n"
                    f"  - Or disable {backend_name} in .pipelex/inference/backends.toml to operate offline (BYOK)."
                )
        super().__init__(msg)
