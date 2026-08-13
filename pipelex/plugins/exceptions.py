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


class DuplicateStorageProviderError(PluginError):
    """Two plugins registered a storage provider for the same method."""

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

    def __init__(self, *, method: str, first_plugin: str, second_plugin: str):
        self.method = method
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"Secrets provider for method '{method}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each method must have a single provider."
        )
        super().__init__(message)


class DuplicatePipeFuncExecutorError(PluginError):
    """Two plugins registered a PipeFunc executor for the same execution mode."""

    def __init__(self, *, mode: str, first_plugin: str, second_plugin: str):
        self.mode = mode
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        message = (
            f"PipeFunc executor for execution mode '{mode}' is registered by both plugin "
            f"'{first_plugin}' and plugin '{second_plugin}'. Each mode must have a single executor."
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


class PluginLayerViolationError(PluginError):
    """A kernel-group plugin registered an interpreter-layer capability.

    The entry-point group a plugin publishes under declares its layer, and a kernel-only boot reads
    the kernel group alone precisely so no interpreter-layer object is ever constructed there. A
    plugin whose declaration and menu calls disagree would defeat that: installed as kernel, loaded
    into a kernel-only process, it would hand back a ``Pipe``-aware object. Caught at register time,
    before anything it contributed is wired.
    """

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

    # The message names the caller's own installed distributions and the exact fix; it is fully
    # actionable, so keep it verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

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

    # The message names the caller's own installed distribution and the exact fix.
    _authors_caller_facing_message = True

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

    def __init__(self, *, plugin_name: str, reason: str):
        self.plugin_name = plugin_name
        self.reason = reason
        message = f"Plugin '{plugin_name}' failed to register: {reason}"
        super().__init__(message)


class UnknownBootOrchestratorError(PluginError):
    """An explicit boot orchestrator was requested, but no plugin of that name is registered.

    ``plugins.boot_orchestrator`` (set via the CLI ``--orchestrator`` flag or
    ``Pipelex.setup(boot_orchestrator=...)``) names the *plugin* this process should boot under:
    a boot-orchestrator plugin claims the process-global hub slots iff
    ``plugins.boot_orchestrator == its own name``. When no discovered, registered plugin carries
    that name — the plugin is not installed, was disabled via ``plugins.disabled``, or the name is
    a typo — nothing claims the slots and execution would silently fall back to the in-process core
    defaults. We fail loud at boot instead. The message names no specific plugin, so core stays
    decoupled from its plugins.
    """

    # The message describes the caller's own input (the requested orchestrator name) and is fully
    # actionable; keep it verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, requested: str):
        self.requested = requested
        message = (
            f"Boot orchestrator '{requested}' was requested, but no plugin named '{requested}' is registered "
            "(its plugin may not be installed, may be disabled via plugins.disabled, or the name may be a typo). "
            "Core provides only in-process execution; booting under a distributed orchestrator requires installing its plugin."
        )
        super().__init__(message)


class UnknownStorageMethodError(PluginError):
    """A configured storage method has no registered provider factory.

    ``storage_config.method`` selects a storage provider from the registry the built-in
    ``StoragePlugin`` (and any external ``pipelex-storage-<backend>`` plugin) populates. When
    the token names no registered factory — a typo, or an external provider plugin that is not
    installed or was disabled via ``plugins.disabled`` — boot fails loud here rather than
    starting with no storage. The message lists the registered methods so the fix is obvious.
    """

    # The message describes the caller's own input (the configured storage method) and lists the
    # registered methods; it is fully actionable, so keep it verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, method: str, registered_methods: list[str]):
        self.method = method
        self.registered_methods = registered_methods
        available = ", ".join(sorted(registered_methods)) or "(none)"
        message = (
            f"No storage provider is registered for method '{method}'. Registered methods: {available}. "
            "Check storage_config.method, or install/enable the plugin that provides that method."
        )
        super().__init__(message)


class UnknownPipeFuncExecutionModeError(PluginError):
    """A configured PipeFunc execution mode has no registered executor factory.

    ``pipe_func_config.execution_mode`` selects a PipeFunc executor from the registry the built-in
    ``PipeFuncPlugin`` (``direct``) and any external sandbox plugin (e.g.
    our Daytona plugin → ``daytona``) populate. When the token names no registered factory —
    a typo, or a sandbox-backend plugin that is not installed or was disabled via ``plugins.disabled`` —
    boot fails loud here rather than starting with no PipeFunc executor. The message lists the
    registered modes so the fix is obvious.
    """

    # The message describes the caller's own input (the configured execution mode) and lists the
    # registered modes; it is fully actionable, so keep it verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, mode: str, registered_modes: list[str]):
        self.mode = mode
        self.registered_modes = registered_modes
        available = ", ".join(sorted(registered_modes)) or "(none)"
        message = (
            f"No PipeFunc executor is registered for execution mode '{mode}'. Registered modes: {available}. "
            "Check pipe_func_config.execution_mode, or install/enable the plugin that provides that mode."
        )
        super().__init__(message)


class UnknownSecretsMethodError(PluginError):
    """A configured secrets method has no registered provider factory.

    ``secrets_config.method`` selects a secrets provider from the registry the built-in
    ``SecretsPlugin`` (and any external ``pipelex-secrets-<backend>`` plugin) populates. When
    the token names no registered factory — a typo, or an external provider plugin that is not
    installed or was disabled via ``plugins.disabled`` — boot fails loud here rather than
    starting with no secrets provider. The message lists the registered methods so the fix is obvious.
    """

    # The message describes the caller's own input (the configured secrets method) and lists the
    # registered methods; it is fully actionable, so keep it verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, method: str, registered_methods: list[str]):
        self.method = method
        self.registered_methods = registered_methods
        available = ", ".join(sorted(registered_methods)) or "(none)"
        message = (
            f"No secrets provider is registered for method '{method}'. Registered methods: {available}. "
            "Check secrets_config.method, or install/enable the plugin that provides that method."
        )
        super().__init__(message)
