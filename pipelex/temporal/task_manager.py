from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from temporalio.client import Client as TemporalClient
    from temporalio.worker import Worker

    from pipelex.system.configuration.config_temporal import WorkerRuntimeProfile, WorkerScope
    from pipelex.temporal.temporal_tasks import TaskPack
    from pipelex.temporal.temporal_types import ActivityList, ActivityType, WorkflowList, WorkflowType


class TaskManager(Protocol):
    def complement_catalog(
        self,
        extra_catalog: dict[str, TaskPack],
        *,
        extra_workflows: list[WorkflowType],
        extra_activities: list[ActivityType],
    ): ...

    def make_worker(
        self,
        temporal_client: TemporalClient,
        *,
        task_queue: str,
        is_not_sandboxed: bool = False,
        scope: WorkerScope | None = None,
        runtime_profile: WorkerRuntimeProfile | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
    ) -> Worker: ...

    async def run_worker(
        self,
        *,
        is_not_sandboxed: bool,
        is_unit_testing: bool,
        task_queue: str | None = None,
        scope_name: str | None = None,
        profile_name: str | None = None,
    ): ...

    def teardown(self) -> None: ...

    def task_packs(self) -> list[str]: ...

    def workflows_and_activities(
        self,
        scope: WorkerScope | None = None,
        *,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
    ) -> tuple[list[WorkflowType], list[ActivityType]]: ...

    def workflows_and_activities_str(self) -> tuple[list[str], list[str]]: ...
