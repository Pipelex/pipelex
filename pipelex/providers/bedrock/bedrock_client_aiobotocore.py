from typing import TYPE_CHECKING, Any, cast

from aiobotocore.session import get_session
from typing_extensions import override

from pipelex import log
from pipelex.providers.bedrock.bedrock_client_protocol import BedrockChatResult, BedrockClientProtocol, make_converse_params, read_converse_response
from pipelex.providers.bedrock.bedrock_message import BedrockMessageDictList

if TYPE_CHECKING:
    from types_aiobotocore_bedrock_runtime.type_defs import ConverseResponseTypeDef


class BedrockClientAiobotocore(BedrockClientProtocol):
    def __init__(self, aws_region: str):
        self.aws_region = aws_region
        self.session = get_session()
        log.debug(f"A Bedrock client was made on aiobotocore for region '{aws_region}'")

    @override
    async def chat(
        self,
        messages: BedrockMessageDictList,
        *,
        system_text: str | None,
        model: str,
        temperature: float | None,
        max_tokens: int | None = None,
    ) -> BedrockChatResult:
        params = make_converse_params(messages=messages, system_text=system_text, model=model, temperature=temperature, max_tokens=max_tokens)

        async with self.session.create_client("bedrock-runtime", region_name=self.aws_region) as bedrock_runtime_client:  # pyright: ignore[reportUnknownMemberType]
            conversation_response: ConverseResponseTypeDef = await bedrock_runtime_client.converse(**params)
            return read_converse_response(response=cast("dict[str, Any]", conversation_response))
