"""How a text completion stopped: normally, cut short, or refused, read from the provider's own stop signal.

A provider answers a completion that did not end normally with a success all the same: a text cut at the
output limit, or refused, or stopped by a safety filter, comes back as a 200 carrying whatever text the model
had written, empty or partial, and a stop value saying why it ended. Every LLM worker therefore passes its
response's stop value through `classify_stop_reason` before it returns any text, and raises on an outcome that
is not normal (see `LLMWorkerAbstract._check_completion_stop`), so a text the model could not finish fails its
pipe instead of passing for a result.

The classifier knows every vocabulary a worker can receive, each checked against the provider SDK's own type,
and reads them as one: a gateway in non-strict mode passes each provider's own value through the OpenAI
completions shape, so that worker can receive any of them, and the values agree wherever two vocabularies share
one. A value the classifier does not know is logged at warning level and taken as normal, so a value a provider
adds later cannot fail every call. A missing value is taken as normal without a word, since some
OpenAI-compatible servers send none. Two signals say on their own that the text is unusable, whatever reason comes
with them: a Responses API answer whose status is `incomplete` is never normal, an unknown or missing reason being
taken as a truncation, and a Gemini answer with no candidate whose prompt feedback names a block reason is a refusal.

The classifier only turns a stop that was silently a success into an error. Structured generation is not read
here: its stops are the structuring library's business, and its configured re-asks are left as they are.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pipelex import log
from pipelex.cogt.exceptions import CompletionTruncationLimit, LLMCompletionRefusedError, LLMCompletionTruncatedError


class CompletionStopOutcome(StrEnum):
    """What a completion's stop value says about its text."""

    NORMAL = "normal"
    # Cut at the output limit the request sent
    TRUNCATED = "truncated"
    # Cut when the input and the output together filled the model's context window, which no higher output limit lifts
    CONTEXT_WINDOW_EXCEEDED = "context_window_exceeded"
    REFUSED = "refused"


_NORMAL = CompletionStopOutcome.NORMAL
_TRUNCATED = CompletionStopOutcome.TRUNCATED
_CONTEXT_WINDOW_EXCEEDED = CompletionStopOutcome.CONTEXT_WINDOW_EXCEEDED
_REFUSED = CompletionStopOutcome.REFUSED

# `openai.types.chat.chat_completion.Choice.finish_reason`, plus `refusal`, the value a gateway's strict OpenAI
# compliance maps Anthropic's refusal to.
OPENAI_CHAT_FINISH_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "stop": _NORMAL,
        "tool_calls": _NORMAL,
        "function_call": _NORMAL,
        "length": _TRUNCATED,
        "content_filter": _REFUSED,
        "refusal": _REFUSED,
    }
)

# `anthropic.types.StopReason`, plus `model_context_window_exceeded`, which the Messages API returns when the
# context window ends the text and a gateway passes through.
ANTHROPIC_STOP_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "end_turn": _NORMAL,
        "stop_sequence": _NORMAL,
        "tool_use": _NORMAL,
        "pause_turn": _NORMAL,
        "max_tokens": _TRUNCATED,
        "model_context_window_exceeded": _CONTEXT_WINDOW_EXCEEDED,
        "refusal": _REFUSED,
    }
)

# `types_aiobotocore_bedrock_runtime.literals.StopReasonType`, Bedrock Converse's `stopReason`. The two
# `malformed_*` values concern tool use and output parsing, which a text generation does not ask for, so the
# text is returned as before.
BEDROCK_CONVERSE_STOP_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "end_turn": _NORMAL,
        "stop_sequence": _NORMAL,
        "tool_use": _NORMAL,
        "malformed_model_output": _NORMAL,
        "malformed_tool_use": _NORMAL,
        "max_tokens": _TRUNCATED,
        "model_context_window_exceeded": _CONTEXT_WINDOW_EXCEEDED,
        "content_filtered": _REFUSED,
        "guardrail_intervened": _REFUSED,
    }
)

