from pipelex import log
from pipelex.temporal.config_temporal import WorkerScope
from pipelex.temporal.exceptions import TemporalConfigError, WorkerScopeConfigError
from pipelex.temporal.temporal_types import ActivityList, ActivityType, WorkflowList, WorkflowType


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
        *,
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
        *,
        new_workflows: list[WorkflowType],
        new_activities: list[ActivityType],
    ):
        self.tasks_catalog = new_catalog
        self.extra_workflows = new_workflows
        self.extra_activities = new_activities

    def task_packs(self) -> list[str]:
        return list(self.tasks_catalog.keys())

    def _full_catalog(self) -> tuple[dict[str, WorkflowType], dict[str, ActivityType]]:
        all_workflows: dict[str, WorkflowType] = {}
        all_activities: dict[str, ActivityType] = {}
        for pack_name, task_pack in self.tasks_catalog.items():
            source = f"task pack '{pack_name}'"
            for workflow in task_pack.workflow_list:
                self._register_workflow(all_workflows=all_workflows, workflow=workflow, source=source)
            for activity in task_pack.activity_list:
                self._register_activity(all_activities=all_activities, activity=activity, source=source)
        for workflow in self.extra_workflows:
            self._register_workflow(all_workflows=all_workflows, workflow=workflow, source="extra_workflows")
        for activity in self.extra_activities:
            self._register_activity(all_activities=all_activities, activity=activity, source="extra_activities")
        return all_workflows, all_activities

    @classmethod
    def _register_workflow(cls, all_workflows: dict[str, WorkflowType], *, workflow: WorkflowType, source: str) -> None:
        existing = all_workflows.get(workflow.__name__)
        if existing is not None and existing is not workflow:
            msg = (
                f"Workflow name collision: '{workflow.__name__}' is registered as two different callables "
                f"(latest source: {source}). Temporal requires a unique name per workflow."
            )
            raise TemporalConfigError(msg)
        all_workflows[workflow.__name__] = workflow

    @classmethod
    def _register_activity(cls, all_activities: dict[str, ActivityType], *, activity: ActivityType, source: str) -> None:
        existing = all_activities.get(activity.__name__)
        if existing is not None and existing is not activity:
            msg = (
                f"Activity name collision: '{activity.__name__}' is registered as two different callables "
                f"(latest source: {source}). Temporal requires a unique name per activity."
            )
            raise TemporalConfigError(msg)
        all_activities[activity.__name__] = activity

    def workflows_and_activities(
        self,
        scope: WorkerScope | None = None,
        *,
        test_workflows: WorkflowList | None = None,
        test_activities: ActivityList | None = None,
        substitute_activities: dict[ActivityType, ActivityType] | None = None,
    ) -> tuple[list[WorkflowType], list[ActivityType]]:
        all_workflows, all_activities = self._full_catalog()

        the_workflows: set[WorkflowType]
        the_activities: set[ActivityType]
        if scope is None:
            the_workflows = set(all_workflows.values())
            the_activities = set(all_activities.values())
        else:
            the_workflows, the_activities = self._resolve_scope(
                scope=scope,
                all_workflows=all_workflows,
                all_activities=all_activities,
            )

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

    def _resolve_scope(
        self,
        scope: WorkerScope,
        *,
        all_workflows: dict[str, WorkflowType],
        all_activities: dict[str, ActivityType],
    ) -> tuple[set[WorkflowType], set[ActivityType]]:
        known_packs = set(self.tasks_catalog.keys())
        unknown_packs = [pack for pack in scope.required_tasks_packs if pack not in known_packs]
        if unknown_packs:
            msg = f"Unknown task pack(s) in scope: {unknown_packs} (known: {sorted(known_packs)})"
            raise WorkerScopeConfigError(msg)

        unknown_required_workflows = [name for name in scope.required_workflows if name not in all_workflows]
        if unknown_required_workflows:
            msg = f"Unknown workflow(s) in scope.required_workflows: {unknown_required_workflows} (known: {sorted(all_workflows.keys())})"
            raise WorkerScopeConfigError(msg)
        unknown_required_activities = [name for name in scope.required_activities if name not in all_activities]
        if unknown_required_activities:
            msg = f"Unknown activity(ies) in scope.required_activities: {unknown_required_activities} (known: {sorted(all_activities.keys())})"
            raise WorkerScopeConfigError(msg)
        unknown_excluded_workflows = [name for name in scope.excluded_workflows if name not in all_workflows]
        if unknown_excluded_workflows:
            msg = f"Unknown workflow(s) in scope.excluded_workflows: {unknown_excluded_workflows} (known: {sorted(all_workflows.keys())})"
            raise WorkerScopeConfigError(msg)
        unknown_excluded_activities = [name for name in scope.excluded_activities if name not in all_activities]
        if unknown_excluded_activities:
            msg = f"Unknown activity(ies) in scope.excluded_activities: {unknown_excluded_activities} (known: {sorted(all_activities.keys())})"
            raise WorkerScopeConfigError(msg)

        the_workflows: set[WorkflowType] = set()
        the_activities: set[ActivityType] = set()
        for pack_name in scope.required_tasks_packs:
            task_pack = self.tasks_catalog[pack_name]
            the_workflows.update(task_pack.workflow_list)
            the_activities.update(task_pack.activity_list)

        the_workflows.update(all_workflows[name] for name in scope.required_workflows)
        the_activities.update(all_activities[name] for name in scope.required_activities)

        the_workflows.difference_update(all_workflows[name] for name in scope.excluded_workflows)
        the_activities.difference_update(all_activities[name] for name in scope.excluded_activities)

        if scope.disable_all_workflows:
            the_workflows.clear()
        if scope.disable_all_activities:
            the_activities.clear()

        if not the_workflows and not the_activities:
            msg = (
                f"Worker scope resolves to an empty set (packs={scope.required_tasks_packs}, "
                f"required_workflows={scope.required_workflows}, required_activities={scope.required_activities}, "
                f"excluded_workflows={scope.excluded_workflows}, excluded_activities={scope.excluded_activities})"
            )
            raise WorkerScopeConfigError(msg)

        return the_workflows, the_activities

    def workflows_and_activities_str(self) -> tuple[list[str], list[str]]:
        workflows, activities = self.workflows_and_activities(test_workflows=None, test_activities=None)
        return [str(w.__name__) for w in workflows], [str(a.__name__) for a in activities]
