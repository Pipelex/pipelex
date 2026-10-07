"""A model spec says whether its provider takes a temperature, from the `temperature_unsupported` listed constraint.

Every LLM worker reads this one answer, so a model listing the constraint gets no temperature on any SDK.
"""

import pytest

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory


def _make_spec(*, listed_constraints: list[ListedConstraint]) -> InferenceModelSpec:
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
        listed_constraints=listed_constraints,
    )


class TestModelSpecTemperature:
    @pytest.mark.parametrize(
        ("listed_constraints", "expected"),
        [
            ([], True),
            ([ListedConstraint.TEMPERATURE_MUST_BE_MULTIPLIED_BY_2], True),
            ([ListedConstraint.TEMPERATURE_UNSUPPORTED], False),
            ([ListedConstraint.THINKING_CANNOT_BE_DISABLED, ListedConstraint.TEMPERATURE_UNSUPPORTED], False),
        ],
    )
    def test_accepts_temperature_reads_the_listed_constraint(self, listed_constraints: list[ListedConstraint], expected: bool) -> None:
        assert _make_spec(listed_constraints=listed_constraints).accepts_temperature is expected
