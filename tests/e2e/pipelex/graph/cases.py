"""Test data constants for graph E2E tests."""

from typing import ClassVar


class GraphTestData:
    """Graph test data constants."""

    # Directory paths
    TEST_GRAPH_DIRECTORY = "tests/data/graphs"

    # Graph JSON file paths
    CV_JOB_MATCH_GRAPH_JSON = f"{TEST_GRAPH_DIRECTORY}/cv_job_match.json"
    CV_BATCH_GRAPH_JSON = f"{TEST_GRAPH_DIRECTORY}/cv_batch.json"

    # Test cases: (topic, graph_json_path)
    GRAPH_JSON_TEST_CASES: ClassVar[list[tuple[str, str]]] = [
        # ("CV Job Match", CV_JOB_MATCH_GRAPH_JSON),
        ("CV Batch", CV_BATCH_GRAPH_JSON),
    ]
