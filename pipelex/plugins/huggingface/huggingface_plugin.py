from typing import TYPE_CHECKING

from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

if TYPE_CHECKING:
    from huggingface_hub.inference._providers import PROVIDER_OR_POLICY_T

_HUGGINGFACE_MISSING_MSG = "The huggingface_hub SDK is required in order to use HuggingFace image generation models."


def _make_huggingface_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="huggingface_hub", extra="huggingface", msg=_HUGGINGFACE_MISSING_MSG)

    from huggingface_hub import AsyncInferenceClient  # noqa: PLC0415

    from pipelex.plugins.huggingface.huggingface_factory import HuggingFaceFactory  # noqa: PLC0415
    from pipelex.plugins.huggingface.huggingface_img_gen_worker import HuggingFaceImgGenWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    provider_literal: PROVIDER_OR_POLICY_T
    if provider_str := model_handle.variant:
        provider_literal = HuggingFaceFactory.make_huggingface_inference_provider(provider_str=provider_str)
    else:
        provider_literal = "auto"
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: AsyncInferenceClient(provider=provider_literal, token=backend.api_key),
    )
    return HuggingFaceImgGenWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class HuggingFacePlugin:
    """Built-in driver for HuggingFace image generation models via the huggingface_hub SDK."""

    name = "huggingface"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk="huggingface_img_gen", make_worker=_make_huggingface_img_gen_worker)
