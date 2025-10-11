import asyncio
from typing import Any

import boto3
from typing_extensions import override

from pipelex import log
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_message import BedrockMessageDictList


class BedrockClientBoto3(BedrockClientProtocol):
    def __init__(self, aws_region: str):
        log.debug(f"Initializing BedrockClientBoto3 with region '{aws_region}'")
        self.boto3_client = boto3.client(service_name="bedrock-runtime", region_name=aws_region)  # pyright: ignore[reportUnknownMemberType]

    @override
    async def chat(
        self,
        messages: BedrockMessageDictList,
        system_text: str | None,
        model: str,
        temperature: float,
        max_tokens: int | None = None,
    ) -> tuple[str, NbTokensByCategoryDict]:
        params: dict[str, Any] = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": max_tokens,
            },
        }
        if system_text:
            params["system"] = [{"text": system_text}]

        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        resp_dict: dict[str, Any] = await loop.run_in_executor(None, lambda: self.boto3_client.converse(**params))  # pyright: ignore[reportUnknownLambdaType, reportUnknownMemberType]

        usage_dict: dict[str, Any] = resp_dict["usage"]
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage_dict["inputTokens"],
            TokenCategory.OUTPUT: usage_dict["outputTokens"],
        }
        response_text: str = resp_dict["output"]["message"]["content"][0]["text"]
        return response_text, nb_tokens_by_category
