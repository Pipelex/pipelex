"""A model spec declares the range of manual thinking budgets its provider accepts as two valued constraints.

`min_thinking_budget` and `max_thinking_budget` are both inclusive and both optional; a spec declaring a bound
that is not a non-negative integer, or a minimum above its maximum, is refused when it is built.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory


def _make_spec(*, valued_constraints: dict[ValuedConstraint, Any]) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test",
        name="test-model",
        sdk="test_sdk",
        model_type=ModelType.LLM,
        model_id="test-model-id",
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.MANUAL,
        max_tokens=None,
        max_prompt_images=None,
        valued_constraints=valued_constraints,
    )


class TestModelSpecThinkingBudgetBounds:
    @pytest.mark.parametrize(
        ("valued_constraints", "expected_min", "expected_max"),
        [
            ({}, None, None),
            ({ValuedConstraint.MIN_THINKING_BUDGET: 1024}, 1024, None),
            ({ValuedConstraint.MAX_THINKING_BUDGET: 24576}, None, 24576),
            ({ValuedConstraint.MIN_THINKING_BUDGET: 128, ValuedConstraint.MAX_THINKING_BUDGET: 32768}, 128, 32768),
            ({ValuedConstraint.MIN_THINKING_BUDGET: 512, ValuedConstraint.MAX_THINKING_BUDGET: 512}, 512, 512),
        ],
    )
    def test_declared_bounds_are_read_back(
        self, valued_constraints: dict[ValuedConstraint, Any], expected_min: int | None, expected_max: int | None
    ) -> None:
        spec = _make_spec(valued_constraints=valued_constraints)
        assert spec.min_thinking_budget == expected_min
        assert spec.max_thinking_budget == expected_max

    @pytest.mark.parametrize(
        ("valued_constraints", "expected_message"),
        [
            ({ValuedConstraint.MIN_THINKING_BUDGET: "1024"}, "min_thinking_budget='1024', which must be a non-negative integer"),
            ({ValuedConstraint.MAX_THINKING_BUDGET: True}, "max_thinking_budget=True, which must be a non-negative integer"),
            ({ValuedConstraint.MAX_THINKING_BUDGET: 2.5}, "max_thinking_budget=2.5, which must be a non-negative integer"),
            ({ValuedConstraint.MIN_THINKING_BUDGET: -1}, "min_thinking_budget=-1, which must be a non-negative integer"),
            (
                {ValuedConstraint.MIN_THINKING_BUDGET: 2048, ValuedConstraint.MAX_THINKING_BUDGET: 1024},
                "min_thinking_budget=2048 above max_thinking_budget=1024",
            ),
        ],
    )
    def test_an_invalid_declaration_is_refused(self, valued_constraints: dict[ValuedConstraint, Any], expected_message: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _make_spec(valued_constraints=valued_constraints)
        assert expected_message in str(exc_info.value)
