"""Cross-process regression guard for ``ContentGeneratorInWorkflow.make_extract_pages``.

The two-activity branch of ``make_extract_pages`` is the only
``ContentGeneratorProtocol`` method that dispatches more than one activity in
a single call (``act_extract_gen_extract_pages`` then conditionally
``act_render_page_views``), and therefore the only one whose ``activity_id``
uniqueness mitigation (``f"{base_id}-pages"`` and
``f"{base_id}-render-page-views"``) materially affects production. This suite
mirrors ``content_generation/test_tprl_content_generator_pdf_page_views.py``
but pins the activity_id contract via ``WorkflowHandle.fetch_history()``.

Substitute activities return canonical fixtures so the test does not require
Azure Document Intelligence credentials or the real PDF renderer — the goal
is to validate the cross-process activity dispatch and the activity_id
contract, not the OCR backend itself (already covered by the in-process test).

Note on "split worker": single-worker setup is sufficient for the activity
dispatch contract — Temporal still serializes/deserializes activity payloads
across the activity boundary even when the same Python process hosts both
the workflow and the activities. A true cross-process upgrade is now
possible via ``worker_config.activity_queues`` (per-activity routing shipped
in v1; see ``wip/temporal-primitives/per-activity-queue-routing-v1.md``
§"Tests to upgrade when v1 lands"): route the extract activities to a
runner queue and register the substitutes only on that queue. Tracked as a
follow-up — this file is the primary caller of that upgrade.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.assignment_models import ExtractAssignment, RenderPageViewsAssignment
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.test_extras.temporal_test_tasks import TEMPORAL_TEST_WORKFLOWS
from pipelex.temporal.test_extras.wf_test_content_generator_pdf_page_views import WfTestContentGeneratorPdfPageViews
from pipelex.temporal.tprl_content_generation.act_extract_generate import act_extract_gen_extract_pages
from pipelex.temporal.tprl_content_generation.act_render_page_views import act_render_page_views
from tests.integration.pipelex.temporal.tracing.helpers import route_activities_to

_PAGE_VIEW_URLS = ("test://page-view-0.png", "test://page-view-1.png")


def _make_canonical_page_contents() -> list[PageContent]:
    return [PageContent(text_and_images=TextAndImagesContent(text=None, images=None)) for _ in _PAGE_VIEW_URLS]


def _make_canonical_page_views() -> list[ImageContent]:
    return [ImageContent(url=url) for url in _PAGE_VIEW_URLS]


@activity.defn(name="act_extract_gen_extract_pages")
async def _stub_act_extract_gen_extract_pages(_extract_assignment: ExtractAssignment) -> list[PageContent]:  # noqa: RUF029
    """Substitute returning two canonical pages so the in-workflow attachment
    loop has a deterministic length to pair with ``act_render_page_views``.
    """
    return _make_canonical_page_contents()


@activity.defn(name="act_render_page_views")
async def _stub_act_render_page_views(_render_assignment: RenderPageViewsAssignment) -> list[ImageContent]:  # noqa: RUF029
    return _make_canonical_page_views()


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerExtractPages:
    """Submit ``WfTestContentGeneratorPdfPageViews`` and pin the activity_id
    contract via workflow history.

    The fixture workflow exercises the two-activity branch
    (``document_uri`` + ``should_include_page_views=True``). Substitutes return
    canonical 2-page outputs so the in-workflow attachment loop succeeds; the
    test then inspects history to confirm Temporal scheduled both activities
    with the expected ``f"{base_id}-pages"`` / ``f"{base_id}-render-page-views"``
    activity_ids.
    """

    @pytest.mark.timeout(60)
    async def test_two_activity_branch_dispatches_with_distinct_activity_ids(
        self,
        temporal_client: TemporalClient,
    ) -> None:
        """Both ``act_extract_gen_extract_pages`` and ``act_render_page_views``
        must appear in workflow history with the activity_ids constructed by
        ``make_extract_pages`` (``"extract-pages"`` / ``"extract-render-page-views"``
        when no ``wfid`` is passed at the call site).
        """
        task_queue = f"q_extract_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_extract_{uuid.uuid4().hex[:8]}"

        # Route the substituted extract activities to this test's UUID queue
        # so the in-workflow dispatcher (which now passes ``task_queue=resolved``
        # for every activity) lands them on the worker registered here.
        with route_activities_to(task_queue, [act_extract_gen_extract_pages.__name__, act_render_page_views.__name__]):
            async with get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
                test_workflows=TEMPORAL_TEST_WORKFLOWS,
                substitute_activities={
                    act_extract_gen_extract_pages: _stub_act_extract_gen_extract_pages,
                    act_render_page_views: _stub_act_render_page_views,
                },
            ):
                handle = await temporal_client.start_workflow(  # pyright: ignore[reportUnknownMemberType]
                    workflow=WfTestContentGeneratorPdfPageViews.run,
                    arg=False,
                    id=workflow_id,
                    task_queue=task_queue,
                )
                await handle.result()
                history = await handle.fetch_history()

        # Filter by activity_type (not by activity_id suffix): a future test that
        # passes a wfid like "my-pages" to make_object would otherwise pollute this
        # assertion. Pinning to the activity name is strict.
        extract_activity_names = {"act_extract_gen_extract_pages", "act_render_page_views"}
        extract_ids = [
            event.activity_task_scheduled_event_attributes.activity_id
            for event in history.events
            if event.activity_task_scheduled_event_attributes.activity_type.name in extract_activity_names
        ]
        all_scheduled = [
            (event.activity_task_scheduled_event_attributes.activity_type.name, event.activity_task_scheduled_event_attributes.activity_id)
            for event in history.events
            if event.activity_task_scheduled_event_attributes.activity_id
        ]
        assert extract_ids == ["extract-pages", "extract-render-page-views"], (
            f"Unexpected extract activity_ids in history: {extract_ids!r} (full scheduled (type, id) pairs: {all_scheduled!r})"
        )
