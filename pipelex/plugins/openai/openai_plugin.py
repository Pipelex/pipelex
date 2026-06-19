from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_openai_completions_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
    from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory  # noqa: PLC0415
    from pipelex.plugins.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: OpenAIClientFactory.make_openai_client(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsLLMWorker(
        openai_completions_factory=OpenAICompletionsFactory(is_http_url_enabled=True),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_openai_responses_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.plugins.openai.openai_client_factory import OpenAIClientFactory  # noqa: PLC0415
    from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory  # noqa: PLC0415
    from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: OpenAIClientFactory.make_openai_client(model_handle=model_handle, backend=backend),
    )
    return OpenAIResponsesLLMWorker(
        openai_responses_factory=OpenAIResponsesFactory(is_http_url_enabled=True),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class OpenAIPlugin:
    """Always-on built-in driver for OpenAI and Azure OpenAI (no optional SDK)."""

    name = "openai"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="openai", make_worker=_make_openai_completions_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="azure_openai", make_worker=_make_openai_completions_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="openai_responses", make_worker=_make_openai_responses_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="azure_openai_responses", make_worker=_make_openai_responses_worker)
