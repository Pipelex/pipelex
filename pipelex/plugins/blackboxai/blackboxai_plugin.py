from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_blackboxai_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.plugins.blackboxai.blackboxai_completions_factory import BlackboxaiCompletionsFactory  # noqa: PLC0415
    from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
    from pipelex.plugins.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: OpenAIClientFactory.make_openai_client(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsImgGenWorker(
        openai_completions_factory=BlackboxaiCompletionsFactory(is_http_url_enabled=True),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class BlackboxaiPlugin:
    """Built-in driver for Blackbox AI image generation via the OpenAI-completions substrate."""

    name = "blackboxai"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk="blackboxai_img_gen", make_worker=_make_blackboxai_img_gen_worker)
