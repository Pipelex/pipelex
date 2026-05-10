"""Cross-process round-trip tests for ``act_llm_gen_object`` and
``act_llm_gen_object_list``.

Every existing ``library_crate/*.mthds`` bundle outputs ``Text``, so the
structured-output activities never go through Temporal's data converter
across the activity boundary. This suite closes that gap: it submits the
``WfTestStructuredOutputCrossProcess`` fixture workflow and substitutes
``act_llm_gen_object*`` with activities returning canonical ``FixtureInvoice``
instances. The fixture workflow asserts that nested ``FixtureCustomer`` and
``FixtureLineItem`` fields survived ``model_dump(mode="json", serialize_as_any=True)``
→ data converter → ``model_validate(...)``.

Pre-existing asymmetry pinned by these tests: ``make_object`` calls
``model_dump(mode="json", ...)`` while the legacy ``ContentGeneratorChild.make_object_list``
historically omitted ``mode="json"``. The in-workflow generator uses
``mode="json"`` on both, and these tests guard that contract through the
real Temporal data converter (kajson encoder/decoder).

Note on "split worker": single-worker setup is sufficient for the data
converter round-trip — Temporal still serializes/deserializes the activity
return value across the activity boundary even when the same Python process
hosts both the workflow and the activity. A true cross-process upgrade is
now possible via ``worker_config.activity_queues`` (per-activity routing
shipped in v1; see ``wip/temporal-primitives/per-activity-queue-routing-v1.md``
§"Tests to upgrade when v1 lands"): route ``act_llm_gen_object*`` to a
runner queue and register the substitutes only on that queue. Tracked as a
follow-up — this file is the primary caller of that upgrade.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.assignment_models import ObjectAssignment
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.test_extras.temporal_registry_test_models import FixtureCustomer, FixtureInvoice, FixtureLineItem
from pipelex.temporal.test_extras.temporal_test_tasks import TEMPORAL_TEST_WORKFLOWS
from pipelex.temporal.test_extras.wf_test_structured_output_cross_process import WfTestStructuredOutputCrossProcess
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_object, act_llm_gen_object_list
from tests.integration.pipelex.temporal.tracing.helpers import route_activities_to


def _make_canonical_invoice() -> FixtureInvoice:
    """Canonical fixture matched by ``_assert_invoice_round_trip`` in the workflow."""
    return FixtureInvoice(
        invoice_number="INV-RT-001",
        customer=FixtureCustomer(name="Alice Chen", email="alice@example.com"),
        line_items=[
            FixtureLineItem(product_name="Widget", quantity=3, unit_price=9.99),
            FixtureLineItem(product_name="Gadget", quantity=1, unit_price=49.50),
        ],
        total_amount=79.47,
    )


@activity.defn(name="act_llm_gen_object")
async def _stub_act_llm_gen_object(_object_assignment: ObjectAssignment) -> FixtureInvoice:  # noqa: RUF029
    """Substitute that returns a canonical ``FixtureInvoice``.

    Bypasses the real LLM call so the test focuses on the activity-boundary
    serialization. Annotated as ``act_llm_gen_object`` so the worker uses
    this implementation in place of the registered one.
    """
    return _make_canonical_invoice()


@activity.defn(name="act_llm_gen_object_list")
async def _stub_act_llm_gen_object_list(_object_assignment: ObjectAssignment) -> list[FixtureInvoice]:  # noqa: RUF029
    return [
        FixtureInvoice(
            invoice_number="INV-RT-A",
            customer=FixtureCustomer(name="Alice", email="alice@example.com"),
            line_items=[FixtureLineItem(product_name="Alpha", quantity=1, unit_price=1.0)],
            total_amount=1.0,
        ),
        FixtureInvoice(
            invoice_number="INV-RT-B",
            customer=FixtureCustomer(name="Bob", email="bob@example.com"),
            line_items=[FixtureLineItem(product_name="Beta", quantity=2, unit_price=2.0)],
            total_amount=4.0,
        ),
    ]


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerObjectGen:
    """Round-trip nested structured output across the Temporal data converter.

    Workflow completion = round-trip preserved nested fields (the fixture
    workflow's assertion helpers validate ``FixtureCustomer`` and
    ``FixtureLineItem`` value preservation). A failure surfaces as a
    ``WorkflowFailureError`` from ``execute_workflow``.
    """

    @pytest.mark.parametrize(
        "is_list",
        [
            pytest.param(False, id="single"),
            pytest.param(True, id="list"),
        ],
    )
    @pytest.mark.timeout(60)
    async def test_object_gen_round_trip_preserves_nested_fields(
        self,
        temporal_client: TemporalClient,
        is_list: bool,
    ) -> None:
        task_queue = f"q_obj_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_obj_{'list' if is_list else 'single'}_{uuid.uuid4().hex[:8]}"

        # Route the substituted object-gen activities to this test's UUID queue
        # so the in-workflow dispatcher (which now passes ``task_queue=resolved``
        # for every activity) lands them on the worker registered here.
        with route_activities_to(task_queue, [act_llm_gen_object.__name__, act_llm_gen_object_list.__name__]):
            async with get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
                test_workflows=TEMPORAL_TEST_WORKFLOWS,
                substitute_activities={
                    act_llm_gen_object: _stub_act_llm_gen_object,
                    act_llm_gen_object_list: _stub_act_llm_gen_object_list,
                },
            ):
                await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                    workflow=WfTestStructuredOutputCrossProcess.run,
                    arg=is_list,
                    id=workflow_id,
                    task_queue=task_queue,
                )
