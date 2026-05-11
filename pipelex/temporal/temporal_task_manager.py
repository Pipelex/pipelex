import asyncio

from temporalio import workflow
from temporalio.client import Client as TemporalClient
from temporalio.worker import UnsandboxedWorkflowRunner, Worker, WorkflowRunner
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.hub import get_class_registry
from pipelex.system.runtime import WorkerMode, runtime_manager
from pipelex.temporal.config_temporal import WorkerRuntimeProfile, WorkerScope
from pipelex.temporal.exceptions import WorkerProfileConfigError, WorkerScopeConfigError
from pipelex.temporal.log_temporal import configure_temporal_logs
from pipelex.temporal.sandbox_manager import sandbox_manager
from pipelex.temporal.task_manager import TaskManager
from pipelex.temporal.temporal_connect import connect_to_temporal
from pipelex.temporal.temporal_manager import TemporalManager
from pipelex.temporal.temporal_registry_models import TemporalRegistryModels
from pipelex.temporal.temporal_tasks import TaskPack, TemporalTasks
from pipelex.temporal.temporal_types import (
    ActivityList,
    ActivityType,
    WorkflowList,
    WorkflowType,
)
from pipelex.temporal.test_extras.temporal_registry_test_models import TemporalTestModels
from pipelex.temporal.tprl.namespace_check import check_required_search_attributes


def is_in_temporal_sandbox() -> bool:
    """Check if we're in a Temporal workflow sandbox.

    Returns:
        bool: True if in a workflow sandbox, False otherwise.
    """
    return workflow.unsafe.in_sandbox()


