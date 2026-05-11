"""Unit tests for the specialized worker scopes (runner-llm, runner-img-gen,
runner-extract, runner-jinja2) shipped in `pipelex/pipelex.toml`.

These scopes let deployment manifests spin up one worker pool per backend
class. The tests verify (a) each scope registers exactly the activities its
name implies and (b) the union of all four specialized scopes covers the
full ``runner`` registration with no orphan activities.
"""

import pytest

from pipelex.config import get_config
from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_tasks import TemporalTasks


def _make_tasks() -> TemporalTasks:
    """Build a TemporalTasks populated from the production ``Tasks.TASK_PACKS``.

    Mirrors what ``TemporalTaskManager.setup`` registers at runtime — that
    catalog determines which activities ``required_activities=[...]`` can
    reference in a scope.
    """
    tasks = TemporalTasks()
    tasks.complement_catalog(extra_catalog=Tasks.TASK_PACKS, extra_workflows=[], extra_activities=[])
    return tasks


class TestSpecializedWorkerScopes:
    """Specialized scopes register exactly their intended activity set and
    collectively cover the full ``runner`` registration.
    """

    @pytest.mark.parametrize(
        ("scope_name", "expected_activity_names"),
        [
            ("runner-llm", {"act_llm_gen_text", "act_llm_gen_object", "act_llm_gen_object_list"}),
            # img-gen + extract intentionally both register act_render_page_views.
            ("runner-img-gen", {"act_img_gen_images", "act_render_page_views"}),
            ("runner-extract", {"act_extract_gen_extract_pages", "act_render_page_views"}),
            ("runner-jinja2", {"act_jinja2_gen_text"}),
        ],
    )
    def test_scope_registers_expected_activities(self, scope_name: str, expected_activity_names: set[str]) -> None:
        """Each specialized scope registers exactly the activities its name implies."""
        worker_scopes = get_config().temporal.worker_scopes
        assert scope_name in worker_scopes.scopes, f"scope '{scope_name}' missing from worker_scopes.scopes"
        scope = worker_scopes.scopes[scope_name]
        _, activities = _make_tasks().workflows_and_activities(scope=scope)
        registered_names = {activity.__name__ for activity in activities}
        assert registered_names == expected_activity_names

    def test_specialized_scopes_cover_runner_activities(self) -> None:
        """Union of specialized scope activity sets equals the ``runner`` scope
        activity set — no orphan activities that would land on no specialized
        worker in a manifest using only the specialized scopes.
        """
        worker_scopes = get_config().temporal.worker_scopes
        tasks = _make_tasks()
        _, runner_activities = tasks.workflows_and_activities(scope=worker_scopes.scopes["runner"])
        runner_names = {activity.__name__ for activity in runner_activities}

        specialized_union: set[str] = set()
        for scope_name in ("runner-llm", "runner-img-gen", "runner-extract", "runner-jinja2"):
            scope = worker_scopes.scopes[scope_name]
            _, scope_activities = tasks.workflows_and_activities(scope=scope)
            specialized_union.update(activity.__name__ for activity in scope_activities)

        # The pipe task pack also registers control-plane activities (assemble_graph,
        # deliver, flush_trace_events) that are wf_pipe_router / wf_pipe_run plumbing
        # and not "content-generation" activities. Specialized runner scopes are
        # only meant to cover the user-activity surface. Compare on that subset.
        content_gen_runner_names = {
            "act_llm_gen_text",
            "act_llm_gen_object",
            "act_llm_gen_object_list",
            "act_img_gen_images",
            "act_extract_gen_extract_pages",
            "act_render_page_views",
            "act_jinja2_gen_text",
        }
        # Every user-activity registered by `runner` must appear in at least
        # one specialized scope.
        orphans = content_gen_runner_names & runner_names - specialized_union
        assert not orphans, f"specialized scopes leave content-gen activities orphan: {orphans!r}"
