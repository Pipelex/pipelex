from datetime import timedelta
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from temporalio.common import RetryPolicy

from pipelex import log
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.temporal.exceptions import TemporalConfigError
from pipelex.tools.storage.storage_config import StorageProviderConfig
from pipelex.types import Self, StrEnum


class SecretMethod(StrEnum):
    NONE = "none"
    ENV_VAR = "env_var"
    SECRET_PROVIDER = "secret_provider"


class TemporalServerConfig(ConfigModel):
    """Configuration model for Temporal server settings."""

    description: str
    target_host: str
    namespace: str
    api_key_method: SecretMethod = Field(strict=False)
    api_key_id: str

    @property
    def full_description(self) -> str:
        """Generate a full description of the Temporal server configuration.

        Returns:
            str: A detailed description including non-default target host and namespace.
        """
        desc = self.description
        if self.target_host != "localhost:7233":
            desc += f", target host: {self.target_host}"
        if self.namespace != "default":
            desc += f", namespace: {self.namespace}"
        return desc


class TemporalLogConfig(ConfigModel):
    """Configuration model for Temporal logging settings."""

    is_workflow_info_on_message: bool
    is_workflow_info_on_extra: bool
    is_full_workflow_info_on_extra: bool
    is_activity_info_on_message: bool
    is_activity_info_on_extra: bool
    is_full_activity_info_on_extra: bool
    is_formatter_enabled: bool
    is_prefix_enabled: bool
    managed_loggers: list[str]
    is_dispatch_resolution_traced: bool


class WorkerScope(ConfigModel):
    """Defines the subset of workflows and activities a worker registers.

    Resolution order: pack contents → required_* additions → excluded_* subtractions →
    disable_all_* clearing. Names match TaskPack keys, workflow class __name__, and
    activity function __name__.

    `disable_all_workflows` / `disable_all_activities` are useful to split workflow-only
    and activity-only workers on the same task queue (Temporal SDK rejects multiple
    workers with overlapping task types on the same queue).
    """

    required_tasks_packs: list[str]
    required_workflows: list[str]
    required_activities: list[str]
    excluded_workflows: list[str]
    excluded_activities: list[str]
    disable_all_workflows: bool
    disable_all_activities: bool


class WorkerScopesConfig(ConfigModel):
    """Named worker scopes selectable via --scope on the worker CLI."""

    default_scope: str
    scopes: dict[str, WorkerScope]

    @model_validator(mode="after")
    def validate_default_scope(self) -> Self:
        if self.default_scope not in self.scopes:
            msg = f"default_scope '{self.default_scope}' not found in scopes (known: {sorted(self.scopes.keys())})"
            raise TemporalConfigError(msg)
        return self


class TemporalConfig(ConfigModel):
    """Configuration model for overall Temporal settings."""

    temporal_server_configs: dict[str, TemporalServerConfig]
    selected_server: str
    temporal_log_config: TemporalLogConfig

    @model_validator(mode="after")
    def validate_selected_server(self) -> Self:
        """Validate that the selected server exists in the server configurations.

        Raises:
            TemporalConfigError: If the selected server is not found in the configurations.

        Returns:
            Self: The validated instance.
        """
        if self.selected_server not in self.temporal_server_configs:
            msg = f"Selected server '{self.selected_server}' not found in temporal_server_configs"
            raise TemporalConfigError(msg)
        return self


class RetryPolicyConfig(ConfigModel):
    """Configuration model for retry policy settings."""

    initial_interval: timedelta = Field(strict=False)
    backoff_coefficient: float
    maximum_interval: Union[timedelta, Literal["unlimited"]]
    maximum_attempts: Union[int, Literal["unlimited"]]
    non_retryable_error_types: list[str] = Field(default_factory=list)
    # Additive list contributed by per-queue and per-handle overlays. The merged
    # set is built at dispatch time (Phase 2 resolver) — never substituted.
    non_retryable_error_types_extra: list[str] = Field(default_factory=list)

    def make_retry_policy(self, merged_non_retryable_types: list[str] | None = None) -> RetryPolicy:
        """Create a RetryPolicy instance based on the configuration.

        Args:
            merged_non_retryable_types: When provided, used as the policy's
                ``non_retryable_error_types``. Callers building a final retry
                policy after additive composition across baseline/queue/handle
                layers pass this list. When ``None``, the policy uses this
                config's own ``non_retryable_error_types`` (baseline-only).

        Returns:
            RetryPolicy: A configured RetryPolicy object.
        """
        maximum_attempts: int
        if self.maximum_attempts == "unlimited":
            # This is according to the Temporal SDK's documentation
            maximum_attempts = 0
        else:
            maximum_attempts = self.maximum_attempts

        maximum_interval: timedelta | None
        # this test is in two steps because timedelta's are actually read from the config as strings
        if isinstance(self.maximum_interval, str) and self.maximum_interval == "unlimited":
            maximum_interval = None
        else:
            maximum_interval = self.maximum_interval

        non_retryable = merged_non_retryable_types if merged_non_retryable_types is not None else self.non_retryable_error_types

        return RetryPolicy(
            initial_interval=self.initial_interval,
            backoff_coefficient=self.backoff_coefficient,
            maximum_interval=maximum_interval,
            maximum_attempts=maximum_attempts,
            non_retryable_error_types=non_retryable,
        )


