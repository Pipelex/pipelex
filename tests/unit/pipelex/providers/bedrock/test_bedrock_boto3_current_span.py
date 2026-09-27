"""The boto3 Bedrock client runs its blocking call in a thread that keeps the caller's context.

The LLM worker holds its generation span as the Pipelex span active around the provider call, and the
promise is that the SDK's own log lines during the call name it under ``pipelex.*``, while their standard
trace fields, and any span the SDK's instrumentation opens, follow the caller's current span. The boto3
client blocks, so it runs in a thread, and only a thread that carries the context over keeps both there.
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import INVALID_SPAN_ID

from pipelex.providers.bedrock.bedrock_client_boto3 import BedrockClientBoto3
from pipelex.system.telemetry.current_span import current_span_context_for_logs, pipelex_span_active, pipelex_span_context_for_logs


class _RecordingConverse:
    """Stands in for the boto3 runtime client: records the spans the thread that runs ``converse`` sees."""

    def __init__(self) -> None:
        self.seen_log_span_ids: list[int] = []
        self.seen_log_current_span_ids: list[int] = []
        self.seen_current_spans: list[object] = []

    def converse(self, **_params: Any) -> dict[str, Any]:
        log_span_context = pipelex_span_context_for_logs()
        self.seen_log_span_ids.append(INVALID_SPAN_ID if log_span_context is None else log_span_context.span_id)
        log_current_span_context = current_span_context_for_logs()
        self.seen_log_current_span_ids.append(INVALID_SPAN_ID if log_current_span_context is None else log_current_span_context.span_id)
        self.seen_current_spans.append(trace.get_current_span())
        return {"usage": {"inputTokens": 1, "outputTokens": 2}, "output": {"message": {"content": [{"text": "answer"}]}}}


@pytest.mark.asyncio
class TestBedrockBoto3CurrentSpan:
    async def test_the_blocking_call_runs_under_the_callers_spans(self) -> None:
        client = BedrockClientBoto3(aws_region="us-east-1")
        recording = _RecordingConverse()
        client.boto3_client = recording
        tracer = TracerProvider().get_tracer(__name__)
        llm_span = tracer.start_span("llm call")

        with tracer.start_as_current_span("host") as host_span, pipelex_span_active(span=llm_span):
            text, _ = await client.chat(messages=[], system_text=None, model="some-model", temperature=0.5)

        assert text == "answer"
        assert recording.seen_log_span_ids == [llm_span.get_span_context().span_id]
        assert recording.seen_log_current_span_ids == [host_span.get_span_context().span_id]
        assert recording.seen_current_spans == [host_span]
