from pipelex.plugins.anthropic.anthropic_config import AnthropicConfig
from pipelex.plugins.bedrock.bedrock_config import BedrockConfig
from pipelex.plugins.fal.fal_config import FalConfig
from pipelex.plugins.mistral.mistral_config import MistralConfig
from pipelex.plugins.openai.azure_openai_config import AzureOpenAIConfig
from pipelex.plugins.openai.custom_endpoint_config import CustomEndpointConfig
from pipelex.plugins.openai.openai_config import OpenAIConfig
from pipelex.plugins.openai.perplexity_config import PerplexityConfig
from pipelex.plugins.openai.vertexai_config import VertexAIConfig
from pipelex.plugins.openai.xai_config import XaiConfig
from pipelex.tools.config.models import ConfigModel


class PluginsConfig(ConfigModel):
    anthropic_config: AnthropicConfig
    azure_openai_config: AzureOpenAIConfig
    bedrock_config: BedrockConfig
    vertexai_config: VertexAIConfig
    mistral_config: MistralConfig
    openai_config: OpenAIConfig
    perplexity_config: PerplexityConfig
    xai_config: XaiConfig
    custom_endpoint_config: CustomEndpointConfig
    fal_config: FalConfig
