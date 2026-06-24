from pipelex.base_exceptions import ErrorDomain, PipelexError


class PluginError(PipelexError):
    """Base for plugin-discovery and plugin-registration failures."""

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Plugin error"


class PluginApiVersionMismatchError(PluginError):
    """A discovered plugin targets a plugin-API version this Pipelex does not support."""

    def __init__(self, *, plugin_name: str, targets_api: object, supported_api: int):
        self.plugin_name = plugin_name
        self.targets_api = targets_api
        self.supported_api = supported_api
        message = (
            f"Plugin '{plugin_name}' targets plugin API version {targets_api!r}, "
            f"but this Pipelex supports version {supported_api}. "
            "Upgrade Pipelex or install a plugin version that targets the supported API."
        )
        super().__init__(message)


class InferenceBackendNotFoundError(PluginError):
    """No inference backend is registered for a requested (family, sdk).

    Raised by the family worker factories on a registry-lookup miss — typically a
    model whose backend plugin is not installed or was disabled via
    ``plugins.disabled``.
    """

    def __init__(self, *, family: str, sdk: str):
        self.family = family
        self.sdk = sdk
        message = f"No inference backend registered for sdk '{sdk}' in the {family} family. Is its plugin installed and enabled?"
        super().__init__(message)


class DuplicateInferenceBackendError(PluginError):
    """Two plugins registered an inference backend for the same (family, sdk)."""

    def __init__(self, *, family: str, sdk: str, first_plugin: str, second_plugin: str):
        self.family = family
        self.sdk = sdk
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Inference backend ({family}, '{sdk}') is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each (family, sdk) must have a single backend."
        )
        super().__init__(message)


class DuplicateModelListerError(PluginError):
    """Two plugins registered a model lister for the same sdk."""

    def __init__(self, *, sdk: str, first_plugin: str, second_plugin: str):
        self.sdk = sdk
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Model lister for sdk '{sdk}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each sdk must have a single lister."
        )
        super().__init__(message)


class DuplicateOrchestratorError(PluginError):
    """Two plugins registered an orchestrator for the same orchestration mode."""

    def __init__(self, *, mode: str, first_plugin: str, second_plugin: str):
        self.mode = mode
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Orchestrator for orchestration mode '{mode}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each mode must have a single orchestrator."
        )
        super().__init__(message)


class DuplicateBundleValidatorError(PluginError):
    """Two plugins registered a bundle validator for the same orchestration mode."""

    def __init__(self, *, mode: str, first_plugin: str, second_plugin: str):
        self.mode = mode
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Bundle validator for orchestration mode '{mode}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each mode must have a single validator."
        )
        super().__init__(message)


class DuplicateHttpErrorMapperError(PluginError):
    """Two plugins registered an HTTP-error mapper for the same exception type."""

    def __init__(self, *, exc_type: str, first_plugin: str, second_plugin: str):
        self.exc_type = exc_type
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"HTTP-error mapper for exception type '{exc_type}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each exception type must have a single mapper."
        )
        super().__init__(message)


class HubSlotAlreadyClaimedError(PluginError):
    """Two plugins claimed the same hub slot."""

    def __init__(self, *, slot: str, first_plugin: str, second_plugin: str):
        self.slot = slot
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Hub slot '{slot}' is claimed by both plugin '{first_plugin}' and plugin "
            f"'{second_plugin}'. Each slot can be claimed by at most one plugin."
        )
        super().__init__(message)


class CoreUnconditionalPluginDisabledError(PluginError):
    """A plugin that core requires unconditionally was named in plugins.disabled."""

    def __init__(self, *, plugin_name: str):
        self.plugin_name = plugin_name
        message = f"Plugin '{plugin_name}' is required by core and cannot be disabled via plugins.disabled. Remove it from the denylist."
        super().__init__(message)


class BrokenPluginError(PluginError):
    """A discovered plugin failed while loading or registering itself."""

    def __init__(self, *, plugin_name: str, reason: str):
        self.plugin_name = plugin_name
        self.reason = reason
        message = f"Plugin '{plugin_name}' failed to register: {reason}"
        super().__init__(message)
