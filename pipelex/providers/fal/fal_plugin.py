from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_FAL_MISSING_MSG = "The fal-client SDK is required in order to use FAL models (generation of images)."


def _make_fal_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="fal_client", dependency_name="fal-client", extra="fal", msg=_FAL_MISSING_MSG)

    from fal_client import AsyncClient as FalAsyncClient  # ruff: ignore[import-outside-top-level]

    from pipelex.providers.fal.fal_img_gen_worker import FalImgGenWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: FalAsyncClient(key=backend.api_key),
    )
    return FalImgGenWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class FalPlugin:
    """Built-in driver for FAL image generation models via the fal-client SDK."""

    name = "fal"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk="fal", make_worker=_make_fal_img_gen_worker)
