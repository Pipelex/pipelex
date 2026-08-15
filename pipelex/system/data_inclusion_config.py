"""Data-capture configuration for the per-execution trace streams.

Lives below both ``graph`` and ``tracing`` because it rides in every job's
``TraceContext`` — the transport that reaches the inference layer — while the
TOML nests it under ``[...graph.data_inclusion]``, which is where an
operator expects to tune it. Keeping the class here is what lets
:mod:`pipelex.system.trace_context` stay independent of the graph rendering
configs (``mermaid`` / ``reactflow``) that ``GraphConfig`` pulls in.
"""

from pipelex.system.configuration.config_model import ConfigModel


class DataInclusionConfig(ConfigModel):
    """Controls which data is included in graph outputs."""

    stuff_json_content: bool
    stuff_text_content: bool
    stuff_html_content: bool
    error_stack_traces: bool
    pipe_and_concept_registry: bool
