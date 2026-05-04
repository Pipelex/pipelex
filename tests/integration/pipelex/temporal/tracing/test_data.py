"""Test data constants for Temporal graph tracing integration tests.

Expected graph structures for each bundle used in tracing tests.
"""

from typing import ClassVar

_CRATE_DIR = "tests/integration/pipelex/temporal/library_crate"


class SequenceTracingTestData:
    """Expected graph structure for native_text_sequence.mthds.

    Bundle: PipeSequence with 2 PipeLLM steps (step_one → step_two).
    Nodes: sequence controller + step_one + step_two.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/native_text_sequence.mthds"
    PIPE_CODE: ClassVar[str] = "native_text_sequence"
    DOMAIN: ClassVar[str] = "native_text_test"

    EXPECTED_PIPE_CODES: ClassVar[set[str | None]] = {
        "native_text_sequence",
        "step_one",
        "step_two",
    }
    EXPECTED_NODE_COUNT: ClassVar[int] = 3
    EXPECTED_CONTAINS_EDGE_COUNT: ClassVar[int] = 2
    MIN_DATA_EDGES: ClassVar[int] = 1


class ParallelTracingTestData:
    """Expected graph structure for temporal_parallel.mthds.

    Bundle: PipeSequence wrapping PipeParallel (2 branches) + summarize step.
    Nodes: outer sequence + analyze_in_parallel + branch_tone + branch_length + summarize_results.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_parallel.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_parallel_sequence"
    DOMAIN: ClassVar[str] = "temporal_parallel_test"

    EXPECTED_PIPE_CODES: ClassVar[set[str | None]] = {
        "temporal_parallel_sequence",
        "analyze_in_parallel",
        "branch_tone",
        "branch_length",
        "summarize_results",
    }
    MIN_NODE_COUNT: ClassVar[int] = 5


class BatchTracingTestData:
    """Expected graph structure for temporal_batch.mthds.

    Bundle: PipeSequence wrapping PipeBatch (fan-out to per-item child workflows).
    Nodes: outer sequence + generate_topics + batch controller + per-item processors.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_batch.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_batch_sequence"
    DOMAIN: ClassVar[str] = "temporal_batch_test"

    MIN_NODE_COUNT: ClassVar[int] = 4
    MIN_BATCH_ITEM_EDGES: ClassVar[int] = 1
    MIN_BATCH_AGGREGATE_EDGES: ClassVar[int] = 1
