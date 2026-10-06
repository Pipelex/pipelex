"""A dry-run condition runs every outcome but the last on a copy of the memory it received.

A dry run cannot know which outcome a live run would take, so ``PipeCondition`` dry-runs every
outcome, and the default outcome runs last. No outcome reads what a sibling wrote, and the steps
after the condition read the value a live run falls back to when nothing matches.
"""

from collections.abc import Sequence

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory import working_memory as working_memory_module
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline
from tests.integration.pipelex.pipeline.dry_run_condition.graph_reading import input_named, node_by_code, only_output
from tests.integration.pipelex.pipeline.dry_run_condition.test_data import DryRunConditionTestData


def _replaced_key_warnings(warning_calls: Sequence[object], *, key: str) -> list[str]:
    needle = f"Key '{key}' already exists in WorkingMemory and will be replaced"
    return [str(call) for call in warning_calls if needle in str(call)]


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunConditionOutcomeIsolation:
    async def test_an_outcome_reads_the_slot_as_the_condition_received_it(self) -> None:
        """`b_polish` runs after `a_rewrite` and reads `draft`: it must read `first_draft`'s value."""
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.SLOT_CROSS_READ_MTHDS])

        first_draft_digest = only_output(node_by_code(graph_spec, "first_draft")).digest
        polish_read_digest = input_named(node_by_code(graph_spec, "b_polish"), "draft").digest
        rewrite_digest = only_output(node_by_code(graph_spec, "a_rewrite")).digest

        assert first_draft_digest is not None
        assert polish_read_digest == first_draft_digest
        assert polish_read_digest != rewrite_digest

    async def test_no_outcome_replaces_a_sibling_value_in_the_slot(self, mocker: MockerFixture) -> None:
        """`follow_up` holds nothing before the condition, so no outcome may find it already written."""
        warning_spy = mocker.spy(working_memory_module.log, "warning")

        await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.REPORT_SHAPE_MTHDS])

        assert _replaced_key_warnings(warning_spy.call_args_list, key="follow_up") == []

    async def test_the_default_outcome_names_the_shared_stuff(self) -> None:
        """The default outcome runs last, so its value is the one the next step reads."""
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.SLOT_CROSS_READ_MTHDS])

        shared_digest = only_output(node_by_code(graph_spec, "route")).digest
        assert only_output(node_by_code(graph_spec, "b_polish")).digest == shared_digest
        assert only_output(node_by_code(graph_spec, "a_rewrite")).digest == shared_digest
