from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_MISTRAL_MISSING_MSG = (
    "The mistralai SDK is required in order to use Mistral models through the mistralai client. "
    "However, you can use Mistral models through bedrock directly "
    "by using the 'bedrock-mistral' llm family. (eg: bedrock-mistral-large)"
)
_MISTRAL_EXTRACT_MISSING_MSG = "The mistralai SDK is required in order to use Mistral OCR models through the mistralai client."


def _make_mistral_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="mistralai", extra="mistral", msg=_MISTRAL_MISSING_MSG)

    from pipelex.providers.mistral.mistral_factory import MistralFactory  # noqa: PLC0415
    from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: MistralFactory.make_mistral_client(backend=backend),
    )
    return MistralLLMWorker(
        mistral_factory=MistralFactory(),
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


def _make_mistral_extract_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="mistralai", extra="mistral", msg=_MISTRAL_EXTRACT_MISSING_MSG)

    from pipelex.providers.mistral.mistral_extract_worker import MistralExtractWorker  # noqa: PLC0415
    from pipelex.providers.mistral.mistral_factory import MistralFactory  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: MistralFactory.make_mistral_client(backend=backend),
    )
    return MistralExtractWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


# Async to satisfy the uniform ListModelsFn contract (the loop awaits it) even though Mistral lists synchronously.
async def _list_mistral_models(  # noqa: RUF029
    *,
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,  # noqa: ARG001 — uniform lister signature; Mistral lists without a backend client
    flat: bool,
    any_listed: bool,
) -> None:
    from pipelex.providers.mistral.mistral_list import list_mistral_models  # noqa: PLC0415

    list_mistral_models(sdk=sdk, backend_name=backend_name, flat=flat, any_listed=any_listed)


class MistralPlugin:
    """Built-in driver for Mistral models (LLM + OCR extraction) via the mistralai SDK."""

    name = "mistral"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="mistral", make_worker=_make_mistral_worker)
        registrar.add_inference_backend(family=InferenceFamily.EXTRACT, sdk="mistral", make_worker=_make_mistral_extract_worker)
        registrar.add_model_lister(sdk="mistral", lister=_list_mistral_models)
