from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.tools.log.json_log_sink import MESSAGE_KEY, JsonLogSink

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

FIXED_TEMPERATURE_WARNING = "The model's fixed temperature was used in place of the requested one"


def _make_model(
    *,
    thinking_mode: ThinkingMode,
    max_tokens: int | None = None,
    listed_constraints: list[ListedConstraint] | None = None,
    valued_constraints: dict[ValuedConstraint, Any] | None = None,
) -> InferenceModelSpec:
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
        max_tokens=max_tokens,
        max_prompt_images=None,
        listed_constraints=listed_constraints or [],
        valued_constraints=valued_constraints or {},
    )


class _ProviderlessLLMWorker(LLMWorkerAbstract):
    """A worker that never reaches a provider: only its handling of the model's constraints is exercised."""

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        raise NotImplementedError

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        raise NotImplementedError


class TestConstrainedJobParams:
    def test_a_model_without_constraints_changes_nothing(self) -> None:
        job_params = LLMJobParams(temperature=0.5, max_tokens=None)
        assert LLMWorkerAbstract.constrained_job_params(inference_model=_make_model(thinking_mode=ThinkingMode.NONE), job_params=job_params) is None

    def test_a_scaled_temperature_doubles_and_takes_the_model_max_tokens(self) -> None:
        inference_model = _make_model(
            thinking_mode=ThinkingMode.NONE, max_tokens=8000, listed_constraints=[ListedConstraint.TEMPERATURE_MUST_BE_MULTIPLIED_BY_2]
        )
        constrained = LLMWorkerAbstract.constrained_job_params(inference_model=inference_model, job_params=LLMJobParams(temperature=0.25))
        assert constrained is not None
        assert constrained.temperature == 0.5
        assert constrained.max_tokens == 8000

    def test_a_fixed_temperature_replaces_the_one_asked_for(self) -> None:
        inference_model = _make_model(thinking_mode=ThinkingMode.MANUAL, valued_constraints={ValuedConstraint.FIXED_TEMPERATURE: 1})
        constrained = LLMWorkerAbstract.constrained_job_params(
            inference_model=inference_model, job_params=LLMJobParams(temperature=0.2, max_tokens=500, reasoning_effort=ReasoningEffort.HIGH)
        )
        assert constrained is not None
        assert constrained.temperature == 1
        assert constrained.max_tokens == 500
        assert constrained.reasoning_effort == ReasoningEffort.HIGH

    def test_a_fixed_temperature_already_asked_for_changes_nothing(self) -> None:
        inference_model = _make_model(thinking_mode=ThinkingMode.MANUAL, valued_constraints={ValuedConstraint.FIXED_TEMPERATURE: 1})
        assert LLMWorkerAbstract.constrained_job_params(inference_model=inference_model, job_params=LLMJobParams(temperature=1)) is None

    def test_a_replaced_temperature_is_warned_with_the_model_and_both_temperatures_as_fields(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The warning names the model as its description used to, with the model keys meaning what they mean on the LLM span:
        the handle requested under `gen_ai.request.model` and the provider's model id under `gen_ai.response.model`. The json sink
        writes these OpenTelemetry keys, and the requested temperature's, as plain keys.
        """
        inference_model = _make_model(thinking_mode=ThinkingMode.MANUAL, valued_constraints={ValuedConstraint.FIXED_TEMPERATURE: 1})
        worker = _ProviderlessLLMWorker(inference_model=inference_model)
        llm_job = mocker.MagicMock(job_params=LLMJobParams(temperature=0.2))

        with caplog.at_level(logging.WARNING, logger=LLMWorkerAbstract.__module__):
            worker._apply_constraints(llm_job)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

        (record,) = [record for record in caplog.records if record.getMessage() == FIXED_TEMPERATURE_WARNING]
        buffer = io.StringIO()
        JsonLogSink(stream=buffer).handler.handle(record)
        line: dict[str, Any] = json.loads(buffer.getvalue())
        assert line[MESSAGE_KEY] == FIXED_TEMPERATURE_WARNING
        field_names = (
            "model_handle",
            "backend_name",
            "sdk",
            "gen_ai.request.model",
            "gen_ai.response.model",
            "gen_ai.request.temperature",
            "fixed_temperature",
        )
        assert {name: line[name] for name in field_names} == {
            "model_handle": "gpt-test",
            "backend_name": "openai",
            "sdk": "openai",
            "gen_ai.request.model": "gpt-test",
            "gen_ai.response.model": "gpt-test-id",
            "gen_ai.request.temperature": 0.2,
            "fixed_temperature": 1,
        }
        assert "backend" not in line
