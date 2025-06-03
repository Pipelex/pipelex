from typing import List

from openai.types import Model

from pipelex.cogt.exceptions import LLMSDKError
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.plugins.openai.openai_factory import OpenAIFactory


async def openai_list_available_models(llm_platform: LLMPlatform) -> List[Model]:
    openai_client_async = OpenAIFactory.make_openai_client(llm_platform=llm_platform)
    match llm_platform:
        case LLMPlatform.VERTEXAI | LLMPlatform.PERPLEXITY:
            raise LLMSDKError(f"Platform '{llm_platform}' does not support listing models with OpenAI SDK")
        case _:
            pass

    models = await openai_client_async.models.list()
    data = models.data
    sorted_data = sorted(data, key=lambda x: x.id)
    return sorted_data
