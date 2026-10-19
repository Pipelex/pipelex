from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class PluginError(PipelexError):
    """Base for plugin-discovery and plugin-registration failures, never raised directly."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class PluginApiVersionMismatchError(PluginError):
    """A discovered plugin targets a plugin-API version this Pipelex does not support."""

    error_code = PipelexErrorCode.PLUGIN_API_MISMATCH

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
    ``runtime.plugins.disabled``, or a backend file still naming an sdk handle a
    release renamed, which the plugin that serves it no longer registers.
    """

    error_code = CoreCode.MODEL_UNAVAILABLE

    def __init__(self, *, family: str, sdk: str):
        self.family = family
        self.sdk = sdk
        message = (
            f"No inference backend registered for sdk '{sdk}' in the {family} family. Is its plugin installed and enabled? "
            f"If it is, '{sdk}' may be a handle a release renamed: `pipelex migrate` reports each backend file "
            "that still sets a retired handle."
        )
        super().__init__(message)


class DuplicateInferenceBackendError(PluginError):
    """Two plugins registered an inference backend for the same (family, sdk)."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

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

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, sdk: str, first_plugin: str, second_plugin: str):
        self.sdk = sdk
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Model lister for sdk '{sdk}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each sdk must have a single lister."
        )
        super().__init__(message)


class DuplicateServiceErrorCodeError(PluginError):
    """Two plugins contributed the same service error code."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, code: str, first_plugin: str, second_plugin: str):
        self.code = code
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Service error code '{code}' is contributed by both plugin '{first_plugin}' and plugin '{second_plugin}'. "
            f"Each code must mean one thing, so it must have a single contributor."
        )
        super().__init__(message)


class ReservedServiceErrorCodeError(PluginError):
    """A plugin contributed a service error code the runtime classifies itself."""

    error_code = PipelexErrorCode.PLUGIN_BROKEN

    def __init__(self, *, code: str, plugin: str):
        self.code = code
        self.plugin = plugin
        message = (
            f"Plugin '{plugin}' contributes service error code '{code}', which the runtime already classifies itself. "
            f"A contributed code must not compete with the runtime's own reading of it."
        )
        super().__init__(message)


class DuplicateOrchestratorError(PluginError):
    """Two plugins registered an orchestrator for the same orchestration mode."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

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

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, mode: str, first_plugin: str, second_plugin: str):
        self.mode = mode
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Bundle validator for orchestration mode '{mode}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each mode must have a single validator."
        )
        super().__init__(message)


class DuplicateStorageProviderError(PluginError):
    """Two plugins registered a storage provider for the same method."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, method: str, first_plugin: str, second_plugin: str):
        self.method = method
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Storage provider for method '{method}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each method must have a single provider."
        )
        super().__init__(message)


class DuplicateSecretsProviderError(PluginError):
    """Two plugins registered a secrets provider for the same method."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, method: str, first_plugin: str, second_plugin: str):
        self.method = method
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Secrets provider for method '{method}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each method must have a single provider."
        )
        super().__init__(message)


class DuplicateLogSinkError(PluginError):
    """Two plugins registered a log sink for the same method."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, method: str, first_plugin: str, second_plugin: str):
        self.method = method
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Log sink for method '{method}' is registered by both plugin '{first_plugin}' and plugin '{second_plugin}'. "
            "Each method must have a single sink."
        )
        super().__init__(message)


class DuplicateInternalModelError(PluginError):
    """Two plugins declared a model of the same name and model type in the internal backend."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, name: str, model_type: str, first_plugin: str, second_plugin: str):
        self.name = name
        self.model_type = model_type
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Internal model '{name}' of model type '{model_type}' is declared by both plugin '{first_plugin}' and plugin '{second_plugin}'. "
            "Each internal model must be declared by a single plugin."
        )
        super().__init__(message)


class DuplicateDocGenDefaultError(PluginError):
    """Two plugins declared the model deck's default document engine for the same format and source."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, choice_key: str, first_plugin: str, second_plugin: str):
        self.choice_key = choice_key
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"The default document engine for '{choice_key}' is declared by both plugin '{first_plugin}' and plugin '{second_plugin}'. "
            "Each format and source must have its default declared by a single plugin; a user sets their own in an x_custom_*.toml deck file."
        )
        super().__init__(message)


