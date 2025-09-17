from typing import List

from anthropic import AsyncAnthropic
from anthropic.types import ModelInfo

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicModelListingError, AnthropicSDKUnsupportedError
from pipelex.plugins.anthropic.anthropic_factory import AnthropicFactory
from pipelex.plugins.plugin_sdk_registry import Plugin


async def anthropic_list_anthropic_models(plugin: Plugin, backend: InferenceBackend) -> List[ModelInfo]:
    """
    List available Anthropic models.

    Returns:
        List[ModelInfo]: A list of Anthropic model information objects
    """
    anthropic_client = AnthropicFactory.make_anthropic_client(plugin=plugin, backend=backend)
    if not hasattr(anthropic_client, "models"):
        raise AnthropicSDKUnsupportedError(f"{type(anthropic_client).__name__} does not support listing models")
    if not isinstance(anthropic_client, AsyncAnthropic):
        raise AnthropicSDKUnsupportedError("We only support the standard Anthropic client for listing models")
    models_response = await anthropic_client.models.list()
    if not models_response:
        raise AnthropicModelListingError("No models found")
    models_list = models_response.data
    if not models_list:
        raise AnthropicModelListingError("No models found")
    return sorted(models_list, key=lambda model: model.created_at)
