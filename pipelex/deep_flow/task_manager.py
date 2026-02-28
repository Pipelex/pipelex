from typing import Protocol

from deep_flow.temporal_tasks import TaskPack
from deep_flow.temporal_types import ActivityList, ActivityType, WorkflowList, WorkflowType
from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker


class TaskManager(Protocol):
    def complement_catalog(
        self,
        extra_catalog: dict[str, TaskPack],
        extra_workflows: list[WorkflowType],
        extra_activities: list[ActivityType],
    ): ...

    def make_worker(
        self,
        temporal_client: TemporalClient,
        task_queue: str,
        is_not_sandboxed: bool = False,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
    ) -> Worker: ...

    async def run_worker(self, is_not_sandboxed: bool, is_unit_testing: bool, task_queue: str | None = None): ...

    def task_packs(self) -> list[str]: ...

    def workflows_and_activities(
        self,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
    ) -> tuple[list[WorkflowType], list[ActivityType]]: ...

    def worklows_and_activities_str(self) -> tuple[list[str], list[str]]: ...
