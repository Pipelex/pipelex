import pytest

from pipelex import log
from pipelex.config import get_config
from pipelex.temporal.temporal_hub import get_task_manager


# TODO: improve and check system for all projects using temporal tasks
@pytest.mark.temporal
class TestTasks:
    def test_required_packs(self):
        packs = get_task_manager().task_packs()
        log.verbose(packs, title="Task packs")
        required_packs = get_config().temporal.temporal_config.temporal_tasks_config.required_tasks_packs
        for required_task_pack in required_packs:
            assert required_task_pack in packs, f"Required task pack '{required_task_pack}' not found in packs"

    def test_required_workflows_and_activities(self):
        workflows, activities = get_task_manager().workflows_and_activities_str()
        log.verbose(workflows, title="Workflows")
        log.verbose(activities, title="Activities")
        temporal_tasks_config = get_config().temporal.temporal_config.temporal_tasks_config
        required_workflows = temporal_tasks_config.required_workflows
        required_activities = temporal_tasks_config.required_activities
        for required_workflow in required_workflows:
            assert required_workflow in workflows, f"Required workflow '{required_workflow}' not found in workflows"

        for required_activity in required_activities:
            assert required_activity in activities, f"Required activity '{required_activity}' not found in activities"