# `google.genai.types.FinishReason`. Every safety, recitation, blocklist, privacy and language stop is a filter,
# the image ones included; the unspecified, other, tool-call and no-image values say nothing about the text, so
# it is returned as before, as a gateway in strict mode also maps them to `stop`.
GEMINI_FINISH_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "STOP": _NORMAL,
        "FINISH_REASON_UNSPECIFIED": _NORMAL,
        "OTHER": _NORMAL,
        "MALFORMED_FUNCTION_CALL": _NORMAL,
        "UNEXPECTED_TOOL_CALL": _NORMAL,
        "NO_IMAGE": _NORMAL,
        "IMAGE_OTHER": _NORMAL,
        "MAX_TOKENS": _TRUNCATED,
        "SAFETY": _REFUSED,
        "RECITATION": _REFUSED,
        "LANGUAGE": _REFUSED,
        "BLOCKLIST": _REFUSED,
        "PROHIBITED_CONTENT": _REFUSED,
        "SPII": _REFUSED,
        "IMAGE_SAFETY": _REFUSED,
        "IMAGE_PROHIBITED_CONTENT": _REFUSED,
        "IMAGE_RECITATION": _REFUSED,
    }
)

# `mistralai.client.models.ChatCompletionChoiceFinishReason`. Its `length` is the request's output limit and its
# `model_length` the model's context window. Its `error` is neither a cut nor a refusal, and a gateway in strict mode
# maps it to `stop`, so the text is returned as before.
MISTRAL_FINISH_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "stop": _NORMAL,
        "tool_calls": _NORMAL,
        "error": _NORMAL,
        "length": _TRUNCATED,
        "model_length": _CONTEXT_WINDOW_EXCEEDED,
    }
)

# `openai.types.responses.response.IncompleteDetails.reason`, read when a Responses API answer's status is
# `incomplete`.
OPENAI_RESPONSES_INCOMPLETE_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "max_output_tokens": _TRUNCATED,
        "content_filter": _REFUSED,
    }
)

# `google.genai.types.BlockedReason`, a Gemini answer's `prompt_feedback.block_reason`, read when the answer holds no
# candidate: the prompt was blocked before the model wrote anything, so every value is a refusal, the unspecified
# one included. It is not read with the stop values, which share some of its words with another meaning.
GEMINI_BLOCK_REASONS: Mapping[str, CompletionStopOutcome] = MappingProxyType(
    {
        "BLOCKED_REASON_UNSPECIFIED": _REFUSED,
        "SAFETY": _REFUSED,
        "OTHER": _REFUSED,
        "BLOCKLIST": _REFUSED,
        "PROHIBITED_CONTENT": _REFUSED,
        "IMAGE_SAFETY": _REFUSED,
        "MODEL_ARMOR": _REFUSED,
        "JAILBREAK": _REFUSED,
    }
)

# Every vocabulary a worker's stop value can come from, read as one, whatever worker receives it.
STOP_REASON_VOCABULARIES: tuple[Mapping[str, CompletionStopOutcome], ...] = (
    OPENAI_CHAT_FINISH_REASONS,
    ANTHROPIC_STOP_REASONS,
    BEDROCK_CONVERSE_STOP_REASONS,
    GEMINI_FINISH_REASONS,
    MISTRAL_FINISH_REASONS,
)

# The status a Responses API answer has when it stopped before the model finished.
OPENAI_RESPONSES_INCOMPLETE_STATUS = "incomplete"


def merge_stop_vocabularies(*, vocabularies: tuple[Mapping[str, CompletionStopOutcome], ...]) -> Mapping[str, CompletionStopOutcome]:
    """Merge stop vocabularies into one table keyed by the case-folded value.

    Gemini writes its values in capitals and the others in lower case, and no two of them read a shared value
    differently, which a unit test holds, so the case-folded union classifies a value whichever provider sent it.
    """
    merged: dict[str, CompletionStopOutcome] = {}
    for vocabulary in vocabularies:
        for value, outcome in vocabulary.items():
            merged[value.casefold()] = outcome
    return MappingProxyType(merged)


_ALL_STOP_REASONS = merge_stop_vocabularies(vocabularies=STOP_REASON_VOCABULARIES)


def _log_unknown_stop(*, model_handle: str, stop_value: object) -> None:
    log.warning(
        "An LLM stop reason was not recognized, so it was taken as normal",
        fields={"model_handle": model_handle, "stop_reason": str(stop_value)},
    )


def classify_stop_reason(*, stop_reason: str | None, model_handle: str) -> CompletionStopOutcome:
    """Read a completion's stop value, from any vocabulary the classifier knows, as normal, cut short or refused.

    Args:
        stop_reason: The provider's stop value: a finish reason, a stop reason or Converse's stop reason. None when
            the response carries none.
        model_handle: The model's deck handle, named by the warning about an unknown value.

    Returns:
        The outcome the value stands for: normal for a missing or unknown value.
    """
    if stop_reason is None:
        return _NORMAL
    outcome = _ALL_STOP_REASONS.get(stop_reason.casefold())
    if outcome is None:
        _log_unknown_stop(model_handle=model_handle, stop_value=stop_reason)
        return _NORMAL
    return outcome


