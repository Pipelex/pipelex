from typing import TYPE_CHECKING, Any, cast

from aiobotocore.session import get_session
from typing_extensions import override

from pipelex import log
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.bedrock.bedrock_client_protocol import BedrockClientProtocol, make_converse_params
from pipelex.providers.bedrock.bedrock_message import BedrockMessageDictList

if TYPE_CHECKING:
    from types_aiobotocore_bedrock_runtime.type_defs import ConverseResponseTypeDef


class BedrockClientAiobotocore(BedrockClientProtocol):
    def __init__(self, aws_region: str):
        log.verbose(f"Init BedrockClientAiobotocore with region '{aws_region}'")
        self.aws_region = aws_region
        self.session = get_session()

    @override
    async def chat(
        self,
        messages: BedrockMessageDictList,
        *,
        system_text: str | None,
        model: str,
        temperature: float | None,
        max_tokens: int | None = None,
    ) -> tuple[str, NbTokensByCategoryDict]:
        params = make_converse_params(messages=messages, system_text=system_text, model=model, temperature=temperature, max_tokens=max_tokens)

        async with self.session.create_client("bedrock-runtime", region_name=self.aws_region) as bedrock_runtime_client:  # pyright: ignore[reportUnknownMemberType]
            conversation_response: ConverseResponseTypeDef = await bedrock_runtime_client.converse(**params)
            resp_dict: dict[str, Any] = cast("dict[str, Any]", conversation_response)
            usage_dict: dict[str, Any] = resp_dict["usage"]
            nb_tokens_by_category: NbTokensByCategoryDict = {
                TokenCategory.INPUT: usage_dict["inputTokens"],
                TokenCategory.OUTPUT: usage_dict["outputTokens"],
            }
            response_text: str = resp_dict["output"]["message"]["content"][0]["text"]
            return response_text, nb_tokens_by_category
