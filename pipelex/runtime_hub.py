"""The kernel layer's dependency hub: process-scoped infrastructure services.

``RuntimeHub`` brokers everything that is configured once at boot and never varies per method:
config, console, secrets, storage, telemetry, the model deck and inference workers, the content
generator, the reporting delegate, and the plugin registries. That is the machinery present at
execution time whatever is loaded — the **kernel layer**, in the language-implementation sense.

**The one rule:** ``interpreter_hub`` imports ``runtime_hub``; ``runtime_hub`` must never import
``interpreter_hub``. Nothing here may name ``libraries``, ``pipe_operators``, ``pipe_controllers``,
``codegen``, ``builder``, ``interpreter_plugins``, ``pipe_machinery``, ``pipe_signature``,
``mthds_parsing``, ``pipeline`` or ``pipe_run`` at module level. That list is the interpreter's
top-level packages — all of them, with no qualification — so the property it buys is stated
outright: **importing the Pipelex kernel layer loads zero interpreter modules.** It used to have to trail
"…or the Pipe-touching modules of ``core.pipes``", because some of what it forbids lived under a
package declared kernel-layer, and it had to leave out ``pipeline`` and ``pipe_run``, because four leaf
models of theirs landed in this module's closure. Both qualifications are gone the same way — the
misfiled code moved. ``pipelex.core`` is *not* on the list at all: the whole package is declared
kernel-layer, and this module's own closure runs straight through it. See
``docs/contribute/hub-layering.md``.
"""

import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from kajson.class_registry_abstract import ClassRegistryAbstract
from rich.console import Console

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import (
    ContentGeneratorProtocol,
)
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.inference_manager_protocol import InferenceManagerProtocol
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.plugins.sdk_client_manager import SdkClientManager
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.console_target import ConsoleTarget
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.class_registry_access import get_class_registry as _get_active_class_registry
from pipelex.system.registries.func_registry import FuncRegistry
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

if TYPE_CHECKING:
    # Deferred import: avoid pulling heavy SDK at module-load time
    from opentelemetry.trace import Tracer as OTelTracer

    from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
    from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry
    from pipelex.plugins.model_lister_registry import ModelListerRegistry
    from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
    from pipelex.plugins.secrets_provider_registry import SecretsProviderRegistry
    from pipelex.plugins.storage_provider_registry import StorageProviderRegistry
    from pipelex.tracing.event_log_protocol import EventLogProtocol


def _never_in_isolated_execution() -> bool:
    """Core default isolated-execution probe: the in-process orchestrator has no replay/activity
    split, so an emission is never inside an isolated sub-execution. A boot-orchestrator plugin
    whose runtime has such a split (a Temporal worker) replaces this by claiming
    ``HubSlot.ISOLATED_EXECUTION_PROBE``.
    """
    return False