def classify_responses_stop(*, status: str | None, incomplete_reason: str | None, model_handle: str) -> CompletionStopOutcome:
    """Read a Responses API answer's status, and its incomplete reason, as normal, truncated or refused.

    Only an `incomplete` status says the model did not finish; every other status is normal here, a failed or
    cancelled answer being caught by the worker's own check for an answer with no text. An incomplete answer is never
    normal, since the status alone says its text is unfinished: its reason only tells a filter from a cut, and a
    reason that is missing, the SDK typing both the details and their reason as optional, or that the classifier does
    not know is taken as a cut and logged at warning level.

    Args:
        status: The answer's `status`. None when it carries none.
        incomplete_reason: The `incomplete_details.reason` of an incomplete answer. None when it carries none.
        model_handle: The model's deck handle, named by the warning about a missing or unknown reason.

    Returns:
        The outcome the status and reason stand for: truncated for an incomplete answer whose reason is missing or unknown.
    """
    if status != OPENAI_RESPONSES_INCOMPLETE_STATUS:
        return _NORMAL
    outcome = OPENAI_RESPONSES_INCOMPLETE_REASONS.get(incomplete_reason) if incomplete_reason is not None else None
    if outcome is None:
        log.warning(
            "An incomplete answer gave no known reason, so it was taken as truncated",
            fields={"model_handle": model_handle, "stop_reason": status, "incomplete_reason": incomplete_reason},
        )
        return _TRUNCATED
    return outcome


def classify_prompt_block_reason(*, block_reason: str, model_handle: str) -> CompletionStopOutcome:
    """Read the block reason of a Gemini answer that holds no candidate, which is always a refusal.

    The prompt was blocked before the model wrote anything, so whatever reason is given the text cannot be had: a
    reason the classifier does not know is a refusal too, logged at warning level so the table can learn it.

    Args:
        block_reason: The answer's `prompt_feedback.block_reason`, as its value.
        model_handle: The model's deck handle, named by the warning about an unknown reason.

    Returns:
        The refusal outcome.
    """
    outcome = GEMINI_BLOCK_REASONS.get(block_reason.upper())
    if outcome is None:
        log.warning(
            "A blocked prompt gave an unknown reason, so it was taken as a refusal",
            fields={"model_handle": model_handle, "block_reason": block_reason},
        )
        return _REFUSED
    return outcome


def raise_for_completion_stop(
    *,
    outcome: CompletionStopOutcome,
    stop_reason: str,
    model_handle: str,
    pipe_code: str | None,
    max_tokens: int | None,
    output_tokens: int | None,
) -> None:
    """Raise the error a stop that is not normal stands for, and return on a normal one.

    Args:
        outcome: The outcome the stop value was classified as.
        stop_reason: The provider's stop value, as the error names it.
        model_handle: The model's deck handle.
        pipe_code: The code of the pipe whose text it was, when the job knows it.
        max_tokens: The output limit the request sent, when it sent one.
        output_tokens: The output tokens the provider counted, when it counted them.

    Raises:
        LLMCompletionTruncatedError: When the text was cut before the model finished it, at its output limit or at
            its context window, which the error carries as its `truncation_limit`.
        LLMCompletionRefusedError: When the model refused, or a content filter stopped the text.
    """
    truncation_limit: CompletionTruncationLimit
    match outcome:
        case CompletionStopOutcome.NORMAL:
            return
        case CompletionStopOutcome.REFUSED:
            raise LLMCompletionRefusedError(model_handle=model_handle, stop_reason=stop_reason, pipe_code=pipe_code)
        case CompletionStopOutcome.TRUNCATED:
            truncation_limit = CompletionTruncationLimit.MAX_TOKENS
        case CompletionStopOutcome.CONTEXT_WINDOW_EXCEEDED:
            truncation_limit = CompletionTruncationLimit.CONTEXT_WINDOW
    raise LLMCompletionTruncatedError(
        model_handle=model_handle,
        stop_reason=stop_reason,
        truncation_limit=truncation_limit,
        pipe_code=pipe_code,
        max_tokens=max_tokens,
        output_tokens=output_tokens,
    )
