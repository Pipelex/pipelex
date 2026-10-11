from typing import ClassVar

from pipelex.cogt.llm.completion_stop import CompletionStopOutcome


class CompletionStopTestData:
    # (topic, stop value, outcome): a normal, a truncated and a refused value from each vocabulary
    STOP_REASON_CASES: ClassVar[list[tuple[str, str, CompletionStopOutcome]]] = [
        ("openai normal", "stop", CompletionStopOutcome.NORMAL),
        ("openai tool call", "tool_calls", CompletionStopOutcome.NORMAL),
        ("openai truncated", "length", CompletionStopOutcome.TRUNCATED),
        ("openai filtered", "content_filter", CompletionStopOutcome.REFUSED),
        ("gateway strict refusal", "refusal", CompletionStopOutcome.REFUSED),
        ("anthropic normal", "end_turn", CompletionStopOutcome.NORMAL),
        ("anthropic paused", "pause_turn", CompletionStopOutcome.NORMAL),
        ("anthropic truncated", "max_tokens", CompletionStopOutcome.TRUNCATED),
        ("anthropic context window", "model_context_window_exceeded", CompletionStopOutcome.CONTEXT_WINDOW_EXCEEDED),
        ("anthropic refused", "refusal", CompletionStopOutcome.REFUSED),
        ("converse normal", "stop_sequence", CompletionStopOutcome.NORMAL),
        ("converse truncated", "max_tokens", CompletionStopOutcome.TRUNCATED),
        ("converse context window", "model_context_window_exceeded", CompletionStopOutcome.CONTEXT_WINDOW_EXCEEDED),
        ("converse filtered", "content_filtered", CompletionStopOutcome.REFUSED),
        ("converse guardrail", "guardrail_intervened", CompletionStopOutcome.REFUSED),
        ("gemini normal", "STOP", CompletionStopOutcome.NORMAL),
        ("gemini truncated", "MAX_TOKENS", CompletionStopOutcome.TRUNCATED),
        ("gemini safety", "SAFETY", CompletionStopOutcome.REFUSED),
        ("gemini recitation", "RECITATION", CompletionStopOutcome.REFUSED),
        ("gemini blocklist", "BLOCKLIST", CompletionStopOutcome.REFUSED),
        ("gemini prohibited", "PROHIBITED_CONTENT", CompletionStopOutcome.REFUSED),
        ("gemini privacy", "SPII", CompletionStopOutcome.REFUSED),
        ("mistral normal", "stop", CompletionStopOutcome.NORMAL),
        ("mistral truncated", "length", CompletionStopOutcome.TRUNCATED),
        ("mistral context window", "model_length", CompletionStopOutcome.CONTEXT_WINDOW_EXCEEDED),
    ]

    # (topic, status, incomplete reason, outcome)
    RESPONSES_CASES: ClassVar[list[tuple[str, str | None, str | None, CompletionStopOutcome]]] = [
        ("completed", "completed", None, CompletionStopOutcome.NORMAL),
        ("no status", None, None, CompletionStopOutcome.NORMAL),
        ("truncated", "incomplete", "max_output_tokens", CompletionStopOutcome.TRUNCATED),
        ("filtered", "incomplete", "content_filter", CompletionStopOutcome.REFUSED),
        ("incomplete with no reason", "incomplete", None, CompletionStopOutcome.TRUNCATED),
        ("failed", "failed", None, CompletionStopOutcome.NORMAL),
    ]
