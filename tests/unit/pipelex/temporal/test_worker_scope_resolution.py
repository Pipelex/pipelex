from typing import Any

import pytest

from pipelex.system.configuration.config_temporal import WorkerScope
from pipelex.temporal.exceptions import WorkerScopeConfigError
from pipelex.temporal.temporal_tasks import TaskPack, TemporalTasks


class _WfAlpha:
    pass


class _WfBeta:
    pass


class _WfGamma:
    pass


def _act_one(_payload: Any) -> Any:
    return _payload


def _act_two(_payload: Any) -> Any:
    return _payload


def _act_three(_payload: Any) -> Any:
    return _payload


def _make_tasks() -> TemporalTasks:
    tasks = TemporalTasks()
    tasks.complement_catalog(
        extra_catalog={
            "pack_one": TaskPack(workflow_list=[_WfAlpha, _WfBeta], activity_list=[_act_one, _act_two]),
            "pack_two": TaskPack(workflow_list=[_WfGamma], activity_list=[_act_three]),
        },
        extra_workflows=[],
        extra_activities=[],
    )
    return tasks


def _scope(
    required_tasks_packs: list[str] | None = None,
    required_workflows: list[str] | None = None,
    required_activities: list[str] | None = None,
    excluded_workflows: list[str] | None = None,
    excluded_activities: list[str] | None = None,
    disable_all_workflows: bool = False,
    disable_all_activities: bool = False,
) -> WorkerScope:
    return WorkerScope(
        required_tasks_packs=required_tasks_packs or [],
        required_workflows=required_workflows or [],
        required_activities=required_activities or [],
        excluded_workflows=excluded_workflows or [],
        excluded_activities=excluded_activities or [],
        disable_all_workflows=disable_all_workflows,
        disable_all_activities=disable_all_activities,
    )


class TestWorkerScopeResolution:
    def test_no_scope_returns_full_catalog(self):
        tasks = _make_tasks()
        workflows, activities = tasks.workflows_and_activities()
        assert set(workflows) == {_WfAlpha, _WfBeta, _WfGamma}
        assert set(activities) == {_act_one, _act_two, _act_three}

    def test_pack_only_scope(self):
        tasks = _make_tasks()
        workflows, activities = tasks.workflows_and_activities(scope=_scope(required_tasks_packs=["pack_one"]))
        assert set(workflows) == {_WfAlpha, _WfBeta}
        assert set(activities) == {_act_one, _act_two}

    def test_required_workflows_and_activities_only(self):
        tasks = _make_tasks()
        workflows, activities = tasks.workflows_and_activities(
            scope=_scope(required_workflows=["_WfGamma"], required_activities=["_act_three"]),
        )
        assert set(workflows) == {_WfGamma}
        assert set(activities) == {_act_three}

    def test_pack_plus_required(self):
        tasks = _make_tasks()
        workflows, activities = tasks.workflows_and_activities(
            scope=_scope(required_tasks_packs=["pack_one"], required_workflows=["_WfGamma"]),
        )
        assert set(workflows) == {_WfAlpha, _WfBeta, _WfGamma}
        assert set(activities) == {_act_one, _act_two}

    def test_exclusions_apply_after_inclusions(self):
        tasks = _make_tasks()
        workflows, activities = tasks.workflows_and_activities(
            scope=_scope(
                required_tasks_packs=["pack_one", "pack_two"],
                excluded_workflows=["_WfBeta"],
                excluded_activities=["_act_one"],
            ),
        )
        assert set(workflows) == {_WfAlpha, _WfGamma}
        assert set(activities) == {_act_two, _act_three}

    def test_unknown_pack_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="Unknown task pack"):
            tasks.workflows_and_activities(scope=_scope(required_tasks_packs=["pack_missing"]))

    def test_unknown_required_workflow_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="required_workflows"):
            tasks.workflows_and_activities(scope=_scope(required_workflows=["WfUnknown"]))

    def test_unknown_required_activity_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="required_activities"):
            tasks.workflows_and_activities(scope=_scope(required_activities=["act_unknown"]))

    def test_unknown_excluded_workflow_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="excluded_workflows"):
            tasks.workflows_and_activities(
                scope=_scope(required_tasks_packs=["pack_one"], excluded_workflows=["WfUnknown"]),
            )

    def test_unknown_excluded_activity_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="excluded_activities"):
            tasks.workflows_and_activities(
                scope=_scope(required_tasks_packs=["pack_one"], excluded_activities=["act_unknown"]),
            )

    def test_empty_resolved_scope_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="empty set"):
            tasks.workflows_and_activities(scope=_scope())

    def test_full_excluded_to_empty_raises(self):
        tasks = _make_tasks()
        with pytest.raises(WorkerScopeConfigError, match="empty set"):
            tasks.workflows_and_activities(
                scope=_scope(
                    required_tasks_packs=["pack_one", "pack_two"],
                    excluded_workflows=["_WfAlpha", "_WfBeta", "_WfGamma"],
                    excluded_activities=["_act_one", "_act_two", "_act_three"],
                ),
            )
