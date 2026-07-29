from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_azure_rest_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,  # noqa: ARG001 - uniform MakeWorkerFn signature; this REST worker builds its own client
    sdk_clients: SdkClientRegistry,  # noqa: ARG001 - direct construction, no SDK-client caching
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.azure_rest.azure_img_gen_worker import AzureImgGenWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    return AzureImgGenWorker(
        model_handle=model_handle,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class AzureRestPlugin:
    """Built-in driver for Azure OpenAI image generation via the REST worker (no SDK client cache)."""

    name = "azure_rest"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk="azure_rest_img_gen", make_worker=_make_azure_rest_img_gen_worker)
