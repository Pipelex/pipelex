from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.job_metadata import JobMetadata, RunMetadata

if TYPE_CHECKING:
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class _Answer(BaseModel):
    text: str


class _RecordingLLMWorker(LLMWorkerAbstract):
    """A worker whose provider half records each call it is asked to make."""

    def __init__(self, *, inference_model: InferenceModelSpec) -> None:
        LLMWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self.calls: list[str] = []

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        self.calls.append("text")
        return "answer"

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        self.calls.append("object")
        return schema.model_validate({"text": "answer"})


def _make_model(*, thinking_mode: ThinkingMode) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="openai",
        name="gpt-test",
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="gpt-test-id",
        inputs=["text"],
        outputs=["text", "structured"],
        costs={CostCategory.INPUT: 1, CostCategory.OUTPUT: 2},
        thinking_mode=thinking_mode,
        max_tokens=None,
        max_prompt_images=None,
    )


def _make_llm_job(*, job_params: LLMJobParams) -> LLMJob:
    return LLMJob(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-check", storage_scope="test/scope", read_scope=None)
        ),
        llm_prompt=LLMPrompt(user_text="hello"),
        job_params=job_params,
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


class TestLLMWorkerRequestCheck:
    @pytest.mark.parametrize(
        "job_params",
        [
            pytest.param(LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH), id="effort"),
            pytest.param(LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.NONE), id="effort_none"),
            pytest.param(LLMJobParams(temperature=0.5, reasoning_budget=2048), id="budget"),
        ],
    )
    @pytest.mark.parametrize("is_structured", [False, True])
    def test_a_model_without_thinking_refuses_every_reasoning_setting(self, job_params: LLMJobParams, is_structured: bool) -> None:
        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            LLMWorkerAbstract.check_request(
                inference_model=_make_model(thinking_mode=ThinkingMode.NONE), job_params=job_params, is_structured=is_structured
            )

    @pytest.mark.parametrize(
        ("thinking_mode", "job_params"),
        [
            pytest.param(ThinkingMode.NONE, LLMJobParams(temperature=0.5), id="no_thinking_no_setting"),
            pytest.param(ThinkingMode.MANUAL, LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH), id="manual_effort"),
            pytest.param(ThinkingMode.ADAPTIVE, LLMJobParams(temperature=0.5, reasoning_budget=2048), id="adaptive_budget"),
        ],
    )
    def test_the_shared_rule_passes_every_other_request(self, thinking_mode: ThinkingMode, job_params: LLMJobParams) -> None:
        LLMWorkerAbstract.check_request(inference_model=_make_model(thinking_mode=thinking_mode), job_params=job_params, is_structured=True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_structured", [False, True])
    async def test_a_refused_request_never_reaches_the_provider(self, is_structured: bool) -> None:
        worker = _RecordingLLMWorker(inference_model=_make_model(thinking_mode=ThinkingMode.NONE))
        llm_job = _make_llm_job(job_params=LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.LOW))
        invocation = worker.gen_object(llm_job=llm_job, schema=_Answer) if is_structured else worker.gen_text(llm_job=llm_job)
        with pytest.raises(LLMCapabilityError) as exc_info:
            await invocation
        assert worker.calls == []
        assert exc_info.value.to_error_report().model == "gpt-test"

    @pytest.mark.asyncio
    async def test_an_accepted_request_reaches_the_provider(self) -> None:
        worker = _RecordingLLMWorker(inference_model=_make_model(thinking_mode=ThinkingMode.MANUAL))
        llm_job = _make_llm_job(job_params=LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.LOW))
        await worker.gen_text(llm_job=llm_job)
        await worker.gen_object(llm_job=llm_job, schema=_Answer)
        assert worker.calls == ["text", "object"]