class QueueOptions(ConfigModel):
    """Per-queue submitter options + queue-level rate limit.

    Resolution order at dispatch (for timeouts and retry):
      per-handle override (handle_options.<handle>) →
      this (queue_options[resolved_queue]) →
      worker_config defaults.

    Note: ``heartbeat_timeout`` lives here (queue scope) because heartbeat cadence
    is a property of the backend on the other side of the queue. It is NOT on
    ``HandleOptions``. If a single model on a backend ever needs a different
    cadence, add the field to ``HandleOptions`` then — schema change is one line.
    """

    start_to_close_timeout: timedelta | None = Field(default=None, strict=False)
    schedule_to_close_timeout: timedelta | None = Field(default=None, strict=False)
    schedule_to_start_timeout: timedelta | None = Field(default=None, strict=False)
    heartbeat_timeout: timedelta | None = Field(default=None, strict=False)
    retry_policy_config: RetryPolicyConfig | None = None
    # Cluster-wide queue rate limit, conveyed to the Temporal server by every
    # worker on this queue. The latest value to be sent by a worker wins.
    max_task_queue_activities_per_second: float | None = None

    @model_validator(mode="after")
    def reject_baseline_non_retryable_on_overlay(self) -> Self:
        """Overlay layers MUST contribute non-retryable types via
        ``non_retryable_error_types_extra``, not ``non_retryable_error_types``.

        The baseline list lives on ``worker_config.retry_policy_config`` and is
        always included in the additive composition. If a user sets
        ``non_retryable_error_types = [...]`` on a queue-level overlay, the
        resolver would silently ignore it (the dispatch path only reads
        ``_extra`` from overlay layers). Fail loudly instead so the user
        switches to the correct field name.
        """
        if self.retry_policy_config is not None and self.retry_policy_config.non_retryable_error_types:
            msg = (
                "queue_options retry_policy_config: 'non_retryable_error_types' is not allowed on overlay layers. "
                "Use 'non_retryable_error_types_extra' instead — the dispatch resolver composes layers additively "
                "on top of the worker_config baseline."
            )
            raise TemporalConfigError(msg)
        return self


class HandleOptions(ConfigModel):
    """Per-handle option overrides. Layers on top of QueueOptions for the resolved queue.

    Deliberately narrow: only timeout and retry. Heartbeat is queue-level.
    Other fields will be added on demand when a real case surfaces.
    """

    start_to_close_timeout: timedelta | None = Field(default=None, strict=False)
    retry_policy_config: RetryPolicyConfig | None = None

    @model_validator(mode="after")
    def reject_baseline_non_retryable_on_overlay(self) -> Self:
        """Same invariant as ``QueueOptions``: overlays contribute via
        ``non_retryable_error_types_extra`` so the additive composition rule
        is unambiguous from the config alone.
        """
        if self.retry_policy_config is not None and self.retry_policy_config.non_retryable_error_types:
            msg = (
                "handle_options retry_policy_config: 'non_retryable_error_types' is not allowed on overlay layers. "
                "Use 'non_retryable_error_types_extra' instead — the dispatch resolver composes layers additively "
                "on top of the worker_config baseline."
            )
            raise TemporalConfigError(msg)
        return self


# class PipelexWorkflowsConfig(ConfigModel):
#     """Configuration model for workflow settings."""

#     jinja2_activity_timeout: timedelta = Field(strict=False)
#     jinja2_retry_policy_config: RetryPolicyConfig

#     @property
#     def jinja2_retry_policy(self) -> RetryPolicy:
#         """
#         Create a RetryPolicy for LLM generation based on the configuration.

#         Returns:
#             RetryPolicy: A configured RetryPolicy object for LLM generation.
#         """
#         return self.jinja2_retry_policy_config.make_retry_policy()