class RuntimeHub:
    """Central dependency manager for process-scoped infrastructure services.

    Provides access to core providers and factories through a singleton instance, allowing
    components to retrieve dependencies based on protocols without direct imports that could
    create cycles. Its counterpart for method-scoped machinery (libraries, router, pipeline) is
    ``pipelex.interpreter_hub.InterpreterHub``.
    """

    _instance: ClassVar[Optional["RuntimeHub"]] = None

    def __init__(self):
        # tools
        self._config: ConfigRoot | None = None
        self._console: Console | None = None
        self._secrets_provider: SecretsProviderAbstract | None = None
        self._storage_provider: StorageProviderAbstract | None = None
        self._telemetry_manager: TelemetryManagerAbstract | None = None
        self._func_registry: FuncRegistry | None = None
        # cogt
        self._models_manager: ModelManagerAbstract | None = None
        self._sdk_client_manager: SdkClientManager | None = None
        self._inference_backend_registry: InferenceBackendRegistry | None = None
        self._model_lister_registry: ModelListerRegistry | None = None
        self._orchestrator_registry: OrchestratorRegistry | None = None
        self._bundle_validator_registry: BundleValidatorRegistry | None = None
        self._storage_provider_registry: StorageProviderRegistry | None = None
        self._secrets_provider_registry: SecretsProviderRegistry | None = None
        self._inference_manager: InferenceManagerProtocol
        self._report_delegate: ReportingProtocol
        self._content_generator: ContentGeneratorProtocol | None = None
        # Keyless boot (``Pipelex.make(needs_inference=False)``) forces every run to DRY (eng
        # review D4): the backend still picks inline vs in-workflow on its own; the leaf mocks.
        # Consumed by ``PipeRunParamsFactory.make_run_params`` (the single writer of run_mode).
        self._is_dry_run_forced: bool = False
        # Ambient probe claimed by a boot-orchestrator plugin (ISOLATED_EXECUTION_PROBE): True when
        # the current call runs inside an isolated sub-execution (a Temporal activity) whose emissions
        # must bypass the parent run's registered buffer. Core default never isolated (see
        # _never_in_isolated_execution); consumed by ReportingManager to route usage emissions.
        self._isolated_execution_probe: Callable[[], bool] = _never_in_isolated_execution

    ############################################################
    # Class methods for singleton management
    ############################################################

    @classmethod
    def get_optional_instance(cls) -> "RuntimeHub | None":
        return cls._instance

    @classmethod
    def get_instance(cls) -> "RuntimeHub":
        if cls._instance is None:
            msg = "RuntimeHub is not initialized"
            raise RuntimeError(msg)
        return cls._instance

    @classmethod
    def set_instance(cls, runtime_hub: "RuntimeHub") -> None:
        cls._instance = runtime_hub

    ############################################################
    # Setters
    ############################################################

    # tools

    def setup_config(self, config_cls: type[ConfigRoot], *, config_overrides: dict[str, Any] | None = None, config_dir: Path | None = None):
        """Set the global configuration instance.

        Args:
            config_cls: The config root class to validate against.
            config_overrides: Optional dict deep-merged on top of all TOML layers
                as the highest-priority override. Useful for tests that need
                specific config without editing TOML files.
            config_dir: Optional explicit config dir. When provided, project/global
                layering is bypassed and the load becomes package defaults + this
                directory (the package layer always applies — it is what the TOML
                overrides *are* overrides of). Used by the doctor ``--global`` path
                so the hub reflects exactly the directory being reported on.
        """
        config_dict = config_manager.load_config(extra_overrides=config_overrides, config_dir=config_dir)
        self.set_config(config=config_cls.model_validate(config_dict))

    def set_config(self, config: ConfigRoot):
        if self._config is not None:
            log.warning("set_config() got called but it has already been set")
            return
        self._config = config

    def reset_config(self) -> None:
        """Reset the global configuration instance and the config manager."""
        self._config = None
        log.reset()

    def set_console_print_target(self, target: ConsoleTarget):
        match target:
            case ConsoleTarget.STDOUT:
                self._console = Console(file=sys.stdout)
            case ConsoleTarget.STDERR:
                self._console = Console(file=sys.stderr)
            case _:
                msg = f"Invalid console target: {target}"
                raise ValueError(msg)

    def set_console(self, console: Console):
        self._console = console

    def set_secrets_provider(self, secrets_provider: SecretsProviderAbstract):
        self._secrets_provider = secrets_provider

    def set_storage_provider(self, storage_provider: StorageProviderAbstract | None):
        self._storage_provider = storage_provider

    def set_telemetry_manager(self, telemetry_manager: TelemetryManagerAbstract):
        self._telemetry_manager = telemetry_manager

    # cogt

    def set_models_manager(self, models_manager: ModelManagerAbstract):
        self._models_manager = models_manager

    def set_sdk_client_manager(self, sdk_client_manager: SdkClientManager):
        self._sdk_client_manager = sdk_client_manager

    def set_inference_backend_registry(self, inference_backend_registry: "InferenceBackendRegistry"):
        self._inference_backend_registry = inference_backend_registry

    def set_model_lister_registry(self, model_lister_registry: "ModelListerRegistry"):
        self._model_lister_registry = model_lister_registry

    def set_orchestrator_registry(self, orchestrator_registry: "OrchestratorRegistry"):
        self._orchestrator_registry = orchestrator_registry

    def set_bundle_validator_registry(self, bundle_validator_registry: "BundleValidatorRegistry"):
        self._bundle_validator_registry = bundle_validator_registry

    def set_storage_provider_registry(self, storage_provider_registry: "StorageProviderRegistry"):
        self._storage_provider_registry = storage_provider_registry

    def set_secrets_provider_registry(self, secrets_provider_registry: "SecretsProviderRegistry"):
        self._secrets_provider_registry = secrets_provider_registry

    def set_inference_manager(self, inference_manager: InferenceManagerProtocol):
        self._inference_manager = inference_manager

    def set_report_delegate(self, reporting_delegate: ReportingProtocol):
        self._report_delegate = reporting_delegate

    def set_content_generator(self, content_generator: ContentGeneratorProtocol):
        self._content_generator = content_generator

    def set_dry_run_forced(self, *, is_forced: bool) -> None:
        self._is_dry_run_forced = is_forced

    def is_dry_run_forced(self) -> bool:
        return self._is_dry_run_forced

    def set_isolated_execution_probe(self, probe: Callable[[], bool]) -> None:
        self._isolated_execution_probe = probe

    def set_func_registry(self, func_registry: FuncRegistry):
        self._func_registry = func_registry

    ############################################################
    # Getters
    ############################################################

    # tools

    def get_required_config(self) -> ConfigRoot:
        """Get the current configuration instance as an instance of a particular subclass of ConfigRoot. This should be used only from pipelex.tools.
            when getting the config from other projects, use their own project.get_config() method to get the Config
            with the proper subclass which is required for proper type checking.

        Returns:
            Config: The current configuration instance.

        Raises:
            RuntimeError: If the configuration has not been set.

        """
        if self._config is None:
            msg = "Config instance is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._config

    def get_optional_config(self) -> ConfigRoot | None:
        """Get the current configuration if it has been set, otherwise None.

        Non-raising counterpart to ``get_required_config``. Used by callers that must
        run before/around bootstrap (e.g. ``report_validation_error`` invoked from the
        doctor's setup helper when ``setup_config`` itself failed).
        """
        return self._config

    def get_console(self) -> Console:
        if self._console:
            return self._console
        else:
            return Console(stderr=True)

    def get_required_secrets_provider(self) -> SecretsProviderAbstract:
        if self._secrets_provider is None:
            msg = "Secrets provider is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._secrets_provider

    def get_storage_provider(self) -> StorageProviderAbstract:
        if self._storage_provider is None:
            msg = "StorageProvider is not initialized"
            raise RuntimeError(msg)
        return self._storage_provider

    def get_telemetry_manager(self) -> TelemetryManagerAbstract:
        if self._telemetry_manager is None:
            msg = "TelemetryManager is not initialized"
            raise RuntimeError(msg)
        return self._telemetry_manager

    def get_func_registry(self) -> FuncRegistry:
        if self._func_registry is None:
            msg = "FuncRegistry is not initialized"
            raise RuntimeError(msg)
        return self._func_registry

    # cogt

    def get_required_models_manager(self) -> ModelManagerAbstract:
        if self._models_manager is None:
            msg = "ModelsManager is not initialized"
            raise RuntimeError(msg)
        return self._models_manager

    def get_sdk_client_manager(self) -> SdkClientManager:
        if self._sdk_client_manager is None:
            msg = "SdkClientManager is not initialized"
            raise RuntimeError(msg)
        return self._sdk_client_manager

    def get_inference_backend_registry(self) -> "InferenceBackendRegistry":
        if self._inference_backend_registry is None:
            msg = "InferenceBackendRegistry is not initialized"
            raise RuntimeError(msg)
        return self._inference_backend_registry

    def get_model_lister_registry(self) -> "ModelListerRegistry":
        if self._model_lister_registry is None:
            msg = "ModelListerRegistry is not initialized"
            raise RuntimeError(msg)
        return self._model_lister_registry

    def get_orchestrator_registry(self) -> "OrchestratorRegistry":
        if self._orchestrator_registry is None:
            msg = "OrchestratorRegistry is not initialized"
            raise RuntimeError(msg)
        return self._orchestrator_registry

    def get_bundle_validator_registry(self) -> "BundleValidatorRegistry":
        if self._bundle_validator_registry is None:
            msg = "BundleValidatorRegistry is not initialized"
            raise RuntimeError(msg)
        return self._bundle_validator_registry

    def get_storage_provider_registry(self) -> "StorageProviderRegistry":
        if self._storage_provider_registry is None:
            msg = "StorageProviderRegistry is not initialized"
            raise RuntimeError(msg)
        return self._storage_provider_registry

    def get_secrets_provider_registry(self) -> "SecretsProviderRegistry":
        if self._secrets_provider_registry is None:
            msg = "SecretsProviderRegistry is not initialized"
            raise RuntimeError(msg)
        return self._secrets_provider_registry

    def get_inference_manager(self) -> InferenceManagerProtocol:
        return self._inference_manager

    def get_report_delegate(self) -> ReportingProtocol:
        return self._report_delegate

    def get_required_content_generator(self) -> ContentGeneratorProtocol:
        if self._content_generator is None:
            msg = "ContentGenerator is not initialized"
            raise RuntimeError(msg)
        return self._content_generator

    def is_in_isolated_execution(self) -> bool:
        """True when the current call runs inside an isolated sub-execution whose side-effecting
        emissions must not be written into the parent run's registered (replay-deterministic) buffer.

        Delegates to the boot-orchestrator's claimed probe (a Temporal worker reports True while a
        call executes inside an activity); the core default is always False.
        """
        return self._isolated_execution_probe()


