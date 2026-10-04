"""An image worker refuses a model spec it cannot use as a configuration fault, not as the caller's input.

A spec with no `rules`, a rule value this release does not know, or one missing the `model_choice` or
`endpoint_path` its worker needs, is the backend configuration's fault: the job fails before any provider call with an `ImgGenParameterError`
in the `CONFIGURATION` category, which the error model renders as a 500 rather than the 422 that
tells a caller to change what they sent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fal_client import AsyncClient as FalAsyncClient
from huggingface_hub import AsyncInferenceClient
from openai import AsyncOpenAI
from portkey_ai import AsyncPortkey

from pipelex.cogt.exceptions import ImgGenParameterError, InferenceErrorCategory
from pipelex.cogt.img_gen.img_gen_model_rules import ImgGenArgTopic
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.azure_rest.azure_img_gen_worker import AzureImgGenWorker
from pipelex.providers.fal.fal_img_gen_worker import FalImgGenWorker
from pipelex.providers.gateway.gateway_img_gen_worker import GatewayImgGenWorker
from pipelex.providers.huggingface.huggingface_img_gen_worker import HuggingFaceImgGenWorker
from pipelex.providers.manifold.manifold_img_gen_worker import ManifoldImgGenWorker
from pipelex.providers.openai.openai_img_gen_worker import OpenAIImgGenWorker
from tests.unit.pipelex.cogt.img_gen.conftest import make_img_gen_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.img_gen.img_gen_model_rules import ImgGenModelRules
    from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract

# Rules that every worker's args factory accepts, and that name neither a model choice nor a geometry.
PROMPT_ONLY_RULES: ImgGenModelRules = {ImgGenArgTopic.PROMPT: "positive_only"}
# Rules naming an aspect_ratio taxonomy no release knows, as a catalog newer than this release could.
UNKNOWN_ASPECT_RATIO_RULES: ImgGenModelRules = {ImgGenArgTopic.ASPECT_RATIO: "gemini_9_turbo"}
# Rules naming a prompt taxonomy no release knows, so the refusal is not particular to geometry.
UNKNOWN_PROMPT_RULES: ImgGenModelRules = {ImgGenArgTopic.PROMPT: "weird"}


def _model(*, backend_name: str, sdk: str, rules: ImgGenModelRules | None) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name="misconfigured-image-model",
        sdk=sdk,
        model_type=ModelType.IMG_GEN,
        model_id="misconfigured-image-model",
        inputs=["text"],
        outputs=["image"],
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
        rules=rules,
    )


def _make_worker(mocker: MockerFixture, *, worker_kind: str, rules: ImgGenModelRules | None) -> ImgGenWorkerAbstract:
    """The worker, built around an SDK stand-in it accepts, for a model with these rules and no endpoint path."""
    match worker_kind:
        case "openai":
            return OpenAIImgGenWorker(
                sdk_instance=mocker.MagicMock(spec=AsyncOpenAI), inference_model=_model(backend_name="openai", sdk="openai_img_gen", rules=rules)
            )
        case "gateway":
            return GatewayImgGenWorker(
                sdk_instance=mocker.MagicMock(spec=AsyncPortkey),
                inference_model=_model(backend_name="pipelex_gateway", sdk="gateway_img_gen", rules=rules),
            )
        case "manifold":
            return ManifoldImgGenWorker(
                sdk_instance=mocker.MagicMock(spec=AsyncPortkey),
                inference_model=_model(backend_name="pipelex_manifold", sdk="manifold_img_gen", rules=rules),
            )
        case "fal":
            return FalImgGenWorker(
                sdk_instance=mocker.MagicMock(spec=FalAsyncClient), inference_model=_model(backend_name="fal", sdk="fal", rules=rules)
            )
        case "huggingface":
            return HuggingFaceImgGenWorker(
                sdk_instance=mocker.MagicMock(spec=AsyncInferenceClient),
                inference_model=_model(backend_name="huggingface", sdk="huggingface_img_gen", rules=rules),
            )
        case "azure":
            backend: Any = mocker.MagicMock(endpoint="https://azure.example", extra_config={"api_version": "2025-04-01-preview"}, api_key="test-key")
            models_manager = mocker.MagicMock()
            models_manager.get_required_inference_backend.return_value = backend
            mocker.patch("pipelex.providers.azure_rest.azure_img_gen_worker.get_models_manager", return_value=models_manager)
            return AzureImgGenWorker(
                model_handle=ModelHandle(sdk="azure_rest_img_gen", backend="azure_openai"),
                inference_model=_model(backend_name="azure_openai", sdk="azure_rest_img_gen", rules=rules),
            )
        case _:
            msg = f"Unknown worker kind '{worker_kind}'"
            raise ValueError(msg)


class TestImgGenWorkerConfigFaults:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("worker_kind", "rules", "error_match"),
        [
            ("openai", None, "does not have rules configured"),
            ("gateway", None, "does not have rules configured"),
            ("manifold", None, "does not have rules configured"),
            ("fal", None, "does not have rules configured"),
            ("huggingface", None, "does not have rules configured"),
            ("azure", None, "does not have rules configured"),
            ("fal", PROMPT_ONLY_RULES, "must include a 'model_choice' entry"),
            ("huggingface", PROMPT_ONLY_RULES, "must include a 'model_choice' entry"),
            ("gateway", PROMPT_ONLY_RULES, "does not have an endpoint_path configured"),
            ("openai", UNKNOWN_ASPECT_RATIO_RULES, "unknown aspect_ratio taxonomy 'gemini_9_turbo'"),
            ("manifold", UNKNOWN_ASPECT_RATIO_RULES, "unknown aspect_ratio taxonomy 'gemini_9_turbo'"),
            ("azure", UNKNOWN_ASPECT_RATIO_RULES, "unknown aspect_ratio taxonomy 'gemini_9_turbo'"),
            ("openai", UNKNOWN_PROMPT_RULES, "unknown prompt taxonomy 'weird'"),
            ("fal", UNKNOWN_PROMPT_RULES, "unknown prompt taxonomy 'weird'"),
            ("huggingface", UNKNOWN_PROMPT_RULES, "unknown prompt taxonomy 'weird'"),
        ],
    )
    async def test_unusable_model_spec_is_a_configuration_fault(
        self,
        mocker: MockerFixture,
        worker_kind: str,
        rules: ImgGenModelRules | None,
        error_match: str,
    ) -> None:
        """The job fails before any provider call, in the CONFIGURATION category, naming the model."""
        worker = _make_worker(mocker, worker_kind=worker_kind, rules=rules)

        with pytest.raises(ImgGenParameterError, match=error_match) as exc_info:
            await worker.gen_image(img_gen_job=make_img_gen_job())

        assert exc_info.value.error_category == InferenceErrorCategory.CONFIGURATION
        assert "misconfigured-image-model" in str(exc_info.value)
