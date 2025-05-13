# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Protocol, Tuple, runtime_checkable

from pipelex.cogt.bedrock.bedrock_message import BedrockMessageDictList
from pipelex.cogt.llm.llm_report import NbTokensByCategoryDict


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
