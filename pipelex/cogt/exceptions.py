from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.base_exceptions import ErrorReport, PipelexError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.types import StrEnum

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


class CogtError(PipelexError):
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
    ):
        super().__init__(message)
        if error_category is not None:
            self.error_category = error_category
        if user_action is not None:
            self.user_action = user_action
        if provider_metadata is not None:
            self.provider_metadata = provider_metadata

    def fill_model_and_provider(self, model_handle: str | None, backend_name: str | None) -> None:
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
        report = ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            error_category=self.error_category,
            error_domain=self.error_domain,
            retryable=self.error_category.is_retryable if self.error_category is not None else None,
            user_action=self.user_action,
            model=self.model_handle,
            provider=self.backend_name,
            provider_metadata=self.provider_metadata,
        )
        return self._enrich_error_report_from_cause(report)


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

    The ``id()`` set guards against a cyclic ``__cause__`` chain: without it a cycle would
    spin this loop forever — and it runs on the error path, so the failure being classified
    would be lost to a hang rather than reported.
    """
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, CogtError) and current.error_category is not None:
            return current.error_category
        current = current.__cause__
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


class LLMPromptTemplateInputsError(CogtError):
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


class ModelDeckNotFoundError(CogtError):
    pass


class ModelDeckValidationError(CogtError):
    pass


class GatewayUnknownModelError(CogtError):
    """A model handle referenced by the deck cannot be located in the active gateway specs.

    Carries the provenance of the gateway config (``FRESH`` vs ``CACHED``) so the message can
    branch: a cached-source failure suggests stale gateway specs and points the user at
    ``pipelex init`` to refresh while online; a fresh-source failure is a genuine
    misconfiguration.
    """

    error_category = InferenceErrorCategory.CONFIGURATION

    def __init__(self, model_name: str, source: RemoteConfigSource) -> None:
        self.model_name = model_name
        self.source = source
        match source:
            case RemoteConfigSource.FRESH:
                msg = (
                    f"Model handle '{model_name}' is referenced by the active model deck but is not present "
                    "in the Pipelex Gateway specs we just fetched. Either the model name is wrong, the gateway "
                    "no longer offers it, or your deck overrides need updating.\n"
                    "  - Run `pipelex doctor` to inspect the active gateway models.\n"
                    "  - Disable pipelex_gateway in .pipelex/inference/backends.toml to fall back to BYOK."
                )
            case RemoteConfigSource.CACHED:
                msg = (
                    f"Model handle '{model_name}' is referenced by the active model deck but is not present "
                    "in the Pipelex Gateway specs loaded from the on-disk cache. The cache may be stale.\n"
                    "  - Run `pipelex init` while online to refresh the cached gateway config.\n"
                    "  - Or disable pipelex_gateway in .pipelex/inference/backends.toml to operate offline (BYOK)."
                )
        super().__init__(msg)
