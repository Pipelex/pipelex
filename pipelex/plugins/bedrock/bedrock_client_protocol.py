from typing import Optional, Protocol, Tuple, runtime_checkable

from pipelex.cogt.llm.token_category import NbTokensByCategoryDict
from pipelex.plugins.bedrock.bedrock_message import BedrockMessageDictList


@runtime_checkable
class BedrockClientProtocol(Protocol):
    async def chat(
        self,
        messages: BedrockMessageDictList,
        system_text: Optional[str],
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, NbTokensByCategoryDict]: ...
