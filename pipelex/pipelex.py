"""The interpreter layer's composition root: the runtime boot plus the method machinery.

``Pipelex`` is the public entry point every consumer and sibling repo imports, and it is the
interpreter half of the boot: it subclasses :class:`pipelex.runtime_boot.RuntimeBoot` — importing it
downward, which the interpreter layer may do — and appends the constructions that only a process
which will actually load and run a method needs: the ``InterpreterHub``, the composed plugin
manifests, the ``PipeFuncExecutorRegistry`` and its executor, the ``LibraryManager``, the
``PipelineManager``, the pipe-kind class registrations, the ``PipeRouter`` and the ``PipeRun``.

Inheritance rather than composition is deliberate: every attribute address is preserved
(``self.models_manager``, ``self.class_registry``, ``self.telemetry_manager`` and the rest keep
working from both halves), the singleton stays keyed such that ``Pipelex`` and ``RuntimeBoot`` exclude
each other, and it reads as what it is — the interpreter boot *is* the runtime boot plus the
interpreter constructions. See ``docs/contribute/hub-layering.md``.
"""

from pathlib import Path
from typing import Any, Self

from kajson.class_registry_abstract import ClassRegistryAbstract
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.content_generation.content_generator_protocol import (
    ContentGeneratorProtocol,
)
from pipelex.cogt.inference.inference_manager import InferenceManager
from pipelex.cogt.models.model_manager_abstract import ModelManagerAbstract
from pipelex.config import get_config, get_pipe_func_execution_mode
from pipelex.interpreter_hub import InterpreterHub, set_interpreter_hub
from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS, CORE_UNCONDITIONAL_PLUGIN_NAMES
from pipelex.libraries.library_manager import LibraryManager
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.observer.observer_protocol import ObserverProtocol
from pipelex.pipe_machinery.registry_models import PipeRegistryModels
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutorProtocol
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipeline.pipeline_manager import PipelineManager
from pipelex.pipeline.pipeline_manager_abstract import PipelineManagerAbstract
from pipelex.plugins.pipe_func_executor_registry import PipeFuncExecutorRegistry
from pipelex.plugins.registrar import HubSlot
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_boot import PACKAGE_NAME, PACKAGE_VERSION, RuntimeBoot
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.environment import get_pipelexpath_dirs
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.telemetry_config import (
    TelemetryConfig,
)
from pipelex.system.telemetry.telemetry_manager_abstract import (
    TelemetryManagerAbstract,
)
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class Pipelex(RuntimeBoot):
    def __init__(
        self,
        *,
        config_dir: Path | None = None,
        config_cls: type[ConfigRoot] | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        # Two hubs, two lifecycles: RuntimeHub is process-scoped infrastructure, InterpreterHub is the
        # library-scoped method machinery. Runtime is constructed first because it is the lower layer,
        # so it reads first — not because installing the InterpreterHub needs it: that install only
        # stores the class-registry scoping resolver, which resolves lazily at call time.
        super().__init__(config_dir=config_dir, config_cls=config_cls, config_overrides=config_overrides)
        self.interpreter_hub = InterpreterHub()
        set_interpreter_hub(self.interpreter_hub)

        # pipeline
        self.library_manager: LibraryManagerAbstract | None = None

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} init done")

    @override
    def setup(
        self,
        *,
        integration_mode: IntegrationMode,
        needs_inference: bool = True,
        boot_orchestrator: str | None = None,
        needs_model_specs: bool | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipe_func_executor: PipeFuncExecutorProtocol | None = None,
        pipeline_manager: PipelineManagerAbstract | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        library_manager: LibraryManagerAbstract | None = None,
        library_dirs: list[str] | list[Path] | None = None,
        **kwargs: Any,
    ) -> None:
        if kwargs:
            msg = f"The Pipelex setup method does not support any additional arguments: {kwargs}"
            raise PipelexSetupError(msg)

        # The runtime layer first, with the *composed* plugin manifests: this process will run methods,
        # so it needs the interpreter-touching built-ins (the `direct` orchestrator, the built-in
        # PipeFunc executor modes) alongside the runtime half a bare RuntimeBoot discovers.
        super().setup(
            integration_mode=integration_mode,
            needs_inference=needs_inference,
            boot_orchestrator=boot_orchestrator,
            needs_model_specs=needs_model_specs,
            builtin_plugins=BUILTIN_PLUGINS,
            core_unconditional_plugin_names=CORE_UNCONDITIONAL_PLUGIN_NAMES,
            class_registry=class_registry,
            secrets_provider=secrets_provider,
            storage_provider=storage_provider,
            models_manager=models_manager,
            inference_manager=inference_manager,
            content_generator=content_generator,
            reporting_delegate=reporting_delegate,
            telemetry_config=telemetry_config,
            telemetry_manager=telemetry_manager,
            observers=observers,
        )

        # --- The interpreter layer ---------------------------------------------------------------
        # Everything below needs a method to be loadable. Nothing the runtime setup above does
        # consumes any of it, which is what lets these be a tail rather than an interleaving; the two
        # values that cross the seam go the other way (``self._plugin_registrar`` and
        # ``self.multi_observer``, both built by the runtime half and read here).

        plugin_registrar = self._plugin_registrar
        if plugin_registrar is None:
            msg = "The plugin registrar must be built by the runtime setup before the interpreter setup runs"
            raise PipelexSetupError(msg)

        pipe_func_executor_registry = PipeFuncExecutorRegistry(plugin_registrar.pipe_func_executors)
        self.interpreter_hub.set_pipe_func_executor_registry(pipe_func_executor_registry)

        # Injection precedence: explicit setup() param > plugin slot-claim thunk > config-selected
        # registry factory. The PipeFunc execution axis is orthogonal to orchestration: a Temporal
        # worker claims the PIPE_FUNC_EXECUTOR slot to wrap execution in an activity, and inside that
        # activity resolves the real executor through this same registry by execution_mode. Every
        # non-worker boot resolves directly here — pipe_func_config.execution_mode selects the mode
        # ("direct" in-process by default; a sandbox mode like "daytona" runs it out-of-process).
        if pipe_func_executor is None:
            pipe_func_config = get_config().pipelex.pipe_func_config
            execution_mode = get_pipe_func_execution_mode()
            pipe_func_executor = self._resolve_hub_slot(
                slot=HubSlot.PIPE_FUNC_EXECUTOR,
                default=lambda: pipe_func_executor_registry.get_required(mode=execution_mode)(pipe_func_config),
            )
        self.interpreter_hub.set_pipe_func_executor(pipe_func_executor)

        # --- Libraries -------------------------------------------------------------------------

        self.library_manager = library_manager or LibraryManager()
        self.interpreter_hub.set_library_manager(library_manager=self.library_manager)

        # Resolve library_dirs: explicit value replaces PIPELEXPATH, otherwise use env var as fallback
        # When library_dirs is explicitly provided (even if empty), it overrides the env var
        if library_dirs is not None:
            resolved_library_dirs = [Path(dir_path) for dir_path in library_dirs]
            self.interpreter_hub.set_default_library_dirs(resolved_library_dirs)
        else:
            pipelexpath_dirs = get_pipelexpath_dirs()
            if pipelexpath_dirs is not None:
                self.interpreter_hub.set_default_library_dirs(pipelexpath_dirs)

        self.pipeline_manager = pipeline_manager or PipelineManager()
        self.interpreter_hub.set_pipeline_manager(pipeline_manager=self.pipeline_manager)
        self.pipeline_manager.setup()

        # Two manifests, one registry: core's value model (registered by the runtime setup above) and
        # the pipe kinds. They are disjoint by construction and pinned as such by
        # tests/unit/pipelex/test_registry_models_split.py, so the two calls landing in different
        # halves carries no meaning beyond that.
        if self.class_registry is None:
            msg = "The class registry must be created by the runtime setup before the interpreter setup runs"
            raise PipelexSetupError(msg)
        self.class_registry.register_classes(PipeRegistryModels.get_all_models())

        # --- Pipe Router -----------------------------------------------------------------------
        # Injection precedence (codex C8): explicit setup() param > plugin slot-claim thunk > core default.

        if pipe_router:
            self.interpreter_hub.set_pipe_router(pipe_router)
        else:
            self.interpreter_hub.set_pipe_router(
                self._resolve_hub_slot(slot=HubSlot.PIPE_ROUTER, default=lambda: PipeRouter(observer=self.multi_observer))
            )

        # --- Pipe Run --------------------------------------------------------------------------
        # No explicit param for pipe_run: plugin slot-claim thunk > core default.

        self.interpreter_hub.set_pipe_run(
            self._resolve_hub_slot(slot=HubSlot.PIPE_RUN, default=lambda: PipeRun(pipe_router=self.interpreter_hub.get_required_pipe_router()))
        )

        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} setup done")

    @override
    def teardown(self) -> None:
        # The three phases in this order deliberately: the plugin-contributed callbacks (LIFO) run
        # first — e.g. a Temporal worker tears down its task manager + resets its hub — so a worker's
        # in-flight resources release before the pipeline manager drops the pipelines they may still
        # be reporting on. Sequenced explicitly here rather than through a template hook, because that
        # order is the whole reason the runtime teardown is split into phases.
        # ``try``/``finally`` and not a bare sequence, covering *both* leading phases: ``pipeline_manager``
        # is a public ``make()`` injection point typed as ``PipelineManagerAbstract``, so its ``teardown``
        # can raise, and the plugin callbacks are unbounded third-party code whose per-callback
        # ``except Exception`` does not cover ``BaseException``. ``_teardown_runtime`` is what leaves the
        # process re-bootable, so skipping it would wedge the process for good — see its docstring. The
        # order is preserved by keeping both statements in the ``try``. No ``except``: the failure still
        # propagates.
        try:
            self._teardown_plugin_callbacks()
            self.pipeline_manager.teardown()
        finally:
            self._teardown_runtime()

    @classmethod
    @override
    def make(
        cls,
        *,
        integration_mode: IntegrationMode = IntegrationMode.PYTHON,
        needs_inference: bool = True,
        boot_orchestrator: str | None = None,
        needs_model_specs: bool | None = None,
        class_registry: ClassRegistryAbstract | None = None,
        secrets_provider: SecretsProviderAbstract | None = None,
        storage_provider: StorageProviderAbstract | None = None,
        models_manager: ModelManagerAbstract | None = None,
        inference_manager: InferenceManager | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
        pipe_func_executor: PipeFuncExecutorProtocol | None = None,
        pipeline_manager: PipelineManagerAbstract | None = None,
        pipe_router: PipeRouterProtocol | None = None,
        reporting_delegate: ReportingProtocol | None = None,
        telemetry_config: TelemetryConfig | None = None,
        telemetry_manager: TelemetryManagerAbstract | None = None,
        observers: dict[str, ObserverProtocol] | None = None,
        library_dirs: list[str] | list[Path] | None = None,
        config_dir: Path | None = None,
        config_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Self:
        """Create and initialize a Pipelex singleton instance.

        All parameters are optional dependency injections. If None, default implementations
        are used during setup. This enables customization of core components like secrets
        management, storage, model routing, and pipeline execution.

        Args:
            integration_mode: Integration mode (CLI, FASTAPI, DOCKER, MCP, N8N, PYTHON, PYTEST)
            needs_inference: When False, forces every run THIS process initiates to DRY mode
                (consumed at PipeRunParamsFactory.make_run_params, the single writer of run_mode:
                operators dispatch normally and the cogt leaf mocks) and loads backends leniently
                (skipping those with missing credentials). This skips gateway terms check and model
                deck validation. Useful for commands like validate/show that don't call inference
                APIs. Generator selection stays backend-keyed. Submitter-side contract only: it does
                not constrain work this process executes as a Temporal worker.
            boot_orchestrator: When provided, boots this process under the orchestrator plugin
                of this name (e.g. "temporal" to run pipes through the Temporal worker runtime).
                Any other value (or None) leaves execution in-process. Core names no orchestrator;
                the matching plugin gates on its own name.
            needs_model_specs: When True, load real model specs even if needs_inference
                is False. When None (default), follows needs_inference. Useful for validate
                commands that need gateway-provided model specs without enabling full inference.
            class_registry: Custom class registry for dynamic loading
            secrets_provider: Custom secrets/credentials provider
            storage_provider: Custom storage backend
            models_manager: Custom model configuration manager
            inference_manager: Custom inference routing manager
            content_generator: Custom content generation implementation
            pipe_func_executor: Custom PipeFunc execution seam. Defaults to the in-process executor;
                the Temporal worker claims this slot to dispatch PipeFunc runs to a sandbox activity.
            pipeline_manager: Custom pipeline management
            pipe_router: Custom pipe routing logic
            reporting_delegate: Custom reporting handler
            telemetry_config: Custom telemetry configuration
            telemetry_manager: Custom telemetry manager
            observers: Custom observers for pipeline events
            library_dirs: Default library directories for pipeline execution. If provided, these
                directories will be used instead of the PIPELEXPATH environment variable.
                Per-call library_dirs in execute/start will override this default.
            config_dir: Optional explicit config dir. When provided, the **main TOML load** is scoped
                to this directory (package defaults + this directory) instead of following
                project/global layering. Note the limit: it scopes *that load* and nothing else. The
                inference files — backends, routing profiles and the model deck — still resolve through
                the layered paths, and the gateway consent/onboarding state is read from the global
                config dir outright. So this does not fully isolate a boot from the surrounding
                project. See ``wip/boot-split/config-dir-does-not-scope-inference-paths.md``.
            config_overrides: Optional dict deep-merged on top of all TOML config layers
                as the highest-priority override. Useful for tests that need specific
                config without editing TOML files.
            **kwargs: Additional configuration options, only supported by your own subclass of Pipelex if you really need one

        Returns:
            Initialized Pipelex instance.

        Raises:
            PipelexSetupError: If a boot already holds the process globals (a ``Pipelex`` or a bare
                ``RuntimeBoot``), or if setup fails.

        """
        # Before the construction, not left to ``__init__``: a second ``make()`` on an already-registered
        # class never re-runs ``__init__`` (see the guard's docstring). Asked of ``RuntimeBoot``, so a
        # bare runtime boot blocks this one too.
        cls.raise_if_a_boot_already_holds_the_process_globals()

        pipelex_instance = cls(config_dir=config_dir, config_overrides=config_overrides)
        try:
            pipelex_instance.setup(
                integration_mode=integration_mode,
                needs_inference=needs_inference,
                boot_orchestrator=boot_orchestrator,
                needs_model_specs=needs_model_specs,
                class_registry=class_registry,
                secrets_provider=secrets_provider,
                storage_provider=storage_provider,
                models_manager=models_manager,
                inference_manager=inference_manager,
                content_generator=content_generator,
                pipe_func_executor=pipe_func_executor,
                pipeline_manager=pipeline_manager,
                pipe_router=pipe_router,
                reporting_delegate=reporting_delegate,
                telemetry_config=telemetry_config,
                telemetry_manager=telemetry_manager,
                observers=observers,
                library_dirs=library_dirs,
                **kwargs,
            )
            if needs_inference:
                pipelex_instance.models_manager.validate_model_deck()
        except BaseException:
            pipelex_instance._release_after_failed_boot()
            raise
        # Publish readiness only now: setup() AND the optional validate_model_deck() have both succeeded
        # and the delete-on-failure handler above is behind us, so a reader can never adopt an instance
        # that is about to be removed from the registry.
        pipelex_instance.is_ready = True
        log.verbose(f"{PACKAGE_NAME} version {PACKAGE_VERSION} ready")
        return pipelex_instance
