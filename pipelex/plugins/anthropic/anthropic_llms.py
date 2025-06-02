from typing import List

from anthropic import AsyncAnthropic
from anthropic.types import ModelInfo

from pipelex.cogt.exceptions import LLMModelProviderError, LLMSDKError
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.plugins.anthropic.anthropic_factory import AnthropicFactory


async def anthropic_list_anthropic_models(llm_platform: LLMPlatform) -> List[ModelInfo]:
    """
    List available Anthropic models.

    Returns:
        List[ModelInfo]: A list of Anthropic model information objects
    """
    anthropic_client = AnthropicFactory.make_anthropic_client(llm_platform=llm_platform)
    if not hasattr(anthropic_client, "models"):
        raise LLMSDKError(f"{type(anthropic_client).__name__} does not support listing models")
    if not isinstance(anthropic_client, AsyncAnthropic):
        raise LLMSDKError("We only support the standard Anthropic client for listing models")
    models_response = await anthropic_client.models.list()
    if not models_response:
        raise LLMModelProviderError("No models found")
    models_list = models_response.data
    if not models_list:
        raise LLMModelProviderError("No models found")
    return sorted(models_list, key=lambda model: model.created_at)
