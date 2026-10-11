from typing import Any, NamedTuple, Protocol, cast, runtime_checkable

from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.bedrock.bedrock_message import BedrockMessageDictList


class BedrockChatResult(NamedTuple):
    """What a Bedrock Converse call answered: its text, its token counts and why it stopped.

    `stop_reason` is Converse's `stopReason`, which the worker reads to tell a text cut at its limit or stopped by
    a filter from a finished one, None when the answer carries none.
    """

    text: str
    nb_tokens_by_category: NbTokensByCategoryDict
    stop_reason: str | None


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
    ) -> BedrockChatResult: ...


def read_converse_response(*, response: dict[str, Any]) -> BedrockChatResult:
    """Read a Bedrock Converse answer into its text, its token counts and its stop reason.

    The text is every text block of the answer's message joined, empty when none came back, as when a content
    filter stopped the answer: the worker then raises on the stop reason rather than on a missing block.
    """
    usage_dict: dict[str, Any] = response["usage"]
    nb_tokens_by_category: NbTokensByCategoryDict = {
        TokenCategory.INPUT: usage_dict["inputTokens"],
        TokenCategory.OUTPUT: usage_dict["outputTokens"],
    }
    content_blocks = cast("list[dict[str, Any]]", response.get("output", {}).get("message", {}).get("content", []))
    text_parts: list[str] = []
    for content_block in content_blocks:
        block_text = content_block.get("text")
        if isinstance(block_text, str):
            text_parts.append(block_text)
    stop_reason = response.get("stopReason")
    return BedrockChatResult(
        text="".join(text_parts),
        nb_tokens_by_category=nb_tokens_by_category,
        stop_reason=stop_reason if isinstance(stop_reason, str) else None,
    )


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
