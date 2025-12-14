import importlib.util

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_models_manager, get_plugin_manager
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
            case "openai_alt_img_gen":
                from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
                from pipelex.plugins.openai.openai_img_gen_alt_worker import OpenAIImgGenAlternativeWorker  # noqa: PLC0415

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIClientFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                img_gen_worker = OpenAIImgGenAlternativeWorker(
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
            case _:
                msg = f"Plugin '{plugin}' is not supported for image generation"
                raise NotImplementedError(msg)

        return img_gen_worker
