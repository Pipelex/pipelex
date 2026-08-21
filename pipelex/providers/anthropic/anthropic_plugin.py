from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_ANTHROPIC_MISSING_MSG = (
    "The anthropic SDK is required in order to use Anthropic models via the anthropic client. "
    "However, you can use Anthropic models through bedrock directly "
    "by using the 'bedrock-anthropic-claude' llm family. (eg: bedrock-anthropic-claude)"
)


def _make_anthropic_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="anthropic", extra="anthropic", msg=_ANTHROPIC_MISSING_MSG)

    from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker  # ruff: ignore[import-outside-top-level]

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: AnthropicFactory.make_anthropic_client(model_handle=model_handle, backend=backend),
    )
    return AnthropicLLMWorker(
        sdk_instance=sdk_instance,
        extra_config=backend.extra_config,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


async def _list_anthropic_models(
    *,
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    from pipelex.cogt.exceptions import ModelListingUnsupportedError  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.anthropic.anthropic_exceptions import AnthropicSDKUnsupportedError  # ruff: ignore[import-outside-top-level]
    from pipelex.providers.anthropic.anthropic_list import list_anthropic_models  # ruff: ignore[import-outside-top-level]

    try:
        await list_anthropic_models(sdk=sdk, backend_name=backend_name, backend=backend, flat=flat, any_listed=any_listed)
    except AnthropicSDKUnsupportedError as exc:
        # Translate the vendor "this client variant can't list" into the core soft signal the
        # list-models loop understands, so core names no Anthropic-specific exception.
        raise ModelListingUnsupportedError(sdk=sdk) from exc


class AnthropicPlugin:
    """Built-in driver for Anthropic models via the anthropic SDK (also serves bedrock_anthropic)."""

    name = "anthropic"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="anthropic", make_worker=_make_anthropic_worker)
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="bedrock_anthropic", make_worker=_make_anthropic_worker)
        registrar.add_model_lister(sdk="anthropic", lister=_list_anthropic_models)