# Shorthand functions for accessing the singleton


def get_runtime_hub() -> RuntimeHub:
    return RuntimeHub.get_instance()


def set_runtime_hub(runtime_hub: RuntimeHub):
    RuntimeHub.set_instance(runtime_hub)


# root convenience functions

# tools


def get_required_config() -> ConfigRoot:
    return get_runtime_hub().get_required_config()


def get_optional_config() -> ConfigRoot | None:
    """Non-raising by contract: also covers the no-hub-at-all state, not just hub-without-config."""
    runtime_hub = RuntimeHub.get_optional_instance()
    return runtime_hub.get_optional_config() if runtime_hub is not None else None


def get_secrets_provider() -> SecretsProviderAbstract:
    return get_runtime_hub().get_required_secrets_provider()


def get_storage_provider() -> StorageProviderAbstract:
    return get_runtime_hub().get_storage_provider()


def get_class_registry() -> ClassRegistryAbstract:
    """Return the active class registry, respecting per-workflow library scoping.

    When a library_id is set in the current async context (e.g. inside a Temporal workflow),
    returns the library's scoped ClassRegistry. Otherwise, returns the global registry.

    Delegates to ``pipelex.system.registries.class_registry_access``, which sits below this module
    so that ``core.concepts`` — inside this module's own import closure — can reach the same
    accessor without a cycle. This is the public entry point; prefer it.
    """
    return _get_active_class_registry()


