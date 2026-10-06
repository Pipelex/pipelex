from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.llm.llm_job_components import LLMJobParams, ReasoningEffort
from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS
from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry, InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.system.configuration.configs import PipelexConfig


def _build_registrar() -> PluginRegistrar:
    registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace()))
    for plugin in BUILTIN_PLUGINS:
        plugin.register(registrar)
    return registrar


class TestLLMRequestChecks:
    def test_every_built_in_llm_backend_registers_its_check(self) -> None:
        """Validation can check a model on any built-in LLM sdk against the worker that serves it."""
        registrar = _build_registrar()
        llm_sdks = {sdk for family, sdk in registrar.inference_backends if family == InferenceFamily.LLM}
        assert llm_sdks
        assert set(registrar.llm_request_checks) == llm_sdks

    @pytest.mark.parametrize(
        ("sdk", "worker_class"),
        [
            ("openai", OpenAICompletionsLLMWorker),
            ("azure_openai", OpenAICompletionsLLMWorker),
            ("openai_responses", OpenAIResponsesLLMWorker),
            ("azure_openai_responses", OpenAIResponsesLLMWorker),
            ("portkey_completions", OpenAICompletionsLLMWorker),
            ("portkey_responses", OpenAIResponsesLLMWorker),
            ("anthropic", AnthropicLLMWorker),
            ("bedrock_anthropic", AnthropicLLMWorker),
            ("mistral", MistralLLMWorker),
            ("google", GoogleLLMWorker),
            ("bedrock_boto3", BedrockLLMWorker),
            ("bedrock_aioboto", BedrockLLMWorker),
        ],
    )
    def test_each_check_is_the_check_of_the_worker_its_backend_builds(
        self, mocker: MockerFixture, sdk: str, worker_class: type[LLMWorkerAbstract]
    ) -> None:
        """The registered check delegates to the worker class's own check_request, which the worker runs before every call."""
        registrar = _build_registrar()
        registry = InferenceBackendRegistry(registrar.inference_backends, llm_request_checks=registrar.llm_request_checks)
        check_request = registry.lookup_llm_request_check(sdk=sdk)
        assert check_request is not None
        worker_check = mocker.patch.object(worker_class, "check_request")
        inference_model = cast("InferenceModelSpec", mocker.MagicMock())
        job_params = LLMJobParams(temperature=0.5, reasoning_effort=ReasoningEffort.HIGH)

        check_request(inference_model=inference_model, job_params=job_params, is_structured=True)

        worker_check.assert_called_once_with(inference_model=inference_model, job_params=job_params, is_structured=True)

    def test_a_check_outlives_a_family_swap_and_only_the_llm_family_records_one(self, mocker: MockerFixture) -> None:
        """Standing stub workers in for a family keeps the checks; a check registered on another family is never read."""
        registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace()))
        llm_check = mocker.MagicMock()
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="some_llm", make_worker=mocker.MagicMock(), check_llm_request=llm_check)
        registrar.add_inference_backend(
            family=InferenceFamily.IMG_GEN, sdk="some_img_gen", make_worker=mocker.MagicMock(), check_llm_request=mocker.MagicMock()
        )
        assert registrar.llm_request_checks == {"some_llm": llm_check}

        registry = InferenceBackendRegistry(registrar.inference_backends, llm_request_checks=registrar.llm_request_checks)
        swapped = registry.with_family(family=InferenceFamily.LLM, backends={})
        assert swapped.lookup_llm_request_check(sdk="some_llm") is llm_check
        assert swapped.lookup_llm_request_check(sdk="unregistered") is None
