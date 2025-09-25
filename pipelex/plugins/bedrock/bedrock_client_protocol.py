from typing import Protocol, runtime_checkable

from pipelex.cogt.usage.token_category import NbTokensByCategoryDict
from pipelex.plugins.bedrock.bedrock_message import BedrockMessageDictList


@runtime_checkable
class BedrockClientProtocol(Protocol):
    async def chat(
        self,
        messages: BedrockMessageDictList,
        system_text: str | None,
        model: str,
        temperature: float,
        max_tokens: int | None = None,
    ) -> tuple[str, NbTokensByCategoryDict]: ...