def get_func_registry() -> FuncRegistry:
    return get_runtime_hub().get_func_registry()


def get_telemetry_manager() -> TelemetryManagerAbstract:
    return get_runtime_hub().get_telemetry_manager()


def get_otel_tracer() -> "OTelTracer | None":
    return get_telemetry_manager().get_otel_tracer()


# cogt


def get_models_manager() -> ModelManagerAbstract:
    return get_runtime_hub().get_required_models_manager()


def get_model_deck() -> ModelDeck:
    return get_models_manager().get_model_deck()


def get_sdk_client_manager() -> SdkClientManager:
    return get_runtime_hub().get_sdk_client_manager()


def get_inference_backend_registry() -> "InferenceBackendRegistry":
    return get_runtime_hub().get_inference_backend_registry()


def get_model_lister_registry() -> "ModelListerRegistry":
    return get_runtime_hub().get_model_lister_registry()


def get_orchestrator_registry() -> "OrchestratorRegistry":
    return get_runtime_hub().get_orchestrator_registry()


def get_bundle_validator_registry() -> "BundleValidatorRegistry":
    return get_runtime_hub().get_bundle_validator_registry()


def get_storage_provider_registry() -> "StorageProviderRegistry":
    return get_runtime_hub().get_storage_provider_registry()


def get_secrets_provider_registry() -> "SecretsProviderRegistry":
    return get_runtime_hub().get_secrets_provider_registry()


def get_inference_manager() -> InferenceManagerProtocol:
    return get_runtime_hub().get_inference_manager()


def get_llm_worker(
    llm_handle: str,
) -> LLMWorkerAbstract:
    return get_inference_manager().get_llm_worker(llm_handle=llm_handle)


def get_img_gen_worker(
    img_gen_handle: str,
) -> ImgGenWorkerAbstract:
    return get_inference_manager().get_img_gen_worker(img_gen_handle=img_gen_handle)


def get_extract_worker(
    extract_handle: str,
) -> ExtractWorkerAbstract:
    return get_inference_manager().get_extract_worker(extract_handle=extract_handle)


def get_report_delegate() -> ReportingProtocol:
    return get_runtime_hub().get_report_delegate()


def is_in_isolated_execution() -> bool:
    """Module-level accessor — see :meth:`RuntimeHub.is_in_isolated_execution`."""
    return get_runtime_hub().is_in_isolated_execution()


_content_generator_override: ContextVar[ContentGeneratorProtocol | None] = ContextVar("content_generator_override", default=None)


