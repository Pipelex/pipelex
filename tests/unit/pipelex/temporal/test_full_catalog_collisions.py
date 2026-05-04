from typing import Any

import pytest

from pipelex.temporal.exceptions import TemporalConfigError
from pipelex.temporal.temporal_tasks import TaskPack, TemporalTasks
from pipelex.temporal.temporal_types import ActivityType, WorkflowType


def _make_workflow(name: str) -> WorkflowType:
    return type(name, (), {})


def _make_activity(name: str) -> ActivityType:
    def _impl(payload: Any) -> Any:
        return payload

    _impl.__name__ = name
    return _impl


class TestFullCatalogCollisions:
    def test_same_workflow_callable_in_multiple_packs_dedups(self):
        workflow = _make_workflow("WfShared")
        activity = _make_activity("act_shared")
        tasks = TemporalTasks()
        tasks.complement_catalog(
            extra_catalog={
                "pack_one": TaskPack(workflow_list=[workflow], activity_list=[activity]),
                "pack_two": TaskPack(workflow_list=[workflow], activity_list=[activity]),
            },
            extra_workflows=[],
            extra_activities=[],
        )

        workflows, activities = tasks.workflows_and_activities()

        assert workflows == [workflow]
        assert activities == [activity]

    def test_same_callable_in_pack_and_extras_dedups(self):
        workflow = _make_workflow("WfShared")
        activity = _make_activity("act_shared")
        tasks = TemporalTasks()
        tasks.complement_catalog(
            extra_catalog={
                "pack_one": TaskPack(workflow_list=[workflow], activity_list=[activity]),
            },
            extra_workflows=[workflow],
            extra_activities=[activity],
        )

        workflows, activities = tasks.workflows_and_activities()

        assert workflows == [workflow]
        assert activities == [activity]

    def test_distinct_workflows_with_same_name_across_packs_raises(self):
        workflow_one = _make_workflow("WfClash")
        workflow_two = _make_workflow("WfClash")
        assert workflow_one is not workflow_two

        tasks = TemporalTasks()
        tasks.complement_catalog(
            extra_catalog={
                "pack_one": TaskPack(workflow_list=[workflow_one], activity_list=[]),
                "pack_two": TaskPack(workflow_list=[workflow_two], activity_list=[]),
            },
            extra_workflows=[],
            extra_activities=[],
        )

        with pytest.raises(TemporalConfigError, match="Workflow name collision: 'WfClash'") as exc_info:
            tasks.workflows_and_activities()
        assert "task pack 'pack_two'" in str(exc_info.value)

    def test_distinct_workflows_with_same_name_pack_and_extras_raises(self):
        workflow_in_pack = _make_workflow("WfClash")
        workflow_in_extras = _make_workflow("WfClash")

        tasks = TemporalTasks()
        tasks.complement_catalog(
            extra_catalog={
                "pack_one": TaskPack(workflow_list=[workflow_in_pack], activity_list=[]),
            },
            extra_workflows=[workflow_in_extras],
            extra_activities=[],
        )

        with pytest.raises(TemporalConfigError, match="Workflow name collision: 'WfClash'") as exc_info:
            tasks.workflows_and_activities()
        assert "extra_workflows" in str(exc_info.value)

    def test_distinct_activities_with_same_name_across_packs_raises(self):
        activity_one = _make_activity("act_clash")
        activity_two = _make_activity("act_clash")
        assert activity_one is not activity_two

        tasks = TemporalTasks()
        tasks.complement_catalog(
            extra_catalog={
                "pack_one": TaskPack(workflow_list=[], activity_list=[activity_one]),
                "pack_two": TaskPack(workflow_list=[], activity_list=[activity_two]),
            },
            extra_workflows=[],
            extra_activities=[],
        )

        with pytest.raises(TemporalConfigError, match="Activity name collision: 'act_clash'") as exc_info:
            tasks.workflows_and_activities()
        assert "task pack 'pack_two'" in str(exc_info.value)

    def test_distinct_activities_with_same_name_pack_and_extras_raises(self):
        activity_in_pack = _make_activity("act_clash")
        activity_in_extras = _make_activity("act_clash")

        tasks = TemporalTasks()
        tasks.complement_catalog(
            extra_catalog={
                "pack_one": TaskPack(workflow_list=[], activity_list=[activity_in_pack]),
            },
            extra_workflows=[],
            extra_activities=[activity_in_extras],
        )

        with pytest.raises(TemporalConfigError, match="Activity name collision: 'act_clash'") as exc_info:
            tasks.workflows_and_activities()
        assert "extra_activities" in str(exc_info.value)
