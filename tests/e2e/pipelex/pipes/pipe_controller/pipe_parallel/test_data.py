"""Test data for PipeParallel graph tests."""

from typing import ClassVar


class ParallelAddEachGraphExpectations:
    """Expected structure for the parallel_graph_add_each graph."""

    # Expected node pipe_codes
    EXPECTED_PIPE_CODES: ClassVar[set[str]] = {
        "parallel_then_consume",  # PipeSequence (outer controller)
        "parallel_summarize",  # PipeParallel (parallel controller)
        "summarize_short",  # PipeLLM (branch 1)
        "summarize_detailed",  # PipeLLM (branch 2)
        "combine_summaries",  # PipeLLM (downstream consumer)
    }

    # Expected number of nodes per pipe_code
    EXPECTED_NODE_COUNTS: ClassVar[dict[str, int]] = {
        "parallel_then_consume": 1,
        "parallel_summarize": 1,
        "summarize_short": 1,
        "summarize_detailed": 1,
        "combine_summaries": 1,
    }

    # Expected number of edges by kind
    EXPECTED_EDGE_COUNTS: ClassVar[dict[str, int]] = {
        "contains": 4,  # sequence->parallel, sequence->combine, parallel->short, parallel->detailed
        "data": 2,  # parallel->combine (short_summary), parallel->combine (detailed_summary)
    }


class ParallelCombinedGraphExpectations:
    """Expected structure for the parallel_graph_combined graph."""

    # Expected node pipe_codes
    EXPECTED_PIPE_CODES: ClassVar[set[str]] = {
        "pgc_parallel_analysis",  # PipeParallel (parallel controller with combined_output)
        "pgc_analyze_tone",  # PipeLLM (branch 1)
        "pgc_analyze_length",  # PipeLLM (branch 2)
    }

    # Expected number of nodes per pipe_code
    EXPECTED_NODE_COUNTS: ClassVar[dict[str, int]] = {
        "pgc_parallel_analysis": 1,
        "pgc_analyze_tone": 1,
        "pgc_analyze_length": 1,
    }

    # Expected number of edges by kind
    EXPECTED_EDGE_COUNTS: ClassVar[dict[str, int]] = {
        "contains": 2,  # parallel->tone, parallel->length
        "parallel_combine": 2,  # tone_result->combined, length_result->combined
    }
