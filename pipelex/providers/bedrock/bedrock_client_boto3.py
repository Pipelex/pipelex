import asyncio
from typing import Any

import boto3
from typing_extensions import override

from pipelex import log
from pipelex.providers.bedrock.bedrock_client_protocol import BedrockChatResult, BedrockClientProtocol, make_converse_params, read_converse_response
from pipelex.providers.bedrock.bedrock_message import BedrockMessageDictList


class BedrockClientBoto3(BedrockClientProtocol):
    def __init__(self, aws_region: str):
        self.boto3_client = boto3.client(service_name="bedrock-runtime", region_name=aws_region)  # pyright: ignore[reportUnknownMemberType]
        log.debug(f"A Bedrock client was made on boto3 for region '{aws_region}'")

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

        # ``to_thread`` rather than ``run_in_executor``: it carries the context over, so the SDK's own log
        # lines in the thread name the LLM span under `pipelex.*` and the caller's current span in their
        # standard trace fields, and a span its instrumentation opens has that current span as its parent.
        resp_dict: dict[str, Any] = await asyncio.to_thread(self.boto3_client.converse, **params)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]

        return read_converse_response(response=resp_dict)