@contextmanager
def scoped_content_generator(content_generator: ContentGeneratorProtocol) -> Generator[None, None, None]:
    """Set ``content_generator`` as the active generator for the scope, then restore the prior value on exit.

    Inference operators (PipeLLM / PipeImgGen / PipeExtract / PipeSearch / PipeStructure) resolve
    :func:`get_content_generator`; under a Temporal-enabled hub that default is
    ``ContentGeneratorInWorkflow``, which dispatches activities. An in-process run (e.g. the
    dry-run/validation activity body) wraps itself in this scope with an inline generator so its
    leaves never dispatch — the DRY mock lives at the cogt leaf, so the inline generator's leaves
    mock without dispatching and without storage IO. ContextVar-scoped like
    :func:`pipelex.interpreter_hub.scoped_pipe_router`, so concurrent runs don't cross-contaminate.
    """
    prev = _content_generator_override.get()
    _content_generator_override.set(content_generator)
    try:
        yield
    finally:
        _content_generator_override.set(prev)


def is_dry_run_forced() -> bool:
    """True when the boot was keyless (``needs_inference=False``): every run is forced to DRY (D4)."""
    return get_runtime_hub().is_dry_run_forced()


def resolve_run_mode_for_boot(*, requested: PipeRunMode) -> PipeRunMode:
    """Apply the keyless-boot forced-DRY flag to a requested run mode (eng review D4).

    The one place the flag is *applied*, sitting beside the accessor that reads it. Every factory
    that mints run params for a run **this process initiates** calls it — the pipe tier's
    ``PipeRunParamsFactory.make_run_params`` and the kernel tier's ``PipelexKernel.make`` — so
    ``needs_inference=False`` stays a property of the boot rather than of whichever entry point a
    caller happened to reach for. A second copy of the rule at a second factory is exactly how the
    two would drift apart.

    Note what this does NOT cover, deliberately: constructing a ``PipeRunParams`` or a
    ``CogtRunParams`` directly bypasses it, just as it bypasses every other factory-level default.
    Params handed to a worker over the wire are likewise untouched — the flag is a submitter-side
    contract, not a constraint on work this process executes for someone else.
    """
    if is_dry_run_forced() and requested.is_live:
        log.warning(
            "LIVE run requested under a keyless boot (needs_inference=False): forcing run_mode to DRY — "
            "outputs will be synthetic mocks, not real inference."
        )
        return PipeRunMode.DRY
    return requested


def get_content_generator() -> ContentGeneratorProtocol:
    override = _content_generator_override.get()
    if override is not None:
        return override
    return get_runtime_hub().get_required_content_generator()


def get_secret(secret_id: str) -> str:
    return get_secrets_provider().get_secret(secret_id=secret_id)


_event_log_override: ContextVar["EventLogProtocol | None"] = ContextVar("event_log_override", default=None)


@contextmanager
def scoped_event_log(event_log: "EventLogProtocol") -> Generator[None, None, None]:
    """Pin ``event_log`` as the trace-event transport for the scope, then restore the prior value on exit.

    Both the write side (tracer emission, set up in ``pipeline_run_setup``) and the read
    side (``tracing_assembly.assemble_tracing``) prefer this override over building a new
    backend via ``make_event_log``, so emit and assemble share the SAME instance — which
    is what makes a plain in-memory event log usable for graph assembly (no external
    store bridges the two sides). A set override implies tracing-enabled: it is honored
    even when ``tracing_config.is_enabled`` is False.

    Lifecycle: the machinery never calls ``cleanup`` on the instance and the read side does
    not ``close`` it — but the write-side tracer DOES call ``close()`` on its event log at
    teardown (``GraphTracer._reset``), which happens BEFORE the read side assembles. A scoped
    event log's ``close()`` must therefore be safe to call mid-lifecycle — idempotent or a
    no-op, as ``InMemoryEventLog``'s is. Scoping a backend whose ``close()`` releases a real
    resource (NDJSON file handle, DynamoDB client) would break its own assembly read. Mirrors
    :func:`pipelex.interpreter_hub.scoped_pipe_router`.
    """
    prev = _event_log_override.get()
    _event_log_override.set(event_log)
    try:
        yield
    finally:
        _event_log_override.set(prev)


def get_event_log_override() -> "EventLogProtocol | None":
    """Return the contextvar-scoped event-log override set by :func:`scoped_event_log`, or None."""
    return _event_log_override.get()


def get_console() -> Console:
    runtime_hub = RuntimeHub.get_optional_instance()
    if runtime_hub:
        return runtime_hub.get_console()
    else:
        return Console(stderr=True)