class DuplicatePipeFuncExecutorError(PluginError):
    """Two plugins registered a PipeFunc executor for the same execution mode."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, mode: str, first_plugin: str, second_plugin: str):
        self.mode = mode
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"PipeFunc executor for execution mode '{mode}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each mode must have a single executor."
        )
        super().__init__(message)


class DuplicatePipeFuncPackageOfferError(PluginError):
    """Two plugins stated the package offer of the same PipeFunc execution mode."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

    def __init__(self, *, mode: str, first_plugin: str, second_plugin: str):
        self.mode = mode
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"The PipeFunc package offer of execution mode '{mode}' is stated by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each mode must have a single package offer."
        )
        super().__init__(message)


class DuplicateHttpErrorMapperError(PluginError):
    """Two plugins registered an HTTP-error mapper for the same exception type."""

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

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

    error_code = PipelexErrorCode.PLUGIN_CONFLICT

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
    """A plugin that core requires unconditionally was named in ``runtime.plugins.disabled``."""

    error_code = PipelexErrorCode.CONFIG_INVALID

    def __init__(self, *, plugin_name: str):
        self.plugin_name = plugin_name
        message = f"Plugin '{plugin_name}' is required by core and cannot be disabled via runtime.plugins.disabled. Remove it from the denylist."
        super().__init__(message)


class PluginLayerViolationError(PluginError):
    """A kernel-group plugin registered an interpreter-layer capability.

    The entry-point group a plugin publishes under declares its layer, and a kernel-only boot reads
    the kernel group alone precisely so no interpreter-layer object is ever constructed there. A
    plugin whose declaration and menu calls disagree would defeat that: installed as kernel, loaded
    into a kernel-only process, it would hand back a ``Pipe``-aware object. Caught at register time,
    before anything it contributed is wired.
    """

    error_code = PipelexErrorCode.PLUGIN_BROKEN

    def __init__(self, *, plugin_name: str, capability: str, declared_group: str, interpreter_group: str):
        self.plugin_name = plugin_name
        self.capability = capability
        self.declared_group = declared_group
        self.interpreter_group = interpreter_group
        message = (
            f"Plugin '{plugin_name}' is published under the entry-point group '{declared_group}' but registered "
            f"an interpreter-layer capability ({capability}). Publish it under '{interpreter_group}' instead — a "
            "kernel-group plugin may only contribute kernel-layer capabilities (inference backends, model listers, "
            "storage and secrets providers, HTTP-error mappers, teardown callbacks, and the content_generator, "
            "task_manager and isolated_execution_probe hub slots)."
        )
        super().__init__(message)


class RetiredPluginEntryPointGroupError(PluginError):
    """An installed plugin still advertises itself under the retired single entry-point group.

    Nothing reads that group any more, so without this probe the plugin would simply never be
    discovered: no orchestrator, no backend, no error — a process quietly running without the
    capability it was installed for. Fail loud instead, naming the plugins and the group each
    should move to.
    """

    error_code = PipelexErrorCode.PLUGIN_BROKEN

    def __init__(self, *, plugin_names: list[str], retired_group: str, groups: list[str]):
        self.plugin_names = plugin_names
        self.retired_group = retired_group
        self.groups = groups
        named = ", ".join(f"'{name}'" for name in sorted(plugin_names))
        available = " or ".join(f"'{group}'" for group in groups)
        message = (
            f"Plugin(s) {named} advertise themselves under the retired entry-point group '{retired_group}', which is "
            f"no longer read. Upgrade each to a release published under {available}, or uninstall it to recover "
            "startup. If you author it: re-publish under the group matching its layer — a kernel-layer plugin "
            "(inference backend, model lister, storage or secrets provider) goes in the kernel group; anything that "
            "constructs a Pipe-aware object (orchestrator, bundle validator, PipeFunc executor) goes in the "
            "interpreter group."
        )
        super().__init__(message)


