import copy
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

from pydantic import BaseModel, Field

from pipelex.base_exceptions import ErrorReport
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key
from pipelex.cogt.inference.error_classification import RUNTIME_CLASSIFIED_ERROR_CODES
from pipelex.cogt.model_backends.model_type import DEFAULT_MODEL_TYPE
from pipelex.plugins.bundle_validator_registry import BundleValidatorProtocol
from pipelex.plugins.exceptions import (
    DuplicateBundleValidatorError,
    DuplicateDocGenDefaultError,
    DuplicateHttpErrorMapperError,
    DuplicateInferenceBackendError,
    DuplicateInternalModelError,
    DuplicateLogSinkError,
    DuplicateModelListerError,
    DuplicateOrchestratorError,
    DuplicatePipeFuncExecutorError,
    DuplicateSecretsProviderError,
    DuplicateServiceErrorCodeError,
    DuplicateStorageProviderError,
    HubSlotAlreadyClaimedError,
    PluginLayerViolationError,
    ReservedServiceErrorCodeError,
)
from pipelex.plugins.inference_backend_registry import CheckLLMRequestFn, InferenceFamily, LLMRequestCheck, MakeWorkerFn
from pipelex.plugins.log_sink_registry import LogSinkFactoryFn
from pipelex.plugins.model_lister_registry import ListModelsFn
from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
from pipelex.plugins.pipe_func_executor_registry import PipeFuncExecutorFactoryFn
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.plugin_model_declarations import PluginDocGenDefault, PluginInternalModel, PluginModelDeclarations
from pipelex.plugins.secrets_provider_registry import SecretsProviderFactoryFn
from pipelex.plugins.storage_provider_registry import StorageProviderFactoryFn
from pipelex.runtime_bridge.orchestration_mode import OrchestrationMode

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode
    from pipelex.system.configuration.configs import PipelexConfig


_RegistryKeyT = TypeVar("_RegistryKeyT")
_RegistryValueT = TypeVar("_RegistryValueT")

# A plugin's framework-agnostic mapping from one transport/runtime exception to a
# structured ``ErrorReport``. A host runtime (``pipelex-api``) renders the report
# into its own HTTP error response (RFC 7807 + disclosure) — so core and the plugin
# name no web framework.
HttpErrorMapperFn = Callable[[Exception], ErrorReport]

# A thunk returning the concrete exception class a mapper applies to. The mapper is
# registered with this *provider* rather than the bare type so a plugin whose
# exception lives in a heavy orchestrator SDK (``temporalio``) can keep its
# ``register`` import-light: the provider — and any SDK import it performs to name
# the class — is invoked only when a host runtime resolves the mappers via
# ``get_http_error_mappers`` (i.e. at app construction), never at registration.
HttpErrorTypeProviderFn = Callable[[], type[Exception]]


class _HttpErrorMapperContribution(NamedTuple):
    """One plugin's deferred HTTP-error-mapper contribution.

    A ``NamedTuple`` (not a model) because it holds two callables and is never
    serialized. ``exc_type_provider`` is resolved — and any SDK import it incurs
    paid — only by ``get_http_error_mappers``, which is what keeps a contributing
    plugin's ``register`` import-light.
    """

    exc_type_provider: HttpErrorTypeProviderFn
    to_error_report: HttpErrorMapperFn
    source_plugin: str


