from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_GOOGLE_MISSING_MSG = "The google-genai SDK is required in order to use Google Gemini API directly."
_GOOGLE_IMG_GEN_MISSING_MSG = "The google-genai SDK is required in order to use Google Gemini Image models."


def _make_google_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="google.genai", dependency_name="google-genai", extra="google", msg=_GOOGLE_MISSING_MSG)

    from pipelex.plugins.google.google_factory import GoogleFactory  # noqa: PLC0415
    from pipelex.plugins.google.google_llm_worker import GoogleLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GoogleFactory.make_google_client(backend=backend),
    )
    return GoogleLLMWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_google_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="google.genai", dependency_name="google-genai", extra="google", msg=_GOOGLE_IMG_GEN_MISSING_MSG)

    from pipelex.plugins.google.google_factory import GoogleFactory  # noqa: PLC0415
    from pipelex.plugins.google.google_img_gen_worker import GoogleImgGenWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GoogleFactory.make_google_client(backend=backend),
    )
    return GoogleImgGenWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class GooglePlugin:
    """Built-in driver for Google Gemini models (LLM + image generation) via the google-genai SDK."""

    name = "google"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="google", make_worker=_make_google_worker)
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk="google", make_worker=_make_google_img_gen_worker)
