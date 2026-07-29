from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_gateway_completions_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.gateway.gateway_completions_factory import GatewayCompletionsFactory  # noqa: PLC0415
    from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GatewayCompletionsFactory.make_portkey_openai_client_for_completions(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsLLMWorker(
        openai_completions_factory=GatewayCompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_gateway_responses_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.gateway.gateway_responses_factory import GatewayResponsesFactory  # noqa: PLC0415
    from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GatewayResponsesFactory.make_portkey_openai_client_for_responses(model_handle=model_handle, backend=backend),
    )
    return OpenAIResponsesLLMWorker(
        openai_responses_factory=GatewayResponsesFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_gateway_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415
    from pipelex.providers.gateway.gateway_img_gen_worker import GatewayImgGenWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GatewayFactory.make_portkey_client(backend=backend),
    )
    return GatewayImgGenWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_gateway_completions_img_gen_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.gateway.gateway_completions_factory import GatewayCompletionsFactory  # noqa: PLC0415
    from pipelex.providers.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GatewayCompletionsFactory.make_portkey_openai_client_for_completions(model_handle=model_handle, backend=backend),
    )
    return OpenAICompletionsImgGenWorker(
        openai_completions_factory=GatewayCompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_gateway_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.gateway.gateway_extract_worker import GatewayExtractWorker  # noqa: PLC0415
    from pipelex.providers.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GatewayFactory.make_portkey_client(backend=backend),
    )
    return GatewayExtractWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_gateway_search_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    from pipelex.providers.gateway.gateway_factory import GatewayFactory  # noqa: PLC0415
    from pipelex.providers.gateway.gateway_search_worker import GatewaySearchWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: GatewayFactory.make_portkey_client(backend=backend),
    )
    return GatewaySearchWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class GatewayPlugin:
    """Built-in driver for the Pipelex Gateway (OpenAI-compatible substrate), serving all inference families."""

    name = "gateway"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="gateway_completions", make_worker=_make_gateway_completions_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="gateway_responses", make_worker=_make_gateway_responses_worker)
        registrar.add_inference_backend(family=InferenceFamily.IMG_GEN, sdk="gateway_img_gen", make_worker=_make_gateway_img_gen_worker)
        registrar.add_inference_backend(
            family=InferenceFamily.IMG_GEN, sdk="gateway_completions", make_worker=_make_gateway_completions_img_gen_worker
        )
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk="gateway_extract", make_worker=_make_gateway_extract_worker)
        registrar.add_inference_backend(family=InferenceFamily.SEARCH, sdk="gateway_search", make_worker=_make_gateway_search_worker)
