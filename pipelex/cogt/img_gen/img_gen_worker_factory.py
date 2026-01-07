import importlib.util
from typing import TYPE_CHECKING

from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.exceptions import MissingDependencyError
from pipelex.hub import get_models_manager, get_plugin_manager
from pipelex.plugins.blackboxai.blackboxai_completions_factory import BlackboxaiCompletionsFactory
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.exceptions import CredentialsError


class FalCredentialsError(CredentialsError):
    pass


class ImgGenWorkerFactory:
    @classmethod
    def make_img_gen_worker(
        cls,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> ImgGenWorkerAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        img_gen_worker: ImgGenWorkerAbstract
        match plugin.sdk:
            case "gateway_img_gen":
                from pipelex.plugins.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415
                from pipelex.plugins.gateway.gateway_img_gen_worker import GatewayImgGenWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GatewayFactory.make_portkey_client(backend=backend),
                )

                img_gen_worker = GatewayImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "fal":
                if importlib.util.find_spec("fal_client") is None:
                    lib_name = "fal-client"
                    lib_extra_name = "fal"
                    msg = "The fal-client SDK is required in order to use FAL models (generation of images)."
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from fal_client import AsyncClient as FalAsyncClient  # noqa: PLC0415

                from pipelex.plugins.fal.fal_img_gen_worker import FalImgGenWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=FalAsyncClient(key=backend.api_key),
                )

                img_gen_worker = FalImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "huggingface_img_gen":
                from huggingface_hub import AsyncInferenceClient  # noqa: PLC0415

                from pipelex.plugins.huggingface.huggingface_factory import HuggingFaceFactory  # noqa: PLC0415
                from pipelex.plugins.huggingface.huggingface_img_gen_worker import HuggingFaceImgGenWorker  # noqa: PLC0415

                if TYPE_CHECKING:
                    from huggingface_hub.inference._providers import PROVIDER_OR_POLICY_T  # noqa: PLC0415

                provider_literal: PROVIDER_OR_POLICY_T
                if provider_str := plugin.variant:
                    provider_literal = HuggingFaceFactory.make_huggingface_inference_provider(provider_str=provider_str)
                else:
                    provider_literal = "auto"
                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=AsyncInferenceClient(
                        provider=provider_literal,
                        token=backend.api_key,
                    ),
                )

                img_gen_worker = HuggingFaceImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "openai_img_gen":
                from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_img_gen_worker import OpenAIImgGenWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIClientFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                img_gen_worker = OpenAIImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "blackboxai_img_gen":
                from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIClientFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                openai_completions_factory = BlackboxaiCompletionsFactory(is_http_url_enabled=True)

                img_gen_worker = OpenAICompletionsImgGenWorker(
                    openai_completions_factory=openai_completions_factory,
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "azure_rest_img_gen":
                from pipelex.plugins.azure_rest.azure_img_gen_worker import AzureImgGenWorker  # noqa: PLC0415

                img_gen_worker = AzureImgGenWorker(
                    plugin=plugin,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "google":
                if importlib.util.find_spec("google.genai") is None:
                    lib_name = "google-genai"
                    lib_extra_name = "google"
                    msg = (
                        "The google-genai SDK is required in order to use Google Gemini Image models. "
                        "You can install it with 'pip install google-genai'."
                    )
                    raise MissingDependencyError(
                        lib_name,
                        lib_extra_name,
                        msg,
                    )

                from pipelex.plugins.google.google_factory import GoogleFactory  # noqa: PLC0415
                from pipelex.plugins.google.google_img_gen_worker import GoogleImgGenWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GoogleFactory.make_google_client(backend=backend),
                )

                img_gen_worker = GoogleImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "gateway_completions":
                from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=GatewayCompletionsFactory.make_portkey_openai_client_for_completions(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                gateway_completions_factory = GatewayCompletionsFactory(is_http_url_enabled=False)

                img_gen_worker = OpenAICompletionsImgGenWorker(
                    openai_completions_factory=gateway_completions_factory,
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                msg = f"Plugin '{plugin}' is not supported for image generation"
                raise NotImplementedError(msg)

        return img_gen_worker
