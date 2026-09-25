"""The boto3 Bedrock client runs its blocking call in a thread that keeps the caller's context.

The LLM worker makes its generation span current around the provider call, and the promise is that the
SDK's own log lines and spans during the call are joined to it. The boto3 client blocks, so it runs in a
thread, and only a thread that carries the context over keeps the span current there.
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from pipelex.providers.bedrock.bedrock_client_boto3 import BedrockClientBoto3


class _RecordingConverse:
    """Stands in for the boto3 runtime client: records the span current in the thread that runs ``converse``."""

    def __init__(self) -> None:
        self.seen_span_ids: list[int] = []

    def converse(self, **_params: Any) -> dict[str, Any]:
        self.seen_span_ids.append(trace.get_current_span().get_span_context().span_id)
        return {"usage": {"inputTokens": 1, "outputTokens": 2}, "output": {"message": {"content": [{"text": "answer"}]}}}


@pytest.mark.asyncio
class TestBedrockBoto3CurrentSpan:
    async def test_the_blocking_call_runs_under_the_callers_span(self) -> None:
        client = BedrockClientBoto3(aws_region="us-east-1")
        recording = _RecordingConverse()
        client.boto3_client = recording
        tracer = TracerProvider().get_tracer(__name__)

        with tracer.start_as_current_span("llm call") as span:
            text, _ = await client.chat(messages=[], system_text=None, model="some-model", temperature=0.5)

        assert text == "answer"
        assert recording.seen_span_ids == [span.get_span_context().span_id]