class PluginDeclaredInMultipleGroupsError(PluginError):
    """One installed plugin advertises the same name under more than one entry-point group.

    A boot that reads both groups then finds it twice, loads it twice and runs its ``register``
    twice. Most menu methods collide on the second pass, but the resulting ``Duplicate*Error``
    names the same plugin as both parties to the conflict — which reads as a bug in Pipelex rather
    than as a misdeclared distribution. ``add_teardown`` does not collide at all: it appends, so the
    callback lands twice and runs twice at shutdown with nothing raised. Neither symptom points at
    the cause, hence this error.

    The group is how a plugin declares its layer, so declaring two is not an over-declaration to be
    tolerated — it is the declaration failing to say anything.
    """

    error_code = PipelexErrorCode.PLUGIN_BROKEN

    def __init__(self, *, plugin_name: str, groups: list[str]):
        self.plugin_name = plugin_name
        self.groups = groups
        named = " and ".join(f"'{group}'" for group in sorted(groups))
        message = (
            f"Plugin '{plugin_name}' is published under {named}. The entry-point group is how a plugin declares "
            "which layer it belongs to, so it must appear in exactly one: keep the kernel group if it only "
            "contributes kernel-layer capabilities (inference backend, model lister, storage or secrets provider, "
            "HTTP-error mapper), and the interpreter group if it constructs any Pipe-aware object (orchestrator, "
            "bundle validator, PipeFunc executor). Remove the other declaration and reinstall."
        )
        super().__init__(message)


class BrokenPluginError(PluginError):
    """A discovered plugin failed while loading or registering itself."""

    error_code = PipelexErrorCode.PLUGIN_BROKEN

    def __init__(self, *, plugin_name: str, reason: str):
        self.plugin_name = plugin_name
        self.reason = reason
        message = f"Plugin '{plugin_name}' failed to register: {reason}"
        super().__init__(message)


class UnknownBootOrchestratorError(PluginError):
    """An explicit boot orchestrator was requested, but no plugin of that name is registered.

    The boot orchestrator (a boot argument, set via the CLI ``--orchestrator`` flag or
    ``Pipelex.setup(boot_orchestrator=...)``; never a ``pipelex.toml`` setting) names the *plugin*
    this process should boot under: a boot-orchestrator plugin claims the process-global hub slots
    iff ``boot_orchestrator == its own name``. When no discovered, registered plugin carries that
    name — the plugin is not installed, was disabled via ``runtime.plugins.disabled``, or the name
    is a typo — nothing claims the slots and execution would silently fall back to the in-process core
    defaults. We fail loud at boot instead. The message names no specific plugin, so core stays
    decoupled from its plugins.
    """

    error_code = PipelexErrorCode.PLUGIN_NOT_FOUND

    def __init__(self, *, requested: str):
        self.requested = requested
        message = (
            f"Boot orchestrator '{requested}' was requested, but no plugin named '{requested}' is registered "
            "(its plugin may not be installed, may be disabled via runtime.plugins.disabled, or the name may be a typo). "
            "Core provides only in-process execution; booting under a distributed orchestrator requires installing its plugin."
        )
        super().__init__(message)


class UnknownStorageMethodError(PluginError):
    """A configured storage method has no registered provider factory.

    ``runtime.storage.method`` selects a storage provider from the registry the built-in
    ``StoragePlugin`` (and any external ``pipelex-storage-<backend>`` plugin) populates. When
    the token names no registered factory — a typo, or an external provider plugin that is not
    installed or was disabled via ``runtime.plugins.disabled`` — boot fails loud here rather than
    starting with no storage. The message lists the registered methods so the fix is obvious.
    """

    error_code = PipelexErrorCode.PLUGIN_NOT_FOUND

    def __init__(self, *, method: str, registered_methods: list[str]):
        self.method = method
        self.registered_methods = registered_methods
        available = ", ".join(sorted(registered_methods)) or "(none)"
        message = (
            f"No storage provider is registered for method '{method}'. Registered methods: {available}. "
            "Check runtime.storage.method, or install/enable the plugin that provides that method."
        )
        super().__init__(message)


