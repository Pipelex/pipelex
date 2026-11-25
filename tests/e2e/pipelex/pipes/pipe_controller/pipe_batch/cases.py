"""Test data for PipeBatch graph tests."""

from typing import ClassVar


class JokeBatchGraphExpectations:
    """Expected structure for the joke_batch graph."""

    # Expected node pipe_codes (6 nodes total)
    EXPECTED_PIPE_CODES: ClassVar[set[str]] = {
        "generate_jokes_from_topics",  # PipeSequence (outer controller)
        "generate_topics",  # PipeLLM (produces topics list)
        "batch_generate_jokes",  # PipeBatch (controller for batching)
        "generate_joke",  # PipeLLM (branch pipe, appears 3 times)
    }

    # Expected node pipe_types
    EXPECTED_PIPE_TYPES: ClassVar[dict[str, str]] = {
        "generate_jokes_from_topics": "PipeSequence",
        "generate_topics": "PipeLLM",
        "batch_generate_jokes": "PipeBatch",
        "generate_joke": "PipeLLM",
    }

    # Expected containment structure
    # Key: parent pipe_code, Value: set of child pipe_codes
    EXPECTED_CONTAINMENT: ClassVar[dict[str, set[str]]] = {
        "generate_jokes_from_topics": {"generate_topics", "batch_generate_jokes"},
        "batch_generate_jokes": {"generate_joke"},  # Contains 3 generate_joke branches
    }

    # Expected number of nodes per pipe_code
    EXPECTED_NODE_COUNTS: ClassVar[dict[str, int]] = {
        "generate_jokes_from_topics": 1,
        "generate_topics": 1,
        "batch_generate_jokes": 1,
        "generate_joke": 3,  # 3 branches
    }

    # Expected number of edges by kind
    EXPECTED_EDGE_COUNTS: ClassVar[dict[str, int]] = {
        "contains": 5,  # sequence->topics, sequence->batch, batch->3*joke
        "data": 1,  # topics -> batch
        "batch_item": 3,  # topics list -> 3 topic items
        "batch_aggregate": 3,  # 3 joke items -> jokes list
    }