class ActivityRouteConfig(ConfigModel):
    """Per-activity routing entry.

    Args:
        default: The task queue used when no per-handle override matches.
        by_handle: Mapping from runtime handle (e.g. ``llm_handle``,
            ``img_gen_handle``, ``extract_handle``) to a dedicated task queue.
        handle_options: Rare per-handle option overrides for a single handle
            that needs different timeout/retry from its queue baseline (e.g.
            a long-context model variant). Layered on top of the resolved
            ``QueueOptions`` at dispatch time.
    """

    default: str
    by_handle: dict[str, str] = Field(default_factory=dict)
    handle_options: dict[str, HandleOptions] = Field(default_factory=dict)


class WorkerTuningMode(StrEnum):
    """How a worker scales its slot counts.

    Only EXPLICIT is implemented in v2. RESOURCE_BASED is reserved for a future
    iteration (Temporal SDK's ``WorkerTuner.create_resource_based``). Defined now
    so the profile schema doesn't break when we add it.
    """

    EXPLICIT = "explicit"
    RESOURCE_BASED = "resource_based"


class WorkerRuntimeProfile(ConfigModel):
    """Bundle of ``Worker(...)`` constructor tuning. One worker process selects one profile.

    ``tuning_mode`` MUST be ``"explicit"`` in v2. A model_validator rejects
    ``"resource_based"`` with a clear "not implemented yet" message until the
    follow-up iteration ships the resource-based path.
    """

    tuning_mode: WorkerTuningMode = Field(strict=False)
    max_cached_workflows: int
    max_concurrent_workflow_tasks: int
    max_concurrent_activities: int
    max_concurrent_local_activities: int
    max_concurrent_workflow_task_polls: int
    max_concurrent_activity_task_polls: int
    max_activities_per_second: float
    sticky_queue_schedule_to_start_timeout: timedelta = Field(strict=False)
    max_heartbeat_throttle_interval: timedelta = Field(strict=False)
    default_heartbeat_throttle_interval: timedelta = Field(strict=False)
    graceful_shutdown_timeout: timedelta = Field(strict=False)

    @model_validator(mode="after")
    def reject_unimplemented_tuning_mode(self) -> Self:
        match self.tuning_mode:
            case WorkerTuningMode.EXPLICIT:
                return self
            case WorkerTuningMode.RESOURCE_BASED:
                msg = "tuning_mode='resource_based' is reserved but not implemented in v2; use 'explicit'."
                raise TemporalConfigError(msg)


class WorkerRuntimeProfilesConfig(ConfigModel):
    """Named worker-runtime profiles selectable via ``--profile`` on the worker CLI."""

    default_profile: str
    profiles: dict[str, WorkerRuntimeProfile]

    @model_validator(mode="after")
    def validate_default_profile(self) -> Self:
        if self.default_profile not in self.profiles:
            msg = f"default_profile '{self.default_profile}' not in profiles (known: {sorted(self.profiles.keys())})"
            raise TemporalConfigError(msg)
        return self


