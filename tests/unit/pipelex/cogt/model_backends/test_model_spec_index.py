"""A handle names one model per model type: the index of specs keyed by type, then by handle."""

import pytest

from pipelex.cogt.exceptions import InferenceModelSpecError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType


def _spec(*, name: str, model_type: ModelType, backend_name: str = "openai") -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=name,
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


class TestModelSpecIndex:
    def test_one_handle_holds_one_spec_per_model_type(self) -> None:
        llm_spec = _spec(name="gpt-6-luna", model_type=ModelType.LLM)
        judgment_spec = _spec(name="gpt-6-luna", model_type=ModelType.JUDGMENT, backend_name="openai_decisions")

        index = ModelSpecIndex.make_from_specs(model_specs=[llm_spec, judgment_spec])

        assert index.get(model_type=ModelType.LLM, handle="gpt-6-luna") is llm_spec
        assert index.get(model_type=ModelType.JUDGMENT, handle="gpt-6-luna") is judgment_spec
        assert index.get(model_type=ModelType.SEARCH, handle="gpt-6-luna") is None
        assert index.types_serving(handle="gpt-6-luna") == [ModelType.LLM, ModelType.JUDGMENT]
        assert len(index) == 2
        assert index.all_handles() == ["gpt-6-luna"]

    def test_the_same_pair_twice_is_refused_naming_both_backends(self) -> None:
        index = ModelSpecIndex.make_from_specs(model_specs=[_spec(name="gpt-6-luna", model_type=ModelType.JUDGMENT, backend_name="first")])

        with pytest.raises(InferenceModelSpecError) as exc_info:
            index.add(_spec(name="gpt-6-luna", model_type=ModelType.JUDGMENT, backend_name="second"))

        message = str(exc_info.value)
        assert "'gpt-6-luna'" in message
        assert "a judgment model" in message
        assert "'first'" in message
        assert "'second'" in message

    def test_the_questions_of_one_type_see_that_type_only(self) -> None:
        index = ModelSpecIndex.make_from_specs(
            model_specs=[
                _spec(name="gpt-6-luna", model_type=ModelType.LLM),
                _spec(name="claude", model_type=ModelType.LLM),
                _spec(name="gpt-6-luna", model_type=ModelType.JUDGMENT),
                _spec(name="verdict", model_type=ModelType.JUDGMENT),
            ]
        )

        assert index.handles_of_type(model_type=ModelType.LLM) == ["claude", "gpt-6-luna"]
        assert index.handles_of_type(model_type=ModelType.JUDGMENT) == ["gpt-6-luna", "verdict"]
        assert index.handles_of_type(model_type=ModelType.SEARCH) == []
        assert sorted((spec.model_type, spec.name) for spec in index.all_specs()) == [
            (ModelType.JUDGMENT, "gpt-6-luna"),
            (ModelType.JUDGMENT, "verdict"),
            (ModelType.LLM, "claude"),
            (ModelType.LLM, "gpt-6-luna"),
        ]

    def test_an_empty_index_is_falsy(self) -> None:
        """Readers test a backend's specs for emptiness, so the length must count the specs."""
        assert not ModelSpecIndex.make_empty()
        assert ModelSpecIndex.make_from_specs(model_specs=[_spec(name="x", model_type=ModelType.SEARCH)])
