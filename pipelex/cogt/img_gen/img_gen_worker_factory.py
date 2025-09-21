from typing import Optional

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_models_manager, get_plugin_manager, get_secret
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError


class FalCredentialsError(CogtError):
    pass


class ImgGenWorkerFactory:
    def make_img_gen_worker(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> ImgGenWorkerAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        img_gen_worker: ImgGenWorkerAbstract
        match plugin.sdk:
            case "fal":
                try:
                    fal_api_key = get_secret(secret_id="FAL_API_KEY")
                except SecretNotFoundError as exc:
                    raise FalCredentialsError("FAL_API_KEY not found") from exc

                try:
                    from fal_client import AsyncClient as FalAsyncClient
                except ImportError as exc:
                    raise MissingDependencyError(
                        "fal-client", "fal", "The fal-client SDK is required to use FAL models (generation of images)."
                    ) from exc

                from pipelex.plugins.fal.fal_img_gen_worker import FalImgGenWorker

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=FalAsyncClient(key=fal_api_key),
                )

                img_gen_worker = FalImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "openai":
                from pipelex.plugins.openai.openai_factory import OpenAIFactory
                from pipelex.plugins.openai.openai_img_gen_worker import OpenAIImgGenWorker

                img_gen_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                img_gen_worker = OpenAIImgGenWorker(
                    sdk_instance=img_gen_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                raise NotImplementedError(f"Plugin '{plugin}' is not supported for image generation")

        return img_gen_worker
