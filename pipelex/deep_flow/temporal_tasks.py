from pipelex import log
from pipelex.deep_flow.temporal_types import ActivityList, ActivityType, WorkflowList, WorkflowType


class TaskPack:
    def __init__(self, workflow_list: WorkflowList, activity_list: ActivityList):
        self.workflow_list = workflow_list
        self.activity_list = activity_list


class TemporalTasks:
    def __init__(self):
        self.tasks_catalog: dict[str, TaskPack] = {}
        self.extra_workflows: list[WorkflowType] = []
        self.extra_activities: list[ActivityType] = []

    def complement_catalog(
        self,
        extra_catalog: dict[str, TaskPack],
        extra_workflows: list[WorkflowType],
        extra_activities: list[ActivityType],
    ):
        log.verbose(extra_catalog, title="Complementing catalog with extra_catalog")
        for pack_name, task_pack in extra_catalog.items():
            if pack_name in self.tasks_catalog:
                msg = f"Task pack with the same name '{pack_name}' already exists, no merging or overriding allowed for task packs"
                raise RuntimeError(msg)
            self.tasks_catalog[pack_name] = task_pack

        log.verbose(extra_workflows, title="Complementing catalog with extra_workflows")
        self.extra_workflows = list(set(self.extra_workflows + extra_workflows))
        log.verbose(extra_activities, title="Complementing catalog with extra_activities")
        self.extra_activities = list(set(self.extra_activities + extra_activities))

    def replace_catalog(
        self,
        new_catalog: dict[str, TaskPack],
        new_workflows: list[WorkflowType],
        new_activities: list[ActivityType],
    ):
        self.tasks_catalog = new_catalog
        self.extra_workflows = new_workflows
        self.extra_activities = new_activities

    def task_packs(self) -> list[str]:
        return list(self.tasks_catalog.keys())

    def workflows_and_activities(
        self,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
    ) -> tuple[list[WorkflowType], list[ActivityType]]:
        # aggregating lists from all task packs first as sets to remove duplicates
        the_workflows: set[WorkflowType] = set()
        the_activities: set[ActivityType] = set()
        for task_pack in self.tasks_catalog.values():
            the_workflows.update(task_pack.workflow_list)
            the_activities.update(task_pack.activity_list)
        # adding extra workflows and activities
        the_workflows.update(self.extra_workflows)
        the_activities.update(self.extra_activities)
        # adding test workflows and activities
        if test_workflows:
            the_workflows.update(test_workflows)
        if test_activities:
            the_activities.update(test_activities)
        if substitute_activities:
            for old_activity, new_activity in substitute_activities.items():
                if old_activity in the_activities:
                    the_activities.remove(old_activity)
                    the_activities.add(new_activity)
        return list(the_workflows), list(the_activities)

    def workflows_and_activities_str(self) -> tuple[list[str], list[str]]:
        workflows, activities = self.workflows_and_activities(test_workflows=None, test_activities=None)
        return [str(w.__name__) for w in workflows], [str(a.__name__) for a in activities]
