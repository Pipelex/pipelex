"""Routing tests for LLMWorkerFactory: each plugin SDK string must build the right worker
with the right SDK client, completions/responses factory, and reporting delegate, while
caching the SDK instance in the plugin SDK registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.exceptions import MissingDependencyError
from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.gateway.gateway_responses_factory import GatewayResponsesFactory
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.plugins.plugin_sdk_registry import Plugin, PluginSdkRegistry
from pipelex.plugins.portkey.portkey_completions_factory import PortkeyCompletionsFactory
from pipelex.plugins.portkey.portkey_responses_factory import PortkeyResponsesFactory

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

FACTORY_MODULE = "pipelex.cogt.llm.llm_worker_factory"

GATEWAY_COMPLETIONS_CLIENT = (
    "pipelex.plugins.gateway.gateway_completions_factory.GatewayCompletionsFactory.make_portkey_openai_client_for_completions"
)
GATEWAY_RESPONSES_CLIENT = "pipelex.plugins.gateway.gateway_responses_factory.GatewayResponsesFactory.make_portkey_openai_client_for_responses"
PORTKEY_COMPLETIONS_CLIENT = (
    "pipelex.plugins.portkey.portkey_completions_factory.PortkeyCompletionsFactory.make_portkey_openai_client_for_completions"
)
PORTKEY_RESPONSES_CLIENT = "pipelex.plugins.portkey.portkey_responses_factory.PortkeyResponsesFactory.make_portkey_openai_client_for_responses"
OPENAI_CLIENT = "pipelex.plugins.openai.openai_client_factory.OpenAIClientFactory.make_openai_client"
ANTHROPIC_CLIENT = "pipelex.plugins.anthropic.anthropic_factory.AnthropicFactory.make_anthropic_client"
MISTRAL_CLIENT = "pipelex.plugins.mistral.mistral_factory.MistralFactory.make_mistral_client"
BEDROCK_CLIENT = "pipelex.plugins.bedrock.bedrock_factory.BedrockFactory.make_bedrock_client"
GOOGLE_CLIENT = "pipelex.plugins.google.google_factory.GoogleFactory.make_google_client"

COMPLETIONS_WORKER = "pipelex.plugins.openai.openai_completions_llm_worker.OpenAICompletionsLLMWorker"
RESPONSES_WORKER = "pipelex.plugins.openai.openai_responses_llm_worker.OpenAIResponsesLLMWorker"
ANTHROPIC_WORKER = "pipelex.plugins.anthropic.anthropic_llm_worker.AnthropicLLMWorker"
MISTRAL_WORKER = "pipelex.plugins.mistral.mistral_llm_worker.MistralLLMWorker"
BEDROCK_WORKER = "pipelex.plugins.bedrock.bedrock_llm_worker.BedrockLLMWorker"
GOOGLE_WORKER = "pipelex.plugins.google.google_llm_worker.GoogleLLMWorker"


def make_llm_model_spec(sdk: str, backend_name: str = "test_backend") -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name="test-model",
        sdk=sdk,
        model_type=ModelType.LLM,
        model_id="test-model-id",
        inputs=["text"],
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def make_backend(name: str = "test_backend") -> InferenceBackend:
    return InferenceBackend(
        name=name,
        api_key="test-key",
        extra_config={"region_name": "us-east-1"},
    )


def patch_hub_getters(
    mocker: MockerFixture,
    backend: InferenceBackend,
) -> PluginSdkRegistry:
    """Patch hub getters at the worker-factory namespace; return the fresh SDK registry."""
    registry = PluginSdkRegistry()
    models_manager = mocker.MagicMock()
    models_manager.get_required_inference_backend.return_value = backend
    mocker.patch(f"{FACTORY_MODULE}.get_models_manager", return_value=models_manager)
    plugin_manager = mocker.MagicMock()
    plugin_manager.plugin_sdk_registry = registry
    mocker.patch(f"{FACTORY_MODULE}.get_plugin_manager", return_value=plugin_manager)
    return registry


class TestLLMWorkerFactory:
    @pytest.mark.parametrize(
        ("sdk", "client_target", "worker_target", "factory_field", "factory_cls", "http_flag", "passes_plugin", "expects_extra_config"),
        [
            pytest.param(
                "gateway_completions",
                GATEWAY_COMPLETIONS_CLIENT,
                COMPLETIONS_WORKER,
                "openai_completions_factory",
                GatewayCompletionsFactory,
                False,
                True,
                False,
                id="gateway_completions",
            ),
            pytest.param(
                "gateway_responses",
                GATEWAY_RESPONSES_CLIENT,
                RESPONSES_WORKER,
                "openai_responses_factory",
                GatewayResponsesFactory,
                False,
                True,
                False,
                id="gateway_responses",
            ),
            pytest.param(
                "portkey_completions",
                PORTKEY_COMPLETIONS_CLIENT,
                COMPLETIONS_WORKER,
                "openai_completions_factory",
                PortkeyCompletionsFactory,
                False,
                True,
                False,
                id="portkey_completions",
            ),
            pytest.param(
                "portkey_responses",
                PORTKEY_RESPONSES_CLIENT,
                RESPONSES_WORKER,
                "openai_responses_factory",
                PortkeyResponsesFactory,
                False,
                True,
                False,
                id="portkey_responses",
            ),
            pytest.param(
                "openai",
                OPENAI_CLIENT,
                COMPLETIONS_WORKER,
                "openai_completions_factory",
                OpenAICompletionsFactory,
                True,
                True,
                False,
                id="openai",
            ),
            pytest.param(
                "azure_openai",
                OPENAI_CLIENT,
                COMPLETIONS_WORKER,
                "openai_completions_factory",
                OpenAICompletionsFactory,
                True,
                True,
                False,
                id="azure_openai",
            ),
            pytest.param(
                "openai_responses",
                OPENAI_CLIENT,
                RESPONSES_WORKER,
                "openai_responses_factory",
                OpenAIResponsesFactory,
                True,
                True,
                False,
                id="openai_responses",
            ),
            pytest.param(
                "azure_openai_responses",
                OPENAI_CLIENT,
                RESPONSES_WORKER,
                "openai_responses_factory",
                OpenAIResponsesFactory,
                True,
                True,
                False,
                id="azure_openai_responses",
            ),
            pytest.param("anthropic", ANTHROPIC_CLIENT, ANTHROPIC_WORKER, None, None, None, True, True, id="anthropic"),
            pytest.param("bedrock_anthropic", ANTHROPIC_CLIENT, ANTHROPIC_WORKER, None, None, None, True, True, id="bedrock_anthropic"),
            pytest.param("mistral", MISTRAL_CLIENT, MISTRAL_WORKER, "mistral_factory", MistralFactory, None, False, False, id="mistral"),
            pytest.param("bedrock_boto3", BEDROCK_CLIENT, BEDROCK_WORKER, None, None, None, True, False, id="bedrock_boto3"),
            pytest.param("bedrock_aioboto3", BEDROCK_CLIENT, BEDROCK_WORKER, None, None, None, True, False, id="bedrock_aioboto3"),
            pytest.param("google", GOOGLE_CLIENT, GOOGLE_WORKER, None, None, None, False, False, id="google"),
        ],
    )
    def test_routing_builds_expected_worker(
        self,
        mocker: MockerFixture,
        sdk: str,
        client_target: str,
        worker_target: str,
        factory_field: str | None,
        factory_cls: type | None,
        http_flag: bool | None,
        passes_plugin: bool,
        expects_extra_config: bool,
    ) -> None:
        """Each SDK string routes to its worker class with the SDK client and factory wired in."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_llm_model_spec(sdk=sdk)
        sdk_client = mocker.MagicMock(name="sdk_client")
        client_factory_mock = mocker.patch(client_target, return_value=sdk_client)
        worker_cls_mock = mocker.patch(worker_target)
        reporting_delegate = mocker.MagicMock(name="reporting_delegate")

        worker = LLMWorkerFactory.make_llm_worker(inference_model=inference_model, reporting_delegate=reporting_delegate)

        client_factory_mock.assert_called_once()
        client_kwargs = client_factory_mock.call_args.kwargs
        assert client_kwargs["backend"] is backend
        if passes_plugin:
            assert client_kwargs["plugin"] == Plugin(sdk=sdk, backend="test_backend", variant=None)

        worker_cls_mock.assert_called_once()
        worker_kwargs = worker_cls_mock.call_args.kwargs
        assert worker_kwargs["sdk_instance"] is sdk_client
        assert worker_kwargs["inference_model"] is inference_model
        assert worker_kwargs["reporting_delegate"] is reporting_delegate
        assert worker is worker_cls_mock.return_value

        if factory_field is not None:
            assert factory_cls is not None
            built_factory = worker_kwargs[factory_field]
            assert type(built_factory) is factory_cls
            if http_flag is not None:
                assert isinstance(built_factory, (OpenAICompletionsFactory, OpenAIResponsesFactory))
                assert built_factory.is_http_url_enabled is http_flag

        if expects_extra_config:
            assert worker_kwargs["extra_config"] is backend.extra_config

    def test_cached_sdk_instance_skips_client_factory(self, mocker: MockerFixture) -> None:
        """A pre-seeded registry entry is reused: the client factory must not be called."""
        backend = make_backend()
        registry = patch_hub_getters(mocker, backend=backend)
        inference_model = make_llm_model_spec(sdk="openai")
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        cached_client = mocker.MagicMock(name="cached_client")
        registry.set_sdk_instance(plugin=plugin, sdk_instance=cached_client)
        client_factory_mock = mocker.patch(OPENAI_CLIENT)
        worker_cls_mock = mocker.patch(COMPLETIONS_WORKER)

        LLMWorkerFactory.make_llm_worker(inference_model=inference_model)

        client_factory_mock.assert_not_called()
        worker_cls_mock.assert_called_once()
        assert worker_cls_mock.call_args.kwargs["sdk_instance"] is cached_client

    def test_cold_registry_creates_then_reuses_sdk_instance(self, mocker: MockerFixture) -> None:
        """A cold registry triggers one client build; a second call reuses the cached instance."""
        backend = make_backend()
        registry = patch_hub_getters(mocker, backend=backend)
        inference_model = make_llm_model_spec(sdk="openai")
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        sdk_client = mocker.MagicMock(name="sdk_client")
        client_factory_mock = mocker.patch(OPENAI_CLIENT, return_value=sdk_client)
        worker_cls_mock = mocker.patch(COMPLETIONS_WORKER)

        LLMWorkerFactory.make_llm_worker(inference_model=inference_model)
        LLMWorkerFactory.make_llm_worker(inference_model=inference_model)

        client_factory_mock.assert_called_once()
        assert registry.get_sdk_instance(plugin=plugin) is sdk_client
        first_kwargs, second_kwargs = (call.kwargs for call in worker_cls_mock.call_args_list)
        assert first_kwargs["sdk_instance"] is sdk_client
        assert second_kwargs["sdk_instance"] is sdk_client

    @pytest.mark.parametrize(
        ("sdk", "expected_extra"),
        [
            pytest.param("anthropic", "anthropic", id="anthropic"),
            pytest.param("bedrock_anthropic", "anthropic", id="bedrock_anthropic"),
            pytest.param("mistral", "mistral", id="mistral"),
            pytest.param("bedrock_boto3", "bedrock", id="bedrock_boto3"),
            pytest.param("bedrock_aioboto3", "bedrock", id="bedrock_aioboto3"),
            pytest.param("google", "google", id="google"),
        ],
    )
    def test_missing_dependency_raises(self, mocker: MockerFixture, sdk: str, expected_extra: str) -> None:
        """When the optional SDK is absent, the factory raises MissingDependencyError naming the extra."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_llm_model_spec(sdk=sdk)
        mocker.patch("importlib.util.find_spec", return_value=None)

        with pytest.raises(MissingDependencyError) as exc_info:
            LLMWorkerFactory.make_llm_worker(inference_model=inference_model)

        assert exc_info.value.extra_name == expected_extra
        assert f"pipelex[{expected_extra}]" in str(exc_info.value)

    def test_unknown_sdk_raises_not_implemented(self, mocker: MockerFixture) -> None:
        """An unrecognized SDK string raises NotImplementedError naming the plugin."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_llm_model_spec(sdk="definitely_not_an_sdk")

        with pytest.raises(NotImplementedError) as exc_info:
            LLMWorkerFactory.make_llm_worker(inference_model=inference_model)

        assert "definitely_not_an_sdk" in str(exc_info.value)
        assert "is not supported" in str(exc_info.value)