class TemporalTaskManager(TaskManager):
    def __init__(self):
        self.temporal_tasks = self.__class__.create_temporal_tasks()

    @classmethod
    def create_temporal_tasks(cls) -> TemporalTasks:
        return TemporalTasks()

    def setup(self):
        get_class_registry().register_classes(TemporalRegistryModels.get_all_models())
        if runtime_manager.is_unit_testing:
            log.debug("Registering test models for unit testing")
            get_class_registry().register_classes(TemporalTestModels.get_all_models())
        configure_temporal_logs()
        # TODO: use direct tweaking of settings in Pipelex to apply the sandbox restrictions to loggers etc.
        sandbox_manager.set_sandbox_callable(sandbox_callable=is_in_temporal_sandbox)
        TemporalManager.setup(session_id=get_config().session_id)
        log.info("TemporalTaskManager setup done")

    def teardown(self):
        TemporalManager.teardown()
        log.info("TemporalTaskManager teardown done")

    @override
    def complement_catalog(
        self,
        extra_catalog: dict[str, TaskPack],
        extra_workflows: list[WorkflowType],
        extra_activities: list[ActivityType],
    ):
        self.temporal_tasks.complement_catalog(
            extra_catalog=extra_catalog,
            extra_workflows=extra_workflows,
            extra_activities=extra_activities,
        )

    @override
    def make_worker(
        self,
        temporal_client: TemporalClient,
        task_queue: str,
        is_not_sandboxed: bool = False,
        scope: WorkerScope | None = None,
        runtime_profile: WorkerRuntimeProfile | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
    ) -> Worker:
        workflows, activities = self.temporal_tasks.workflows_and_activities(
            scope=scope,
            test_activities=test_activities,
            test_workflows=test_workflows,
            substitute_activities=substitute_activities,
        )
        workflow_runner: WorkflowRunner
        if is_not_sandboxed:
            workflow_runner = UnsandboxedWorkflowRunner()
        else:
            workflow_runner = SandboxedWorkflowRunner(
                restrictions=SandboxRestrictions.default.with_passthrough_modules(
                    "pydantic",
                    "pydantic.root_model",
                    "bson",
                    "pymongo",
                    "networkx",
                    "google.auth",
                    "google.cloud.logging",
                    "cogt.oai.azure_openai_config",
                    "pipelex.tools.log.log",
                    "pipelex.tools.log.log_config",
                    "pipelex.tools.log.log_dispatch",
                    "pipelex.tools.environment",
                    "citadel.mdb.models",
                    "citadel.mdb.connector",
                    "citadel.gcp.gsecret_helpers",
                )
            )

        # Resolve to the default profile when the caller does not specify one.
        # Most internal/test call sites don't care about profile tuning and want
        # the default knobs; the worker CLI path always passes an explicit profile.
        profile = runtime_profile or self._resolve_runtime_profile_by_name(profile_name=None)

        # Queue-level cluster-wide rate cap is attached to the queue, not the
        # profile. Every worker on this queue sends it; the server enforces it.
        queue_options = get_config().temporal.queue_options.get(task_queue)
        max_task_queue_activities_per_second = queue_options.max_task_queue_activities_per_second if queue_options is not None else None

        return Worker(
            temporal_client,
            task_queue=task_queue,
            workflows=workflows,
            activities=activities,
            workflow_runner=workflow_runner,
            max_cached_workflows=profile.max_cached_workflows,
            max_concurrent_workflow_tasks=profile.max_concurrent_workflow_tasks,
            max_concurrent_activities=profile.max_concurrent_activities,
            max_concurrent_local_activities=profile.max_concurrent_local_activities,
            max_concurrent_workflow_task_polls=profile.max_concurrent_workflow_task_polls,
            max_concurrent_activity_task_polls=profile.max_concurrent_activity_task_polls,
            sticky_queue_schedule_to_start_timeout=profile.sticky_queue_schedule_to_start_timeout,
            max_heartbeat_throttle_interval=profile.max_heartbeat_throttle_interval,
            default_heartbeat_throttle_interval=profile.default_heartbeat_throttle_interval,
            graceful_shutdown_timeout=profile.graceful_shutdown_timeout,
            max_activities_per_second=profile.max_activities_per_second,
            max_task_queue_activities_per_second=max_task_queue_activities_per_second,
        )

    @override
    async def run_worker(
        self,
        is_not_sandboxed: bool,
        is_unit_testing: bool,
        task_queue: str | None = None,
        scope_name: str | None = None,
        profile_name: str | None = None,
    ):
        try:
            test_workflows: WorkflowList | None = None
            test_activities: ActivityList | None = None
            if is_unit_testing:
                log.debug(f"is_unit_testing={is_unit_testing} Registering test models")
                runtime_manager.set_worker_mode(worker_mode=WorkerMode.UNIT_TEST)
                from pipelex.temporal.test_extras.temporal_test_tasks import (  # noqa: PLC0415
                    TEMPORAL_TEST_ACTIVITIES,
                    TEMPORAL_TEST_WORKFLOWS,
                )

                test_workflows = TEMPORAL_TEST_WORKFLOWS
                test_activities = TEMPORAL_TEST_ACTIVITIES
            else:
                log.debug(f"is_unit_testing={is_unit_testing} Setting worker mode to NORMAL")
                runtime_manager.set_worker_mode(worker_mode=WorkerMode.NORMAL)
            temporal_client = await connect_to_temporal()
            worker_config = get_config().temporal.worker_config
            task_queue = task_queue or worker_config.default_task_queue
            # Strict check also runs at the worker CLI startup; repeated here
            # so programmatic callers of ``run_worker`` (tests, library code)
            # also fast-fail on typos rather than polling an idle queue.
            get_config().temporal.validate_task_queue_known(task_queue)
            # One-shot soft-fail check that the namespace has the required
            # custom search attributes registered. Warns only — dev environments
            # without registration still run; only the dashboard is degraded.
            await check_required_search_attributes(
                temporal_client=temporal_client,
                namespace=temporal_client.namespace,
            )
            scope = self._resolve_scope_by_name(scope_name=scope_name)
            runtime_profile = self._resolve_runtime_profile_by_name(profile_name=profile_name)
            effective_scope_name = scope_name or get_config().temporal.worker_scopes.default_scope
            effective_profile_name = profile_name or get_config().temporal.worker_runtime_profiles.default_profile
            log.info(f"Temporal Worker starting: profile='{effective_profile_name}' scope='{effective_scope_name}' task_queue='{task_queue}'")
            async with self.make_worker(
                temporal_client=temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=is_not_sandboxed,
                scope=scope,
                runtime_profile=runtime_profile,
                test_workflows=test_workflows,
                test_activities=test_activities,
            ):
                log.info(f"Temporal Worker started for '{task_queue}'")
                if is_not_sandboxed:
                    log.warning("Worker is running without sandbox")
                await asyncio.Event().wait()
        except asyncio.CancelledError:
            log.info("Main coroutine was cancelled.")
        finally:
            log.info("Shutting down")

    @staticmethod
    def _resolve_scope_by_name(scope_name: str | None) -> WorkerScope:
        worker_scopes = get_config().temporal.worker_scopes
        effective_name = scope_name or worker_scopes.default_scope
        if effective_name not in worker_scopes.scopes:
            msg = f"Unknown worker scope '{effective_name}' (known: {sorted(worker_scopes.scopes.keys())})"
            raise WorkerScopeConfigError(msg)
        return worker_scopes.scopes[effective_name]

    @staticmethod
    def _resolve_runtime_profile_by_name(profile_name: str | None) -> WorkerRuntimeProfile:
        profiles_config = get_config().temporal.worker_runtime_profiles
        effective_name = profile_name or profiles_config.default_profile
        if effective_name not in profiles_config.profiles:
            msg = f"Unknown worker runtime profile '{effective_name}' (known: {sorted(profiles_config.profiles.keys())})"
            raise WorkerProfileConfigError(msg)
        return profiles_config.profiles[effective_name]

    @override
    def task_packs(self) -> list[str]:
        return self.temporal_tasks.task_packs()

    @override
    def workflows_and_activities(
        self,
        scope: WorkerScope | None = None,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
    ) -> tuple[list[WorkflowType], list[ActivityType]]:
        return self.temporal_tasks.workflows_and_activities(
            scope=scope,
            test_workflows=test_workflows,
            test_activities=test_activities,
            substitute_activities=substitute_activities,
        )

    @override
    def workflows_and_activities_str(self) -> tuple[list[str], list[str]]:
        return self.temporal_tasks.workflows_and_activities_str()
