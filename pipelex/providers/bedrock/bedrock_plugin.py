from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_BEDROCK_MISSING_MSG = "The boto3 and aioboto3 SDKs are required to use Bedrock models."


def _make_bedrock_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec=["boto3", "aioboto3"], extra="bedrock", msg=_BEDROCK_MISSING_MSG)

    from pipelex.providers.bedrock.bedrock_factory import BedrockFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: BedrockFactory.make_bedrock_client(model_handle=model_handle, backend=backend),
    )
    return BedrockLLMWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


# Async to satisfy the uniform ListModelsFn contract (the loop awaits it) even though Bedrock lists synchronously.
async def _list_bedrock_models(  # ruff: ignore[unused-async]
    *,
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    from pipelex.providers.bedrock.bedrock_list import list_bedrock_models  # ruff: ignore[import-outside-top-level]

    list_bedrock_models(sdk=sdk, backend_name=backend_name, backend=backend, flat=flat, any_listed=any_listed)


class BedrockPlugin:
    """Built-in driver for Bedrock models via boto3/aioboto3."""

    name = "bedrock"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="bedrock_boto3", make_worker=_make_bedrock_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="bedrock_aioboto3", make_worker=_make_bedrock_worker)
        registrar.add_model_lister(sdk="bedrock", lister=_list_bedrock_models)
        registrar.add_model_lister(sdk="bedrock_aioboto3", lister=_list_bedrock_models)
