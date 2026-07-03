"""Integration test: the agent CLI surfaces the cost report in its JSON output (not a stderr table).

``run_pipeline_core`` attaches a ``cost_report`` object to the ``--with-memory`` envelope when the run
has non-zero cost, and omits it for zero-cost (dry-run-shaped) usage. The runner is mocked so the test
crafts the assembled ``tokens_usages`` directly and spends nothing.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.job_metadata import JobMetadata

_RUN_CORE_MODULE = "pipelex.cli.agent_cli.commands.run._run_core"


def _memory_with_main_stuff() -> WorkingMemory:
    """A completed run always delivers a main stuff — the mocked runner output must honor that."""
    stuff = Stuff(
        stuff_code="main-code",
        stuff_name="result",
        concept=Concept(
            code="Text",
            domain_code="native",
            description="Plain text",
            structure_class_name="TextContent",
        ),
        content=TextContent(text="the result"),
    )
    return WorkingMemory(root={"result": stuff}, aliases={MAIN_STUFF_NAME: "result"})


def _non_zero_usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="claude-x",
        inference_model_id="claude-x-id",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 2000},
    )


def _zero_cost_usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="dry",
        inference_model_id="dry-run",
        nb_tokens_by_category={},
        unit_costs={},
    )


def _free_model_usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    """A free/zero-price model: real tokens, no unit costs -> tokens but zero cost."""
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="ollama-x",
        inference_model_id="ollama-x-id",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        unit_costs={},
    )


@pytest.mark.asyncio(loop_scope="class")
class TestAgentRunCostReport:
    def _patch_runner(self, mocker: MockerFixture, pipe_output: PipeOutput) -> None:
        response = mocker.MagicMock()
        response.pipe_output = pipe_output
        runner = mocker.MagicMock()
        runner.execute = mocker.AsyncMock(return_value=response)
        mocker.patch(f"{_RUN_CORE_MODULE}.PipelexMTHDSProtocol", return_value=runner)

    async def test_cost_report_in_with_memory_json(self, mocker: MockerFixture, job_metadata: JobMetadata, tmp_path: Path) -> None:
        pipe_output = PipeOutput(
            working_memory=_memory_with_main_stuff(),
            pipeline_run_id="agent-run",
            tokens_usages=[_non_zero_usage(job_metadata)],
        )
        self._patch_runner(mocker, pipe_output)

        result = await run_pipeline_core(
            pipe_code="my_pipe",
            bundle_uris=[str(tmp_path / "bundle.mthds")],
            costs=True,
            with_memory=True,
        )

        assert "cost_report" in result
        assert result["cost_report"]["total_cost"] == 0.2
        assert result["cost_report"]["by_model"][0]["model"] == "claude-x"

    async def test_cost_report_for_free_model_run(self, mocker: MockerFixture, job_metadata: JobMetadata, tmp_path: Path) -> None:
        """A free/zero-price model with real tokens still surfaces a cost_report (total_cost 0)."""
        pipe_output = PipeOutput(
            working_memory=_memory_with_main_stuff(),
            pipeline_run_id="agent-free",
            tokens_usages=[_free_model_usage(job_metadata)],
        )
        self._patch_runner(mocker, pipe_output)

        result = await run_pipeline_core(
            pipe_code="my_pipe",
            bundle_uris=[str(tmp_path / "bundle.mthds")],
            costs=True,
            with_memory=True,
        )

        assert "cost_report" in result
        assert result["cost_report"]["total_cost"] == 0.0
        assert result["cost_report"]["by_model"][0]["nb_tokens_input"] == 100

    async def test_no_cost_report_for_dry_run(self, mocker: MockerFixture, job_metadata: JobMetadata, tmp_path: Path) -> None:
        pipe_output = PipeOutput(
            working_memory=_memory_with_main_stuff(),
            pipeline_run_id="agent-dry",
            tokens_usages=[_zero_cost_usage(job_metadata)],
        )
        self._patch_runner(mocker, pipe_output)

        result = await run_pipeline_core(
            pipe_code="my_pipe",
            bundle_uris=[str(tmp_path / "bundle.mthds")],
            costs=True,
            with_memory=True,
        )

        assert "cost_report" not in result