class HubSlot(StrEnum):
    """A process-global capability slot a boot-orchestrator plugin may claim."""

    CONTENT_GENERATOR = "content_generator"
    PIPE_FUNC_EXECUTOR = "pipe_func_executor"
    PIPE_ROUTER = "pipe_router"
    PIPE_RUN = "pipe_run"
    TASK_MANAGER = "task_manager"
    ISOLATED_EXECUTION_PROBE = "isolated_execution_probe"

    @property
    def is_interpreter_layer(self) -> bool:
        """Whether the claim is applied in ``Pipelex.setup`` rather than in the kernel boot.

        The apply-point is the criterion because it is the one every slot has: a kernel-only boot
        runs the kernel boot and not the interpreter tail, so it can never apply an interpreter
        claim — which is exactly what a kernel-group plugin must not be able to reach.

        For the five slots that hand a value back to core, the returned type corroborates the
        classification — the interpreter ones yield a ``Pipe``-aware object, the kernel ones do not.
        ``TASK_MANAGER`` is why that reading cannot govern on its own: its thunk is invoked for its
        side effects and its return is *discarded*, so there is no handed-back object to classify.
        Its work is kernel-tier all the same — a worker registering only leaf content-generation
        activities names no interpreter type, which is precisely the shape of our Temporal plugin's
        per-backend runner scopes.

        The exhaustive match is the point: a new slot cannot be added without classifying it.
        """
        match self:
            case HubSlot.PIPE_FUNC_EXECUTOR | HubSlot.PIPE_ROUTER | HubSlot.PIPE_RUN:
                return True
            case HubSlot.CONTENT_GENERATOR | HubSlot.TASK_MANAGER | HubSlot.ISOLATED_EXECUTION_PROBE:
                return False


class PluginOrigin(StrEnum):
    BUILTIN = "builtin"
    EXTERNAL = "external"


class PluginStatus(StrEnum):
    REGISTERED = "registered"
    DISABLED = "disabled"
    BROKEN = "broken"

    @property
    def is_registered(self) -> bool:
        return self is PluginStatus.REGISTERED


class PluginDiscovery(BaseModel):
    """Observability record of one discovered plugin and what it contributed.

    Populated by ``build_registrar`` (origin/status/targets_api/group) and the registrar
    menu methods (one ``contributions`` line per contribution). Read by
    ``pipelex plugins list``.
    """

    name: str
    origin: PluginOrigin = Field(strict=False)
    status: PluginStatus = Field(strict=False)
    targets_api: int | None = None
    #: The entry-point group the plugin arrived under, and so the layer it declares. ``None`` for a
    #: built-in: built-ins are handed in as a list, filed by layer in-tree rather than declared.
    group: PluginGroup | None = Field(default=None, strict=False)
    contributions: list[str] = Field(default_factory=list)
    detail: str | None = None


