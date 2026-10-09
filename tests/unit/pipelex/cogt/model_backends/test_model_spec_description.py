"""A model spec's `tag` and `desc` are plain text: they name the SDK, the backend and the model id in brackets, never escaped for Rich.

They reach error messages, which a log sink or an API response carries as written, so a backslash put there for a
console reading markup would show up everywhere else.
"""

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory


def _make_spec() -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="openai",
        name="gpt-5",
        sdk="openai_responses",
        model_type=ModelType.LLM,
        model_id="gpt-5-2025",
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.MANUAL,
        max_tokens=None,
        max_prompt_images=None,
    )


class TestModelSpecDescription:
    def test_the_tag_and_the_description_are_plain_text(self) -> None:
        spec = _make_spec()

        assert spec.tag == "gpt-5 → [openai_responses@openai](gpt-5-2025)"
        assert spec.desc == "gpt-5 → SDK[openai_responses]•Backend[openai]•Model[gpt-5-2025]"
