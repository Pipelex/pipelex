"""The id generator of Pipelex's tracer provider, which keeps a span opened in workflow code replay-safe.

See ``pipelex.system.telemetry.replay_safe_spans`` for the rules a span opened in replayable workflow code follows.
This module is apart from that one because it imports the OpenTelemetry SDK, which only the provider's
construction in ``OtelFactory.make_ai_tracer`` loads, and never a pipe's module. Only a pipe span, opened inside
``opening_pipe_span``, draws from the workflow's random: any other span opened in workflow code keeps a random id, so
that whether it exists never shifts the ids of the pipe spans opened after it.
"""

from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from opentelemetry.trace import INVALID_SPAN_ID, INVALID_TRACE_ID
from typing_extensions import override

from pipelex.system.telemetry.replay_safe_spans import get_pipe_span_workflow_execution

SPAN_ID_BITS = 64
TRACE_ID_BITS = 128


class ReplaySafeIdGenerator(IdGenerator):
    """Draws a pipe span's ids from the workflow's deterministic random in workflow code, and every other id at random."""

    def __init__(self) -> None:
        self._random_id_generator = RandomIdGenerator()

    @override
    def generate_span_id(self) -> int:
        workflow_execution = get_pipe_span_workflow_execution()
        if workflow_execution is None:
            return self._random_id_generator.generate_span_id()
        workflow_random = workflow_execution.random()
        span_id = workflow_random.getrandbits(SPAN_ID_BITS)
        while span_id == INVALID_SPAN_ID:
            span_id = workflow_random.getrandbits(SPAN_ID_BITS)
        return span_id

    @override
    def generate_trace_id(self) -> int:
        workflow_execution = get_pipe_span_workflow_execution()
        if workflow_execution is None:
            return self._random_id_generator.generate_trace_id()
        workflow_random = workflow_execution.random()
        trace_id = workflow_random.getrandbits(TRACE_ID_BITS)
        while trace_id == INVALID_TRACE_ID:
            trace_id = workflow_random.getrandbits(TRACE_ID_BITS)
        return trace_id
