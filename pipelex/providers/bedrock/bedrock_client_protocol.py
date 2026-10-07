from typing import Any, Protocol, runtime_checkable

from pipelex.cogt.usage.token_category import NbTokensByCategoryDict
from pipelex.providers.bedrock.bedrock_message import BedrockMessageDictList


@runtime_checkable
class BedrockClientProtocol(Protocol):
    async def chat(
        self,
        messages: BedrockMessageDictList,
        *,
        system_text: str | None,
        model: str,
        temperature: float | None,
        max_tokens: int | None = None,
    ) -> tuple[str, NbTokensByCategoryDict]: ...


def make_converse_params(
    *,
    messages: BedrockMessageDictList,
    system_text: str | None,
    model: str,
    temperature: float | None,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Build the parameters of a Bedrock Converse call, which every Bedrock client sends.

    A temperature of None leaves the key out of the inference config, for a model whose provider refuses one.
    """
    inference_config: dict[str, Any] = {"maxTokens": max_tokens}
    if temperature is not None:
        inference_config["temperature"] = temperature
    params: dict[str, Any] = {
        "modelId": model,
        "messages": messages,
        "inferenceConfig": inference_config,
    }
    if system_text:
        params["system"] = [{"text": system_text}]
    return params