class PluginRegistrar:
    """The accumulator a plugin's ``register`` writes into.

    A plugin only ever calls the menu methods below. ``build_registrar`` drives
    one plugin at a time (setting the "active" discovery so contributions are
    attributed and duplicate conflicts can name both contributors), then boot
    turns the accumulated ``inference_backends`` / ``orchestrators`` into the two
    keyed registries and applies the slot-claim thunks / teardown
    callbacks at their ordered apply-points.

    All duplicate detection is fail-loud and names both contributing plugins.
    """

    def __init__(self, *, config: "PipelexConfig", boot_orchestrator: str | None = None):
        self.config = config
        # The orchestrator plugin this process boots under, or ``None``. A boot argument, not a
        # setting: it arrives from ``build_registrar`` rather than off ``config``, so a plugin's
        # ``register`` gates on ``registrar.boot_orchestrator == self.name``. Defaulted so a focused
        # unit test can build a registrar without naming one.
        self.boot_orchestrator = boot_orchestrator
        self.inference_backends: dict[tuple[InferenceFamily, str], MakeWorkerFn] = {}
        self.llm_request_checks: dict[str, LLMRequestCheck] = {}
        self.model_listers: dict[str, ListModelsFn] = {}
        self.orchestrators: dict[OrchestrationMode, OrchestratorProtocol] = {}
        self.bundle_validators: dict[OrchestrationMode, BundleValidatorProtocol] = {}
        self.storage_providers: dict[str, StorageProviderFactoryFn] = {}
        self.secrets_providers: dict[str, SecretsProviderFactoryFn] = {}
        self.log_sinks: dict[str, LogSinkFactoryFn] = {}
        self.pipe_func_executors: dict[str, PipeFuncExecutorFactoryFn] = {}
        # Plain data, read once by ``make_model_declarations`` for the model manager to merge at boot.
        # Keyed by the model's name and its model type as written, since a handle names one model per model type.
        self.internal_models: dict[tuple[str, str], dict[str, Any]] = {}
        self.doc_gen_defaults: dict[tuple[DocGenFormat, DocGenSource], str] = {}
        self.service_error_codes: dict[str, ServiceErrorCode] = {}
        # Ordered list (not a type-keyed dict) because the exception types are
        # resolved lazily — only ``get_http_error_mappers`` invokes the providers,
        # so duplicate-by-type detection is deferred to resolution time too.
        self.http_error_mappers: list[_HttpErrorMapperContribution] = []
        self.slot_claims: dict[HubSlot, Callable[[], Any]] = {}
        self.teardown_callbacks: list[Callable[[], None]] = []
        self.discoveries: list[PluginDiscovery] = []
        self._inference_sources: dict[tuple[InferenceFamily, str], str] = {}
        self._model_lister_sources: dict[str, str] = {}
        self._orchestrator_sources: dict[OrchestrationMode, str] = {}
        self._bundle_validator_sources: dict[OrchestrationMode, str] = {}
        self._storage_provider_sources: dict[str, str] = {}
        self._secrets_provider_sources: dict[str, str] = {}
        self._log_sink_sources: dict[str, str] = {}
        self._pipe_func_executor_sources: dict[str, str] = {}
        self._internal_model_sources: dict[tuple[str, str], str] = {}
        self._doc_gen_default_sources: dict[tuple[DocGenFormat, DocGenSource], str] = {}
        self._service_error_code_sources: dict[str, str] = {}
        self._slot_sources: dict[HubSlot, str] = {}
        # Reassigned per plugin by build_registrar; the floating default keeps the
        # menu methods safe to call outside a registration loop (e.g. a focused unit test).
        self._active = PluginDiscovery(name="(unregistered)", origin=PluginOrigin.BUILTIN, status=PluginStatus.REGISTERED)

    # ------------------------------------------------------------------ #
    # Driven by build_registrar (not by plugins)
    # ------------------------------------------------------------------ #

    def begin_plugin(self, *, name: str, origin: PluginOrigin, targets_api: int, group: PluginGroup | None) -> PluginDiscovery:
        discovery = PluginDiscovery(name=name, origin=origin, status=PluginStatus.REGISTERED, targets_api=targets_api, group=group)
        self.discoveries.append(discovery)
        self._active = discovery
        return discovery

    # ------------------------------------------------------------------ #
    # Menu methods — the only surface a plugin's register() may call
    # ------------------------------------------------------------------ #

    def add_inference_backend(
        self,
        *,
        family: InferenceFamily,
        sdk: str,
        make_worker: MakeWorkerFn,
        check_llm_request: CheckLLMRequestFn | None = None,
    ) -> None:
        """Register the worker factory serving one sdk of one inference family.

        ``check_llm_request`` is read for the LLM family only: the check the worker ``make_worker`` builds
        applies to a request before calling its provider, which bundle validation runs against the model a
        pipe's setting resolves to (see ``CheckLLMRequestFn``). The check is recorded with the registering
        plugin's origin, which decides how its refusals are shown to a caller. A duplicate backend is refused
        before its check is recorded, so a refused duplicate leaves no check behind.
        """
        self._add(
            store=self.inference_backends,
            sources=self._inference_sources,
            key=(family, sdk),
            value=make_worker,
            contribution=f"inference backend {family}:{sdk}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateInferenceBackendError(
                family=family, sdk=sdk, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )
        match family:
            case InferenceFamily.LLM:
                if check_llm_request is not None:
                    self.llm_request_checks[sdk] = LLMRequestCheck(check=check_llm_request, is_builtin=self._active.origin == PluginOrigin.BUILTIN)
            case InferenceFamily.IMG_GEN | InferenceFamily.EXTRACT | InferenceFamily.SEARCH | InferenceFamily.DOC_GEN | InferenceFamily.JUDGMENT:
                pass

    def add_model_lister(self, *, sdk: str, lister: ListModelsFn) -> None:
        self._add(
            store=self.model_listers,
            sources=self._model_lister_sources,
            key=sdk,
            value=lister,
            contribution=f"model lister {sdk}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateModelListerError(
                sdk=sdk, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_orchestrator(self, *, mode: OrchestrationMode, orchestrator: OrchestratorProtocol) -> None:
        self._require_interpreter_layer(capability=f"orchestrator {mode}")
        self._add(
            store=self.orchestrators,
            sources=self._orchestrator_sources,
            key=mode,
            value=orchestrator,
            contribution=f"orchestrator {mode}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateOrchestratorError(
                mode=mode, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_bundle_validator(self, *, mode: OrchestrationMode, validator: BundleValidatorProtocol) -> None:
        self._require_interpreter_layer(capability=f"bundle validator {mode}")
        self._add(
            store=self.bundle_validators,
            sources=self._bundle_validator_sources,
            key=mode,
            value=validator,
            contribution=f"bundle validator {mode}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateBundleValidatorError(
                mode=mode, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_storage_provider(self, *, method: str, factory: StorageProviderFactoryFn) -> None:
        """Contribute a factory for one storage backend, keyed by an open ``method`` token.

        The built-in ``StoragePlugin`` registers the ``local`` / ``in_memory`` / ``s3`` / ``gcp``
        methods; an external ``pipelex-storage-<backend>`` plugin registers its own token (e.g.
        ``"azure"``). Boot reads ``runtime.storage.method`` and calls the looked-up factory to
        produce the one storage provider set on the hub. ``factory`` is invoked at that boot
        apply-point, never here — so a factory may do heavy work (SDK import, a hub secrets read)
        while ``register`` stays import-light. Fail-loud on a duplicate method, naming both plugins.
        """
        self._add(
            store=self.storage_providers,
            sources=self._storage_provider_sources,
            key=method,
            value=factory,
            contribution=f"storage provider {method}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateStorageProviderError(
                method=method, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_secrets_provider(self, *, method: str, factory: SecretsProviderFactoryFn) -> None:
        """Contribute a factory for one secrets backend, keyed by an open ``method`` token.

        The built-in ``SecretsPlugin`` registers the ``env`` method; an external
        ``pipelex-secrets-<backend>`` plugin registers its own token (e.g. ``"vault"``). Boot reads
        ``runtime.secrets.method`` and calls the looked-up factory to produce the one secrets provider
        set on the hub. ``factory`` is invoked at that boot apply-point, never here — so a factory may
        do heavy work (SDK import) while ``register`` stays import-light. Fail-loud on a duplicate
        method, naming both plugins.
        """
        self._add(
            store=self.secrets_providers,
            sources=self._secrets_provider_sources,
            key=method,
            value=factory,
            contribution=f"secrets provider {method}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateSecretsProviderError(
                method=method, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_log_sink(self, *, method: str, factory: LogSinkFactoryFn) -> None:
        """Contribute a factory for one log sink, keyed by an open ``method`` token.

        The built-in ``LogSinkPlugin`` registers the ``json`` / ``console`` / ``otlp`` methods; an
        external plugin registers its own token (e.g. ``"gcp"``). Boot reads ``runtime.log.sink`` and
        calls the looked-up factory to produce the one sink whose handler goes on the root logger.
        ``factory`` is invoked at that boot apply-point, never here, and the sink builds its handler
        later still, at install — so a factory or a sink may import a heavy SDK (Rich, the OpenTelemetry
        logs SDK) while ``register`` stays import-light. Fail-loud on a duplicate method, naming both plugins.
        """
        self._add(
            store=self.log_sinks,
            sources=self._log_sink_sources,
            key=method,
            value=factory,
            contribution=f"log sink {method}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateLogSinkError(
                method=method, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_internal_model(self, *, name: str, spec: Mapping[str, Any]) -> None:
        """Declare one model of the internal backend, the software-only backend that runs inside Pipelex.

        ``spec`` is exactly the table a backend file would hold for the model (``model_type``, ``sdk``, ``model_id``,
        ``inputs``, ``outputs``, ``costs``…), and it is complete on its own: no backend file's ``[defaults]`` table
        is applied to it. A plugin that ships an engine declares its model here rather than leaving it to the kit's
        ``internal.toml``, and registers the engine's worker with ``add_inference_backend`` for the same sdk.

        Plain data, so it is stored and nothing else: the model manager validates the table when it merges it into
        the internal backend at boot, and refuses one whose name and model type the installation's ``internal.toml``
        already declares. A handle names one model per model type, so a model is identified by its name and by its
        ``model_type`` as written, the default type when the table sets none. Fail-loud on a model another plugin
        declared, naming both plugins.
        """
        model_type = str(spec.get("model_type", DEFAULT_MODEL_TYPE))
        self._add(
            store=self.internal_models,
            sources=self._internal_model_sources,
            key=(name, model_type),
            value=copy.deepcopy(dict(spec)),
            contribution=f"internal model {name} ({model_type})",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateInternalModelError(
                name=name, model_type=model_type, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_doc_gen_default(self, *, doc_gen_format: DocGenFormat, source: DocGenSource, model: str) -> None:
        """Declare the model deck's default document engine for one format and source, such as an ``xlsx`` from the auto-layout.

        ``model`` names the engine a ``PipeDocGen`` step prints with when it names none: a model name, or any model
        reference the deck resolves. The default sits beneath the deck files, so a deck file that sets the same
        format and source, a user's ``x_custom_*.toml`` included, overrides it. Stored and nothing else: the model
        manager checks that a step composes this format from this source when it merges the default at boot.
        Fail-loud on a format and source another plugin declared, naming both plugins.
        """
        key = (doc_gen_format, source)
        self._add(
            store=self.doc_gen_defaults,
            sources=self._doc_gen_default_sources,
            key=key,
            value=model,
            contribution=f"doc_gen default {doc_gen_choice_key(doc_gen_format=doc_gen_format, source=source)} = {model}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicateDocGenDefaultError(
                choice_key=doc_gen_choice_key(doc_gen_format=doc_gen_format, source=source),
                first_plugin=first_plugin,
                second_plugin=second_plugin,
            ),
        )

    def add_service_error_codes(self, *, codes: "Iterable[ServiceErrorCode]") -> None:
        """Contribute the error codes a service this plugin speaks to emits on its own, and what each one means.

        For a plugin whose backend is a gateway or a hosted service that refuses some requests itself,
        before any provider sees them, under codes of its own. Boot freezes every contribution into the
        hub's `ServiceErrorVocabulary`, which `classify_inference_error` consults ahead of the status
        ladder: a contributed code decides the error's category, its action and its advice, whatever the
        status it arrived on. Plain data, stored and nothing else. Fail-loud on a code another plugin
        contributed, naming both plugins, and on a code the runtime classifies itself.
        """
        contributed: list[str] = []
        for service_error_code in codes:
            code = service_error_code.code
            if code in RUNTIME_CLASSIFIED_ERROR_CODES:
                raise ReservedServiceErrorCodeError(code=code, plugin=self._active.name)
            if code in self.service_error_codes:
                raise DuplicateServiceErrorCodeError(code=code, first_plugin=self._service_error_code_sources[code], second_plugin=self._active.name)
            self.service_error_codes[code] = service_error_code
            self._service_error_code_sources[code] = self._active.name
            contributed.append(code)
        if contributed:
            self._active.contributions.append(f"service error codes {', '.join(contributed)}")

    def add_pipe_func_executor(self, *, mode: str, factory: PipeFuncExecutorFactoryFn) -> None:
        """Contribute a factory for one PipeFunc execution mode, keyed by an open ``mode`` token.

        The built-in ``PipeFuncPlugin`` registers ``direct`` (in-process); an external sandbox plugin
        (e.g. our Daytona plugin) registers its own token
        (e.g. ``"daytona"``). Boot reads ``interpreter.pipe_func.execution_mode`` and calls the looked-up
        factory to produce the one PipeFunc executor set on the hub. ``factory`` is invoked at that boot
        apply-point, never here — so a factory may do heavy work (SDK import, config self-load) while
        ``register`` stays import-light. This is the PipeFunc-execution axis, orthogonal to the
        orchestration axis. Fail-loud on a duplicate mode, naming both plugins.
        """
        self._require_interpreter_layer(capability=f"pipe_func executor {mode}")
        self._add(
            store=self.pipe_func_executors,
            sources=self._pipe_func_executor_sources,
            key=mode,
            value=factory,
            contribution=f"pipe_func executor {mode}",
            on_duplicate=lambda first_plugin, second_plugin: DuplicatePipeFuncExecutorError(
                mode=mode, first_plugin=first_plugin, second_plugin=second_plugin
            ),
        )

    def add_http_error_mapper(self, *, exc_type_provider: HttpErrorTypeProviderFn, to_error_report: HttpErrorMapperFn) -> None:
        """Contribute a mapping from a transport/runtime exception to a structured ``ErrorReport``.

        ``exc_type_provider`` is a thunk returning the concrete exception class the
        mapper applies to. It is resolved *lazily* by ``get_http_error_mappers`` (at a
        host runtime's app-construction time), never here — which is what keeps a
        plugin's ``register`` import-light: a plugin whose exception type lives in a
        heavy orchestrator SDK (``temporalio``) passes ``lambda: TemporalError`` and the
        SDK import is deferred until a host runtime actually consumes the mappers. The
        ``to_error_report`` closure is likewise uninvoked until an error is rendered.

        A host runtime (``pipelex-api``) iterates the resolved mappers at app
        construction and wraps each into one framework error handler (FastAPI, …) using
        its own RFC 7807 + disclosure rendering — so core and the plugin name no web
        framework. Duplicate-by-type detection is deferred to ``get_http_error_mappers``
        (the providers must run first); it stays fail-loud and names both plugins.
        """
        self.http_error_mappers.append(
            _HttpErrorMapperContribution(exc_type_provider=exc_type_provider, to_error_report=to_error_report, source_plugin=self._active.name)
        )
        self._active.contributions.append("http error mapper")

    def claim_content_generator(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.CONTENT_GENERATOR, factory=factory)

    def claim_pipe_func_executor(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_FUNC_EXECUTOR, factory=factory)

    def claim_pipe_router(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_ROUTER, factory=factory)

    def claim_pipe_run(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.PIPE_RUN, factory=factory)

    def claim_task_manager(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.TASK_MANAGER, factory=factory)

    def claim_isolated_execution_probe(self, factory: Callable[[], Any]) -> None:
        self._claim(slot=HubSlot.ISOLATED_EXECUTION_PROBE, factory=factory)

    def add_teardown(self, callback: Callable[[], None]) -> None:
        self.teardown_callbacks.append(callback)
        self._active.contributions.append("teardown callback")

    # ------------------------------------------------------------------ #
    # Read accessors (for host runtimes consuming plugin contributions)
    # ------------------------------------------------------------------ #

    @property
    def registered_plugin_names(self) -> set[str]:
        """Names of plugins that discovered and registered successfully.

        The authoritative namespace the ``boot_orchestrator`` gate matches against: a
        boot-orchestrator plugin claims its hub slots iff ``boot_orchestrator == its own name``.
        Disabled/broken discoveries are excluded — they never run ``register`` and so never claim a
        slot, making them invalid boot-orchestrator targets.
        """
        return {discovery.name for discovery in self.discoveries if discovery.status.is_registered}

    def make_model_declarations(self) -> PluginModelDeclarations:
        """Freeze the internal models and model deck defaults the plugins declared, for ``ModelManagerAbstract.setup``.

        A fresh value object with deep copies of the tables, so neither the model manager nor a plugin holding on to
        the mapping it passed, or a list inside it, can change what the registrar recorded.
        """
        internal_models = tuple(
            PluginInternalModel(name=name, spec=copy.deepcopy(spec), plugin=self._internal_model_sources[name, model_type])
            for (name, model_type), spec in self.internal_models.items()
        )
        doc_gen_defaults = tuple(
            PluginDocGenDefault(
                doc_gen_format=doc_gen_format, source=source, model=model, plugin=self._doc_gen_default_sources[doc_gen_format, source]
            )
            for (doc_gen_format, source), model in self.doc_gen_defaults.items()
        )
        return PluginModelDeclarations(internal_models=internal_models, doc_gen_defaults=doc_gen_defaults)

    def get_http_error_mappers(self) -> dict[type[Exception], HttpErrorMapperFn]:
        """Resolve every contributed exc-type provider into a ``{exc_type: mapper}`` dict.

        The read view a host runtime (``pipelex-api``) iterates at app construction to
        register one framework error handler per exception type. Resolving the
        providers *here* (never at registration) is what lets a contributing plugin's
        ``register`` stay import-light: any orchestrator-SDK import a provider performs
        to name its concrete exception class is deferred to this call — which a host
        runtime makes only when it actually has the plugin (and therefore the SDK)
        installed, so the import always resolves. A freshly built dict, so a consumer
        cannot mutate the registrar's state. Fail-loud naming both plugins when two map
        the same resolved exception type.
        """
        resolved: dict[type[Exception], HttpErrorMapperFn] = {}
        sources: dict[type[Exception], str] = {}
        for contribution in self.http_error_mappers:
            exc_type = contribution.exc_type_provider()
            if exc_type in resolved:
                raise DuplicateHttpErrorMapperError(
                    exc_type=exc_type.__qualname__, first_plugin=sources[exc_type], second_plugin=contribution.source_plugin
                )
            resolved[exc_type] = contribution.to_error_report
            sources[exc_type] = contribution.source_plugin
        return resolved

    # ------------------------------------------------------------------ #

    def _add(
        self,
        *,
        store: dict[_RegistryKeyT, _RegistryValueT],
        sources: dict[_RegistryKeyT, str],
        key: _RegistryKeyT,
        value: _RegistryValueT,
        contribution: str,
        on_duplicate: Callable[[str, str], Exception],
    ) -> None:
        """Shared body for the keyed registration menu methods (mirrors ``_claim`` for the slot menu).

        Fail-loud duplicate detection, store, source attribution, and contribution
        recording in one place; each ``add_*`` method supplies its keyed store, the
        parallel sources dict, and a factory that builds its distinctly-typed
        ``Duplicate*Error`` naming both contributing plugins.
        """
        if key in store:
            raise on_duplicate(sources[key], self._active.name)
        store[key] = value
        sources[key] = self._active.name
        self._active.contributions.append(contribution)

    def _require_interpreter_layer(self, *, capability: str) -> None:
        """Reject an interpreter-layer contribution from a plugin that published itself as kernel-layer.

        One-directional by design: an interpreter-group plugin may contribute kernel-tier
        capabilities alongside its interpreter-tier ones — ours registers an orchestrator
        (interpreter-tier, guarded here) *and* an HTTP-error mapper (kernel-tier, not) — and nothing
        is at risk there because a kernel-only boot never reads that group. Built-ins declare no
        group and are skipped: they are filed by layer in-tree, where the hub-layering guard polices
        them statically.
        """
        group = self._active.group
        if group is not None and group.is_kernel:
            raise PluginLayerViolationError(
                plugin_name=self._active.name,
                capability=capability,
                declared_group=group,
                interpreter_group=PluginGroup.INTERPRETER,
            )

    def _claim(self, *, slot: HubSlot, factory: Callable[[], Any]) -> None:
        if slot.is_interpreter_layer:
            self._require_interpreter_layer(capability=f"hub slot {slot}")
        if slot in self.slot_claims:
            raise HubSlotAlreadyClaimedError(slot=slot, first_plugin=self._slot_sources[slot], second_plugin=self._active.name)
        self.slot_claims[slot] = factory
        self._slot_sources[slot] = self._active.name
        self._active.contributions.append(f"hub slot {slot}")
