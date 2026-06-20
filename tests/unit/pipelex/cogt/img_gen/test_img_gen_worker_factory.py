"""Routing tests for ImgGenWorkerFactory: each SDK string must build the right image
generation worker with the right SDK client, completions factory, and reporting delegate,
while caching the SDK instance in the SDK client registry.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.img_gen.img_gen_worker_factory import ImgGenWorkerFactory
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.exceptions import MissingDependencyError
from pipelex.plugins.blackboxai.blackboxai_completions_factory import BlackboxaiCompletionsFactory
from pipelex.plugins.builtins import BUILTIN_PLUGINS
from pipelex.plugins.exceptions import InferenceBackendNotFoundError
from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.plugins.openrouter.openrouter_completions_factory import OpenRouterCompletionsFactory
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelexConfig


def build_builtin_inference_backend_registry() -> InferenceBackendRegistry:
    """Register the built-in driver plugins into a fresh registrar and snapshot the backends.

    This is exactly what boot does, so the routing tests below exercise the real
    plugin closures through the real registry lookup.
    """
    # Stub config exposing only what a builtin's register() reads: TemporalPlugin checks
    # ``config.temporal.is_enabled`` (False here → no slot claims, inference unaffected).
    stub_config = cast("PipelexConfig", SimpleNamespace(temporal=SimpleNamespace(is_enabled=False)))
    registrar = PluginRegistrar(config=stub_config)
    for plugin in BUILTIN_PLUGINS:
        plugin.register(registrar)
    return InferenceBackendRegistry(registrar.inference_backends)


FACTORY_MODULE = "pipelex.cogt.img_gen.img_gen_worker_factory"

GATEWAY_CLIENT = "pipelex.plugins.gateway.gateway_factory.GatewayFactory.make_portkey_client"
GATEWAY_COMPLETIONS_CLIENT = (
    "pipelex.plugins.gateway.gateway_completions_factory.GatewayCompletionsFactory.make_portkey_openai_client_for_completions"
)
OPENAI_CLIENT = "pipelex.plugins.openai.openai_client_factory.OpenAIClientFactory.make_openai_client"
GOOGLE_CLIENT = "pipelex.plugins.google.google_factory.GoogleFactory.make_google_client"
HUGGINGFACE_PROVIDER = "pipelex.plugins.huggingface.huggingface_factory.HuggingFaceFactory.make_huggingface_inference_provider"

GATEWAY_WORKER = "pipelex.plugins.gateway.gateway_img_gen_worker.GatewayImgGenWorker"
FAL_WORKER = "pipelex.plugins.fal.fal_img_gen_worker.FalImgGenWorker"
HUGGINGFACE_WORKER = "pipelex.plugins.huggingface.huggingface_img_gen_worker.HuggingFaceImgGenWorker"
OPENAI_WORKER = "pipelex.plugins.openai.openai_img_gen_worker.OpenAIImgGenWorker"
COMPLETIONS_WORKER = "pipelex.plugins.openai.openai_completions_img_gen_worker.OpenAICompletionsImgGenWorker"
AZURE_WORKER = "pipelex.plugins.azure_rest.azure_img_gen_worker.AzureImgGenWorker"
GOOGLE_WORKER = "pipelex.plugins.google.google_img_gen_worker.GoogleImgGenWorker"


def make_img_gen_model_spec(sdk: str, backend_name: str = "test_backend", variant: str | None = None) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name="test-img-model",
        sdk=sdk,
        variant=variant,
        model_type=ModelType.IMG_GEN,
        model_id="test-img-model-id",
        inputs=["text"],
        outputs=["image"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def make_backend(name: str = "test_backend") -> InferenceBackend:
    return InferenceBackend(
        name=name,
        api_key="test-key",
        extra_config={"api_version": "2024-02-01"},
    )


def patch_hub_getters(
    mocker: MockerFixture,
    backend: InferenceBackend,
) -> SdkClientRegistry:
    """Patch hub getters at the worker-factory namespace; return the fresh SDK registry."""
    registry = SdkClientRegistry()
    models_manager = mocker.MagicMock()
    models_manager.get_required_inference_backend.return_value = backend
    mocker.patch(f"{FACTORY_MODULE}.get_models_manager", return_value=models_manager)
    sdk_client_manager = mocker.MagicMock()
    sdk_client_manager.sdk_client_registry = registry
    mocker.patch(f"{FACTORY_MODULE}.get_sdk_client_manager", return_value=sdk_client_manager)
    mocker.patch(f"{FACTORY_MODULE}.get_inference_backend_registry", return_value=build_builtin_inference_backend_registry())
    return registry


class TestImgGenWorkerFactory:
    @pytest.mark.parametrize(
        ("sdk", "client_target", "worker_target", "factory_cls", "http_flag", "passes_model_handle"),
        [
            pytest.param("gateway_img_gen", GATEWAY_CLIENT, GATEWAY_WORKER, None, None, False, id="gateway_img_gen"),
            pytest.param("openai_img_gen", OPENAI_CLIENT, OPENAI_WORKER, None, None, True, id="openai_img_gen"),
            pytest.param("blackboxai_img_gen", OPENAI_CLIENT, COMPLETIONS_WORKER, BlackboxaiCompletionsFactory, True, True, id="blackboxai_img_gen"),
            pytest.param("openrouter_img_gen", OPENAI_CLIENT, COMPLETIONS_WORKER, OpenRouterCompletionsFactory, True, True, id="openrouter_img_gen"),
            pytest.param(
                "gateway_completions",
                GATEWAY_COMPLETIONS_CLIENT,
                COMPLETIONS_WORKER,
                GatewayCompletionsFactory,
                False,
                True,
                id="gateway_completions",
            ),
            pytest.param("google", GOOGLE_CLIENT, GOOGLE_WORKER, None, None, False, id="google"),
        ],
    )
    def test_routing_builds_expected_worker(
        self,
        mocker: MockerFixture,
        sdk: str,
        client_target: str,
        worker_target: str,
        factory_cls: type | None,
        http_flag: bool | None,
        passes_model_handle: bool,
    ) -> None:
        """Each SDK string routes to its image generation worker with the SDK client wired in."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk=sdk)
        sdk_client = mocker.MagicMock(name="sdk_client")
        client_factory_mock = mocker.patch(client_target, return_value=sdk_client)
        worker_cls_mock = mocker.patch(worker_target)
        reporting_delegate = mocker.MagicMock(name="reporting_delegate")

        worker = ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model, reporting_delegate=reporting_delegate)

        client_factory_mock.assert_called_once()
        client_kwargs = client_factory_mock.call_args.kwargs
        assert client_kwargs["backend"] is backend
        if passes_model_handle:
            assert client_kwargs["model_handle"] == ModelHandle(sdk=sdk, backend="test_backend", variant=None)

        worker_cls_mock.assert_called_once()
        worker_kwargs = worker_cls_mock.call_args.kwargs
        assert worker_kwargs["sdk_instance"] is sdk_client
        assert worker_kwargs["inference_model"] is inference_model
        assert worker_kwargs["reporting_delegate"] is reporting_delegate
        assert worker is worker_cls_mock.return_value

        if factory_cls is not None:
            built_factory = worker_kwargs["openai_completions_factory"]
            assert type(built_factory) is factory_cls
            assert isinstance(built_factory, OpenAICompletionsFactory)
            assert built_factory.is_http_url_enabled is http_flag

    def test_fal_builds_async_client_with_api_key(self, mocker: MockerFixture) -> None:
        """The fal SDK string builds a FalImgGenWorker around an AsyncClient keyed with the backend api_key."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk="fal")
        fal_client_mock = mocker.patch("fal_client.AsyncClient")
        worker_cls_mock = mocker.patch(FAL_WORKER)

        worker = ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model)

        fal_client_mock.assert_called_once_with(key="test-key")
        worker_cls_mock.assert_called_once()
        worker_kwargs = worker_cls_mock.call_args.kwargs
        assert worker_kwargs["sdk_instance"] is fal_client_mock.return_value
        assert worker_kwargs["inference_model"] is inference_model
        assert worker_kwargs["reporting_delegate"] is None
        assert worker is worker_cls_mock.return_value

    def test_huggingface_with_variant_resolves_provider(self, mocker: MockerFixture) -> None:
        """A huggingface variant is mapped to a provider via HuggingFaceFactory and passed to the client."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk="huggingface_img_gen", variant="fal-ai")
        provider_mock = mocker.patch(HUGGINGFACE_PROVIDER, return_value="fal-ai")
        hf_client_mock = mocker.patch("huggingface_hub.AsyncInferenceClient")
        worker_cls_mock = mocker.patch(HUGGINGFACE_WORKER)

        ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model)

        provider_mock.assert_called_once_with(provider_str="fal-ai")
        hf_client_mock.assert_called_once_with(provider="fal-ai", token="test-key")
        worker_cls_mock.assert_called_once()
        assert worker_cls_mock.call_args.kwargs["sdk_instance"] is hf_client_mock.return_value

    def test_huggingface_without_variant_uses_auto_provider(self, mocker: MockerFixture) -> None:
        """Without a variant, the huggingface client gets the auto provider policy."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk="huggingface_img_gen", variant=None)
        provider_mock = mocker.patch(HUGGINGFACE_PROVIDER)
        hf_client_mock = mocker.patch("huggingface_hub.AsyncInferenceClient")
        worker_cls_mock = mocker.patch(HUGGINGFACE_WORKER)

        ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model)

        provider_mock.assert_not_called()
        hf_client_mock.assert_called_once_with(provider="auto", token="test-key")
        worker_cls_mock.assert_called_once()
        assert worker_cls_mock.call_args.kwargs["sdk_instance"] is hf_client_mock.return_value

    def test_azure_rest_builds_worker_without_registry(self, mocker: MockerFixture) -> None:
        """The azure_rest SDK constructs the worker directly: no SDK instance is registered."""
        backend = make_backend()
        registry = patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk="azure_rest_img_gen")
        worker_cls_mock = mocker.patch(AZURE_WORKER)
        reporting_delegate = mocker.MagicMock(name="reporting_delegate")

        worker = ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model, reporting_delegate=reporting_delegate)

        worker_cls_mock.assert_called_once_with(
            model_handle=ModelHandle(sdk="azure_rest_img_gen", backend="test_backend", variant=None),
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        assert worker is worker_cls_mock.return_value
        assert registry.root == {}

    def test_cached_sdk_instance_skips_client_factory(self, mocker: MockerFixture) -> None:
        """A pre-seeded registry entry is reused: the client factory must not be called."""
        backend = make_backend()
        registry = patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk="gateway_img_gen")
        model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
        cached_client = mocker.MagicMock(name="cached_client")
        registry.set(model_handle=model_handle, sdk_instance=cached_client)
        client_factory_mock = mocker.patch(GATEWAY_CLIENT)
        worker_cls_mock = mocker.patch(GATEWAY_WORKER)

        ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model)

        client_factory_mock.assert_not_called()
        worker_cls_mock.assert_called_once()
        assert worker_cls_mock.call_args.kwargs["sdk_instance"] is cached_client

    @pytest.mark.parametrize(
        ("sdk", "expected_extra"),
        [
            pytest.param("fal", "fal", id="fal"),
            pytest.param("google", "google", id="google"),
            pytest.param("huggingface_img_gen", "huggingface", id="huggingface_img_gen"),
        ],
    )
    def test_missing_dependency_raises(self, mocker: MockerFixture, sdk: str, expected_extra: str) -> None:
        """When the optional SDK is absent, the factory raises MissingDependencyError naming the extra."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk=sdk)
        mocker.patch("importlib.util.find_spec", return_value=None)

        with pytest.raises(MissingDependencyError) as exc_info:
            ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model)

        assert exc_info.value.extra_name == expected_extra
        assert f"pipelex[{expected_extra}]" in str(exc_info.value)

    def test_unknown_sdk_raises_backend_not_found(self, mocker: MockerFixture) -> None:
        """An unrecognized SDK string raises a structured InferenceBackendNotFoundError naming the SDK (a registry miss)."""
        backend = make_backend()
        patch_hub_getters(mocker, backend=backend)
        inference_model = make_img_gen_model_spec(sdk="definitely_not_an_sdk")

        with pytest.raises(InferenceBackendNotFoundError) as exc_info:
            ImgGenWorkerFactory.make_img_gen_worker(inference_model=inference_model)

        assert exc_info.value.sdk == "definitely_not_an_sdk"
        assert "definitely_not_an_sdk" in str(exc_info.value)
        assert "Is its plugin installed and enabled?" in str(exc_info.value)
