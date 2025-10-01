from anthropic import AsyncAnthropic
from anthropic.types import ModelInfo

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicModelListingError, AnthropicSDKUnsupportedError
from pipelex.plugins.anthropic.anthropic_factory import AnthropicFactory
from pipelex.plugins.plugin_sdk_registry import Plugin


async def anthropic_list_available_models(plugin: Plugin, backend: InferenceBackend) -> list[ModelInfo]:
    """List available Anthropic models.

    Returns:
        List[ModelInfo]: A list of Anthropic model information objects

    """
    anthropic_client = AnthropicFactory.make_anthropic_client(plugin=plugin, backend=backend)
    if not hasattr(anthropic_client, "models"):
        msg = f"{type(anthropic_client).__name__} does not support listing models"
        raise AnthropicSDKUnsupportedError(msg)
    if not isinstance(anthropic_client, AsyncAnthropic):
        msg = "We only support the standard Anthropic client for listing models"
        raise AnthropicSDKUnsupportedError(msg)
    models_response = await anthropic_client.models.list()
    if not models_response:
        msg = "No models found"
        raise AnthropicModelListingError(msg)
    models_list = models_response.data
    if not models_list:
        msg = "No models found"
        raise AnthropicModelListingError(msg)
    return sorted(models_list, key=lambda model: model.created_at)