class UnknownPipeFuncExecutionModeError(PluginError):
    """A configured PipeFunc execution mode has no registered executor factory.

    ``interpreter.pipe_func.execution_mode`` selects a PipeFunc executor from the registry the built-in
    ``PipeFuncPlugin`` (``direct``) and any external sandbox plugin (e.g.
    our Daytona plugin → ``daytona``) populate. When the token names no registered factory —
    a typo, or a sandbox-backend plugin that is not installed or was disabled via ``runtime.plugins.disabled`` —
    boot fails loud here rather than starting with no PipeFunc executor. The message lists the
    registered modes so the fix is obvious.
    """

    error_code = PipelexErrorCode.PLUGIN_NOT_FOUND

    def __init__(self, *, mode: str, registered_modes: list[str]):
        self.mode = mode
        self.registered_modes = registered_modes
        available = ", ".join(sorted(registered_modes)) or "(none)"
        message = (
            f"No PipeFunc executor is registered for execution mode '{mode}'. Registered modes: {available}. "
            "Check interpreter.pipe_func.execution_mode, or install/enable the plugin that provides that mode."
        )
        super().__init__(message)


class UnknownSecretsMethodError(PluginError):
    """A configured secrets method has no registered provider factory.

    ``runtime.secrets.method`` selects a secrets provider from the registry the built-in
    ``SecretsPlugin`` (and any external ``pipelex-secrets-<backend>`` plugin) populates. When
    the token names no registered factory — a typo, or an external provider plugin that is not
    installed or was disabled via ``runtime.plugins.disabled`` — boot fails loud here rather than
    starting with no secrets provider. The message lists the registered methods so the fix is obvious.
    """

    error_code = PipelexErrorCode.PLUGIN_NOT_FOUND

    def __init__(self, *, method: str, registered_methods: list[str]):
        self.method = method
        self.registered_methods = registered_methods
        available = ", ".join(sorted(registered_methods)) or "(none)"
        message = (
            f"No secrets provider is registered for method '{method}'. Registered methods: {available}. "
            "Check runtime.secrets.method, or install/enable the plugin that provides that method."
        )
        super().__init__(message)


class UnknownLogSinkError(PluginError):
    """A configured log sink has no registered factory.

    ``runtime.log.sink`` selects a sink from the registry the built-in ``LogSinkPlugin`` (and any
    external plugin contributing one) populates. When the token names no registered factory — a typo,
    or an external plugin that is not installed or was disabled via ``runtime.plugins.disabled`` — boot
    fails loud here rather than starting with its records going nowhere. The message lists the
    registered sinks so the fix is obvious.
    """

    error_code = PipelexErrorCode.PLUGIN_NOT_FOUND

    def __init__(self, *, method: str, registered_methods: list[str]):
        self.method = method
        self.registered_methods = registered_methods
        available = ", ".join(sorted(registered_methods)) or "(none)"
        message = (
            f"No log sink is registered for '{method}'. Registered sinks: {available}. "
            "Check runtime.log.sink, or install/enable the plugin that provides that sink."
        )
        super().__init__(message)


class PluginErrorCodeNotRegisteredError(PluginError):
    """A plugin declared, at registration, a public error code that neither registry defines.

    Every code a plugin raises is one a caller reads, with its page and its next step, so it must be a code of the
    MTHDS core or of Pipelex's registry, whose names are public even where the plugin's implementation is closed.
    ``PluginRegistrar.declare_error_codes`` binds each declared code at boot, and this refuses the boot on the first
    code that does not parse, rather than letting it reach a caller as a code no page explains. The plugin is broken
    as packaged: a release of it targets codes this Pipelex does not define, so the fix is the plugin's.
    """

    error_code = PipelexErrorCode.PLUGIN_BROKEN

    def __init__(self, *, plugin_name: str, code: str):
        self.plugin_name = plugin_name
        self.code = code
        message = (
            f"Plugin '{plugin_name}' declares the error code '{code}', which is not a registered code of the MTHDS core or of "
            "Pipelex. Upgrade Pipelex or install a release of the plugin whose codes this Pipelex defines."
        )
        super().__init__(message)
