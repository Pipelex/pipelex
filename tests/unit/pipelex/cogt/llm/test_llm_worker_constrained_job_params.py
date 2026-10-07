from typing import Any

from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory


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
