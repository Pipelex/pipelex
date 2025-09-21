from typing import Optional

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_models_manager, get_plugin_manager, get_secret
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError


class FalCredentialsError(CogtError):
    pass


class ImggWorkerFactory:
    def make_imgg_worker(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ) -> ImggWorkerAbstract:
        plugin = Plugin.make_for_inference_model(inference_model=inference_model)
        backend = get_models_manager().get_required_inference_backend(inference_model.backend_name)
        plugin_sdk_registry = get_plugin_manager().plugin_sdk_registry
        imgg_worker: ImggWorkerAbstract
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

                from pipelex.plugins.fal.fal_imgg_worker import FalImggWorker

                imgg_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=FalAsyncClient(key=fal_api_key),
                )

                imgg_worker = FalImggWorker(
                    sdk_instance=imgg_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case "openai":
                from pipelex.plugins.openai.openai_factory import OpenAIFactory
                from pipelex.plugins.openai.openai_imgg_worker import OpenAIImggWorker

                imgg_sdk_instance = plugin_sdk_registry.get_sdk_instance(plugin=plugin) or plugin_sdk_registry.set_sdk_instance(
                    plugin=plugin,
                    sdk_instance=OpenAIFactory.make_openai_client(
                        plugin=plugin,
                        backend=backend,
                    ),
                )

                imgg_worker = OpenAIImggWorker(
                    sdk_instance=imgg_sdk_instance,
                    inference_model=inference_model,
                    reporting_delegate=reporting_delegate,
                )
            case _:
                raise NotImplementedError(f"Plugin '{plugin}' is not supported for image generation")

        return imgg_worker
