"""Test data for PipeParallel graph tests."""

from typing import ClassVar


class ParallelCombinedGraphExpectationsBase:
    """Base class for PipeParallel graph expectations with a combined output."""

    PARALLEL_PIPE_CODE: ClassVar[str]
    EXPECTED_PIPE_CODES: ClassVar[set[str]]
    EXPECTED_NODE_COUNTS: ClassVar[dict[str, int]]
    EXPECTED_EDGE_COUNTS: ClassVar[dict[str, int]]


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
        "parallel_combine": 2,  # short_summary->combined, detailed_summary->combined (always-combine)
        "data": 2,  # parallel->combine (short_summary), parallel->combine (detailed_summary)
    }


class ParallelCombinedGraphExpectations(ParallelCombinedGraphExpectationsBase):
    """Expected structure for the parallel_graph_combined graph (PipeSequence wrapping PipeParallel with a combined output)."""

    PARALLEL_PIPE_CODE: ClassVar[str] = "pgc_parallel_analysis"

    # Expected node pipe_codes
    EXPECTED_PIPE_CODES: ClassVar[set[str]] = {
        "pgc_analysis_then_summarize",  # PipeSequence (outer controller)
        "pgc_parallel_analysis",  # PipeParallel (parallel controller with structured combined output)
        "pgc_analyze_tone",  # PipeLLM (branch 1)
        "pgc_analyze_length",  # PipeLLM (branch 2)
        "pgc_summarize_combined",  # PipeLLM (downstream consumer of combined result)
    }

    # Expected number of nodes per pipe_code
    EXPECTED_NODE_COUNTS: ClassVar[dict[str, int]] = {
        "pgc_analysis_then_summarize": 1,
        "pgc_parallel_analysis": 1,
        "pgc_analyze_tone": 1,
        "pgc_analyze_length": 1,
        "pgc_summarize_combined": 1,
    }

    # Expected number of edges by kind
    EXPECTED_EDGE_COUNTS: ClassVar[dict[str, int]] = {
        "contains": 4,  # sequence->parallel, sequence->summarize_combined, parallel->tone, parallel->length
        "parallel_combine": 2,  # tone_result->combined, length_result->combined
        "data": 1,  # parallel->summarize_combined (combined result)
    }


class Parallel3BranchGraphExpectations(ParallelCombinedGraphExpectationsBase):
    """Expected structure for the parallel_graph_3branch graph (3-branch PipeParallel with selective consumption)."""

    PARALLEL_PIPE_CODE: ClassVar[str] = "pg3_parallel"

    # Expected node pipe_codes
    EXPECTED_PIPE_CODES: ClassVar[set[str]] = {
        "pg3_sequence",  # PipeSequence (outer controller)
        "pg3_parallel",  # PipeParallel (3-branch parallel with combined output)
        "pg3_analyze_tone",  # PipeLLM (branch 1)
        "pg3_analyze_length",  # PipeLLM (branch 2)
        "pg3_analyze_style",  # PipeLLM (branch 3 - unused downstream)
        "pg3_refine_tone",  # PipeLLM (consumes tone_result)
        "pg3_refine_length",  # PipeLLM (consumes length_result)
    }

    # Expected number of nodes per pipe_code
    EXPECTED_NODE_COUNTS: ClassVar[dict[str, int]] = {
        "pg3_sequence": 1,
        "pg3_parallel": 1,
        "pg3_analyze_tone": 1,
        "pg3_analyze_length": 1,
        "pg3_analyze_style": 1,
        "pg3_refine_tone": 1,
        "pg3_refine_length": 1,
    }

    # Expected number of edges by kind
    EXPECTED_EDGE_COUNTS: ClassVar[dict[str, int]] = {
        "contains": 6,  # sequence->parallel, sequence->refine_tone, sequence->refine_length, parallel->tone, parallel->length, parallel->style
        "parallel_combine": 3,  # tone->combined, length->combined, style->combined
        "data": 2,  # parallel->refine_tone (tone_result), parallel->refine_length (length_result)
    }
