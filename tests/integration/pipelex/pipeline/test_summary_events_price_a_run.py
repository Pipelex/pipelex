from __future__ import annotations

import io
import json
import logging
import math
from collections import defaultdict
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from pipelex.cogt.inference.inference_call_summary import INFERENCE_CALL_ENDS_MESSAGE
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipe_machinery.pipe_abstract import PIPE_RUN_ENDS_MESSAGE
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.tools.log.json_log_sink import MESSAGE_KEY, JsonLogSink
from tests.integration.pipelex.pipeline.test_data import SummaryEventsTestData

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

# The models the method's presets resolve to here, as the stand-in workers name them, with their rates per million
# tokens in and out. Each call reads 1,000 tokens and writes 200.
STAND_IN_MODELS: dict[str, tuple[str, dict[CostCategory, float]]] = {
    "@default-small": ("small-test-model", {CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 4.0}),
    "@default-premium": ("premium-test-model", {CostCategory.INPUT: 5.0, CostCategory.OUTPUT: 20.0}),
}
INPUT_TOKENS = 1000
OUTPUT_TOKENS = 200


class StandInLLMWorker(LLMWorkerAbstract):
    """Answers every generation without a provider, recording the usage a provider would have answered with."""

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        self._record_usage(llm_job=llm_job)
        return "Acme builds reusable rockets for research labs."

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        self._record_usage(llm_job=llm_job)
        return schema.model_validate({field_name: f"Stand-in {field_name}" for field_name in schema.model_fields})

    @staticmethod
    def _record_usage(*, llm_job: LLMJob) -> None:
        tokens_usage = llm_job.job_report.llm_tokens_usage
        assert tokens_usage is not None
        tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: INPUT_TOKENS, TokenCategory.OUTPUT: OUTPUT_TOKENS}


def _stand_in_worker(*, llm_handle: str) -> StandInLLMWorker:
    """The worker the handle resolves to here, a stand-in for the model it would have reached."""
    model_name, rates = STAND_IN_MODELS[llm_handle]
    inference_model = InferenceModelSpec(
        backend_name="stand_in",
        name=model_name,
        sdk="stand_in",
        model_type=ModelType.LLM,
        model_id=f"{model_name}-2026",
        inputs=["text"],
        outputs=["text", "structured"],
        costs=rates,
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return StandInLLMWorker(inference_model=inference_model, reporting_delegate=None)


@contextmanager
def _json_sink_on_root(*, buffer: io.StringIO) -> Generator[None]:
    """The ``json`` sink's handler on the root logger, beside whatever the session installed, for as long as the block runs."""
    handler = JsonLogSink(stream=buffer).handler
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        handler.close()


@pytest.mark.asyncio(loop_scope="class")
class TestSummaryEventsPriceARun:
    async def test_the_json_output_alone_gives_latency_and_cost_per_operation_and_model(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        """What a dashboard does with a run's ``json`` output: group the inference events by operation and model, and add them up."""
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", side_effect=_stand_in_worker)
        # The default production level.
        caplog.set_level(logging.INFO, logger="pipelex")
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE)
        buffer = io.StringIO()

        with _json_sink_on_root(buffer=buffer):
            await runner.execute(
                pipe_code=SummaryEventsTestData.MAIN_PIPE, mthds_contents=[SummaryEventsTestData.MTHDS], inputs=SummaryEventsTestData.INPUTS
            )

        lines: list[dict[str, Any]] = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
        calls = [line for line in lines if line[MESSAGE_KEY] == INFERENCE_CALL_ENDS_MESSAGE]
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for call in calls:
            groups[call[GenAISpanAttr.OPERATION_NAME], call["model_handle"]].append(call)
        cost_by_group = {key: sum(call["cost_usd"] for call in group) for key, group in groups.items()}
        latency_by_group = {key: sum(call["duration_ms"] for call in group) / len(group) for key, group in groups.items()}
        tokens_by_group = {
            key: (sum(call[GenAISpanAttr.USAGE_INPUT_TOKENS] for call in group), sum(call[GenAISpanAttr.USAGE_OUTPUT_TOKENS] for call in group))
            for key, group in groups.items()
        }

        assert {key: len(group) for key, group in groups.items()} == {("chat", "small-test-model"): 2, ("chat", "premium-test-model"): 1}
        # 1,000 tokens in and 200 out: $0.0018 a call at $1 and $4 a million, $0.009 at $5 and $20.
        assert math.isclose(cost_by_group["chat", "small-test-model"], 0.0036)
        assert math.isclose(cost_by_group["chat", "premium-test-model"], 0.009)
        assert tokens_by_group == {("chat", "small-test-model"): (2000, 400), ("chat", "premium-test-model"): (1000, 200)}
        for key, latency_ms in latency_by_group.items():
            assert isinstance(latency_ms, float), key
            assert latency_ms >= 0, key
        assert all(call["outcome"] == "success" for call in calls)
        # Every pipe the run announced ended once, at the depth it announced itself.
        ended = sorted((line["pipe_code"], line["pipe_depth"], line["outcome"]) for line in lines if line[MESSAGE_KEY] == PIPE_RUN_ENDS_MESSAGE)
        assert ended == [
            ("brief_company", 0, "success"),
            ("describe_company", 1, "success"),
            ("pitch_company", 1, "success"),
            ("structure_company", 1, "success"),
        ]
