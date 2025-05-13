# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional, Tuple, cast

import aioboto3
from types_aiobotocore_bedrock_runtime.type_defs import ConverseResponseTypeDef
from typing_extensions import override

from pipelex import log
from pipelex.cogt.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.cogt.bedrock.bedrock_message import BedrockMessageDictList
from pipelex.cogt.llm.llm_report import NbTokensByCategoryDict
from pipelex.cogt.llm.token_category import TokenCategory


class BedrockClientAioboto3(BedrockClientProtocol):
    def __init__(self, aws_region: str):
        log.verbose(f"Init BedrockClientAioboto3 with region '{aws_region}'")
        self.aws_region = aws_region
        self.session = aioboto3.Session()

    @override
    async def chat(
        self,
        messages: BedrockMessageDictList,
        system_text: Optional[str],
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, NbTokensByCategoryDict]:
        params: Dict[str, Any] = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": max_tokens,
            },
        }
        if system_text:
            params["system"] = [{"text": system_text}]

        async with self.session.client("bedrock-runtime", region_name=self.aws_region) as aioboto3_session:  # type: ignore
            conversation_response: ConverseResponseTypeDef = await aioboto3_session.converse(**params)
            resp_dict: Dict[str, Any] = cast(Dict[str, Any], conversation_response)
            usage_dict: Dict[str, Any] = resp_dict["usage"]
            nb_tokens_by_category: NbTokensByCategoryDict = {
                TokenCategory.INPUT: usage_dict["inputTokens"],
                TokenCategory.OUTPUT: usage_dict["outputTokens"],
            }
            response_text: str = resp_dict["output"]["message"]["content"][0]["text"]
            return response_text, nb_tokens_by_category