class DispatchOptions(BaseModel):
    """Resolved per-call dispatch bundle returned by ``WorkerConfig.resolve_dispatch``.

    Splat ``to_execute_kwargs()`` into ``workflow.execute_activity(...)`` to
    set queue + timeouts + retry consistently. Optional timeouts are omitted
    from the kwargs dict when unset so the Temporal SDK applies its own
    defaults (rather than ``None``, which the SDK rejects).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_queue: str
    start_to_close_timeout: timedelta
    schedule_to_close_timeout: timedelta | None = None
    schedule_to_start_timeout: timedelta | None = None
    heartbeat_timeout: timedelta | None = None
    retry_policy: RetryPolicy

    def to_execute_kwargs(self) -> dict[str, Any]:
        """Return a kwargs dict to splat into ``workflow.execute_activity``."""
        kwargs: dict[str, Any] = {
            "task_queue": self.task_queue,
            "start_to_close_timeout": self.start_to_close_timeout,
            "retry_policy": self.retry_policy,
        }
        if self.schedule_to_close_timeout is not None:
            kwargs["schedule_to_close_timeout"] = self.schedule_to_close_timeout
        if self.schedule_to_start_timeout is not None:
            kwargs["schedule_to_start_timeout"] = self.schedule_to_start_timeout
        if self.heartbeat_timeout is not None:
            kwargs["heartbeat_timeout"] = self.heartbeat_timeout
        return kwargs


class WorkerConfig(ConfigModel):
    """Submitter-side defaults plus the worker's home queue.

    ``default_task_queue`` is the fallback used by ``resolve_queue`` when no
    ``activity_queues`` entry matches. ``default_activity_start_to_close_timeout``
    is the baseline activity timeout used when no per-queue or per-handle
    overlay applies (Phase 2 resolver).
    """

    default_task_queue: str
    activity_queues: dict[str, ActivityRouteConfig]
    workflow_execution_timeout: timedelta = Field(strict=False)
    run_timeout: timedelta | None = Field(default=None, strict=False)
    task_timeout: timedelta | None = Field(default=None, strict=False)
    start_delay: timedelta | None = Field(default=None, strict=False)
    rpc_timeout: timedelta | None = Field(default=None, strict=False)
    default_activity_start_to_close_timeout: timedelta = Field(strict=False)
    default_activity_heartbeat_timeout: timedelta | None = Field(default=None, strict=False)
    retry_policy_config: RetryPolicyConfig

    @property
    def retry_policy(self) -> "RetryPolicy":
        """Create a baseline RetryPolicy from the worker config.

        Returns:
            RetryPolicy: A configured RetryPolicy object built from the baseline.
        """
        return self.retry_policy_config.make_retry_policy()

    def resolve_queue(self, activity_name: str, routing_key: str | None = None) -> str:
        """Resolve which task queue an activity should dispatch to.

        Thin delegate to ``resolve_dispatch(...).task_queue`` so the v1 resolver
        keeps working for any caller that only needs the queue name.

        Args:
            activity_name: The Temporal activity ``__name__`` (e.g. ``"act_llm_gen_text"``).
            routing_key: Optional per-activity handle (model handle, img-gen
                handle, extract handle). Activities without a meaningful
                routing dimension pass ``None``.

        Returns:
            The task queue name. Resolution order:
              1. ``activity_queues[activity_name].by_handle[routing_key]``
              2. ``activity_queues[activity_name].default``
              3. ``self.default_task_queue`` (worker-wide default)
        """
        activity_route = self.activity_queues.get(activity_name)
        if activity_route is None:
            return self.default_task_queue
        if routing_key is not None:
            per_handle = activity_route.by_handle.get(routing_key)
            if per_handle is not None:
                return per_handle
        return activity_route.default

    def resolve_dispatch(
        self,
        activity_name: str,
        routing_key: str | None = None,
        queue_options_by_queue: dict[str, "QueueOptions"] | None = None,
        is_traced: bool = False,
    ) -> DispatchOptions:
        """Resolve the full per-call dispatch bundle for an activity.

        Layers, last-wins for scalars (None means "no contribution"):
          1. worker_config baseline (``default_activity_start_to_close_timeout``,
             ``default_activity_heartbeat_timeout``, ``retry_policy_config``).
          2. ``queue_options[resolved_queue]`` if present.
          3. ``activity_queues[activity_name].handle_options[routing_key]`` if present.

        ``non_retryable_error_types`` composes **additively** across all three
        layers (baseline list + queue ``_extra`` + handle ``_extra``) — never
        substituted. This is a safety lean: per-queue layers can add to the
        no-retry list but not remove from it.

        Args:
            activity_name: The Temporal activity ``__name__``.
            routing_key: Optional per-activity handle.
            queue_options_by_queue: The full ``queue_options`` map (from
                ``Temporal.queue_options``). Explicit dependency rather than a
                ``get_config()`` reach so this method stays unit-testable.
            is_traced: When true, emit one INFO log line per call with the
                resolved queue + timeout + retry attempts and the layer each
                scalar came from (baseline / queue_options / handle_options).
                Off by default — verbose; turn on when debugging mis-tuned
                timeouts.

        Returns:
            A ``DispatchOptions`` ready to be splatted into
            ``workflow.execute_activity(...)``.
        """
        resolved_queue = self.resolve_queue(activity_name=activity_name, routing_key=routing_key)

        queue_opts: QueueOptions | None = None
        if queue_options_by_queue is not None:
            queue_opts = queue_options_by_queue.get(resolved_queue)

        handle_opts: HandleOptions | None = None
        activity_route = self.activity_queues.get(activity_name)
        if activity_route is not None and routing_key is not None:
            handle_opts = activity_route.handle_options.get(routing_key)

        start_to_close = self.default_activity_start_to_close_timeout
        start_to_close_source = "baseline"
        schedule_to_close: timedelta | None = None
        schedule_to_start: timedelta | None = None
        heartbeat: timedelta | None = self.default_activity_heartbeat_timeout

        if queue_opts is not None:
            if queue_opts.start_to_close_timeout is not None:
                start_to_close = queue_opts.start_to_close_timeout
                start_to_close_source = "queue_options"
            if queue_opts.schedule_to_close_timeout is not None:
                schedule_to_close = queue_opts.schedule_to_close_timeout
            if queue_opts.schedule_to_start_timeout is not None:
                schedule_to_start = queue_opts.schedule_to_start_timeout
            if queue_opts.heartbeat_timeout is not None:
                heartbeat = queue_opts.heartbeat_timeout

        if handle_opts is not None and handle_opts.start_to_close_timeout is not None:
            start_to_close = handle_opts.start_to_close_timeout
            start_to_close_source = "handle_options"

        # Pick the deepest retry policy config to seed the build (intervals,
        # backoff, attempts come from the most-specific layer). Then compose
        # non_retryable_error_types additively across all three layers.
        retry_base: RetryPolicyConfig = self.retry_policy_config
        retry_source = "baseline"
        if queue_opts is not None and queue_opts.retry_policy_config is not None:
            retry_base = queue_opts.retry_policy_config
            retry_source = "queue_options"
        if handle_opts is not None and handle_opts.retry_policy_config is not None:
            retry_base = handle_opts.retry_policy_config
            retry_source = "handle_options"

        merged_non_retryable: list[str] = list(self.retry_policy_config.non_retryable_error_types)
        if queue_opts is not None and queue_opts.retry_policy_config is not None:
            merged_non_retryable.extend(queue_opts.retry_policy_config.non_retryable_error_types_extra)
        if handle_opts is not None and handle_opts.retry_policy_config is not None:
            merged_non_retryable.extend(handle_opts.retry_policy_config.non_retryable_error_types_extra)
        # Dedupe while preserving order so the resulting list is deterministic
        # and small even when layers overlap.
        seen: set[str] = set()
        deduped_non_retryable: list[str] = []
        for error_type in merged_non_retryable:
            if error_type not in seen:
                seen.add(error_type)
                deduped_non_retryable.append(error_type)

        retry_policy = retry_base.make_retry_policy(merged_non_retryable_types=deduped_non_retryable)

        if is_traced:
            log.info(
                f"temporal.dispatch act={activity_name} handle={routing_key} "
                f"-> queue={resolved_queue} "
                f"timeout={start_to_close.total_seconds()}s (from={start_to_close_source}) "
                f"retry_attempts={retry_base.maximum_attempts} (from={retry_source})"
            )

        return DispatchOptions(
            task_queue=resolved_queue,
            start_to_close_timeout=start_to_close,
            schedule_to_close_timeout=schedule_to_close,
            schedule_to_start_timeout=schedule_to_start,
            heartbeat_timeout=heartbeat,
            retry_policy=retry_policy,
        )


class PayloadCodecConfig(ConfigModel):
    """Configuration for the storage-based payload codec that offloads large payloads."""

    is_enabled: bool
    size_threshold: int
    storage_prefix: str
    storage_provider_config: StorageProviderConfig


class Temporal(ConfigModel):
    """Main configuration model for Temporal."""

    is_enabled: bool
    temporal_config: TemporalConfig
    worker_config: WorkerConfig
    queue_options: dict[str, QueueOptions]
    worker_runtime_profiles: WorkerRuntimeProfilesConfig
    worker_scopes: WorkerScopesConfig
    payload_codec_config: PayloadCodecConfig

    @model_validator(mode="after")
    def warn_on_unknown_routing_queues(self) -> Self:
        """Warn when ``activity_queues`` names a queue that has no matching
        ``queue_options`` entry and isn't the worker's ``default_task_queue``.

        Lenient on purpose: a queue riding the worker_config baselines is a
        legitimate state (small deployments don't need per-queue tuning).
        But the message is loud enough that typos surface in CI / on first
        boot. Strict failure happens at worker CLI startup (separate path).
        """
        known_queues = set(self.queue_options.keys())
        known_queues.add(self.worker_config.default_task_queue)
        for activity_name, route in self.worker_config.activity_queues.items():
            if route.default not in known_queues:
                log.warning(
                    f"temporal: queue {route.default!r} referenced by "
                    f"activity_queues.{activity_name}.default has no queue_options entry — "
                    f"it will use worker_config defaults. Typo?"
                )
            for handle, handle_queue in route.by_handle.items():
                if handle_queue not in known_queues:
                    log.warning(
                        f"temporal: queue {handle_queue!r} referenced by "
                        f'activity_queues.{activity_name}.by_handle["{handle}"] has no '
                        f"queue_options entry — it will use worker_config defaults. Typo?"
                    )
        return self
