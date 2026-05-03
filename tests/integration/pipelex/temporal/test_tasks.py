import pytest

from pipelex import log
from pipelex.config import get_config
from pipelex.temporal.temporal_hub import get_task_manager


@pytest.mark.temporal
class TestTasks:
    def test_default_scope_is_known(self):
        worker_scopes = get_config().temporal.worker_scopes
        assert worker_scopes.default_scope in worker_scopes.scopes

    def test_full_scope_packs_present(self):
        packs = get_task_manager().task_packs()
        log.verbose(packs, title="Task packs")
        full_scope = get_config().temporal.worker_scopes.scopes["full"]
        for required_task_pack in full_scope.required_tasks_packs:
            assert required_task_pack in packs, f"Required task pack '{required_task_pack}' not found in packs"

    def test_router_and_runner_names_resolve(self):
        workflows, activities = get_task_manager().workflows_and_activities_str()
        log.verbose(workflows, title="Workflows")
        log.verbose(activities, title="Activities")
        for scope_name in ("router", "runner"):
            scope = get_config().temporal.worker_scopes.scopes[scope_name]
            for required_workflow in scope.required_workflows:
                assert required_workflow in workflows, f"Required workflow '{required_workflow}' not found in workflows"
            for required_activity in scope.required_activities:
                assert required_activity in activities, f"Required activity '{required_activity}' not found in activities"
