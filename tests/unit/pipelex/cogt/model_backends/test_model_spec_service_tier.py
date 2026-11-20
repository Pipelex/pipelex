from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_factory import (
    InferenceModelSpecBlueprint,
    InferenceModelSpecFactory,
)
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_backends.service_tier import ServiceTier
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_constants import OpenAIBodyKey
from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.providers.openrouter.openrouter_completions_factory import (
    OpenRouterCompletionsFactory,
)
from pipelex.providers.portkey.portkey_factory import PortkeyFactory


def _make_spec(*, service_tier: ServiceTier | None = None) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test-backend",
        name="test-model",
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="gpt-test",
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.MANUAL,
        max_tokens=None,
        max_prompt_images=None,
        service_tier=service_tier,
    )


class TestModelSpecServiceTier:
    @pytest.mark.parametrize(
        ("tier_input", "expected_tier"),
        [
            ("auto", ServiceTier.AUTO),
            ("default", ServiceTier.DEFAULT),
            ("fast", ServiceTier.FAST),
            ("flex", ServiceTier.FLEX),
            ("scale", ServiceTier.SCALE),
            ("priority", ServiceTier.PRIORITY),
            ("standard_only", ServiceTier.STANDARD_ONLY),
            (ServiceTier.FAST, ServiceTier.FAST),
            (None, None),
        ],
    )
    def test_blueprint_accepts_valid_service_tier(self, tier_input: str | ServiceTier | None, expected_tier: ServiceTier | None) -> None:
        blueprint = InferenceModelSpecBlueprint(
            sdk="openai",
            model_type=ModelType.LLM,
            service_tier=tier_input,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        )
        assert blueprint.service_tier == expected_tier

    def test_blueprint_rejects_invalid_service_tier(self) -> None:
        with pytest.raises(ValidationError):
            InferenceModelSpecBlueprint(
                sdk="openai",
                model_type=ModelType.LLM,
                service_tier="ultra",  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
            )

    def test_factory_copies_service_tier_to_spec(self) -> None:
        blueprint = InferenceModelSpecBlueprint(
            sdk="openai",
            model_type=ModelType.LLM,
            service_tier=ServiceTier.FAST,
        )
        spec = InferenceModelSpecFactory.make_inference_model_spec(
            "test-backend",
            name="test-model",
            blueprint=blueprint,
            backend_listed_constraints=[],
            backend_valued_constraints={},
        )
        assert spec.service_tier == ServiceTier.FAST

    def test_spec_service_tier_defaults_to_none(self) -> None:
        spec = _make_spec()
        assert spec.service_tier is None


class TestOpenAIFactoriesServiceTier:
    def test_openai_responses_factory_make_extras_with_service_tier(self) -> None:
        factory = OpenAIResponsesFactory(is_http_url_enabled=False)
        spec = _make_spec(service_tier=ServiceTier.FAST)
        job = MagicMock(spec=InferenceJobAbstract)

        headers, body = factory.make_extras(spec, inference_job=job, output_desc="text")

        assert headers == {}
        assert body == {OpenAIBodyKey.SERVICE_TIER: "fast"}

    def test_openai_responses_factory_make_extras_without_service_tier(self) -> None:
        factory = OpenAIResponsesFactory(is_http_url_enabled=False)
        spec = _make_spec(service_tier=None)
        job = MagicMock(spec=InferenceJobAbstract)

        headers, body = factory.make_extras(spec, inference_job=job, output_desc="text")

        assert headers == {}
        assert body == {}

    def test_openai_completions_factory_make_extras_with_service_tier(self) -> None:
        factory = OpenAICompletionsFactory(is_http_url_enabled=False)
        spec = _make_spec(service_tier=ServiceTier.PRIORITY)
        job = MagicMock(spec=InferenceJobAbstract)

        headers, body = factory.make_extras(spec, inference_job=job, output_desc="text")

        assert headers == {}
        assert body == {OpenAIBodyKey.SERVICE_TIER: "priority"}

    def test_openrouter_completions_factory_preserves_service_tier(self) -> None:
        factory = OpenRouterCompletionsFactory(is_http_url_enabled=False)
        spec = _make_spec(service_tier=ServiceTier.FLEX)
        job = MagicMock(spec=InferenceJobAbstract)

        _headers, body = factory.make_extras(spec, inference_job=job, output_desc="text")

        assert body.get(OpenAIBodyKey.SERVICE_TIER) == "flex"

    def test_portkey_factory_make_extras_with_service_tier(self) -> None:
        spec = _make_spec(service_tier=ServiceTier.SCALE)
        job = MagicMock(spec=InferenceJobAbstract)
        job.job_metadata = MagicMock()
        job.job_metadata.otel_context = None

        _headers, body = PortkeyFactory.make_extras(spec, inference_job=job, output_desc="text")

        assert body.get(OpenAIBodyKey.SERVICE_TIER) == "scale"
