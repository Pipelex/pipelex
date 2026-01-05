"""Test data constants for graph E2E tests."""

from typing import ClassVar


class GraphTestData:
    """Graph test data constants."""

    # Directory paths
    TEST_GRAPH_DIRECTORY: ClassVar[str] = "tests/data/graphs"

    # Graph JSON file paths
    CV_MATCHING_GRAPH_JSON: ClassVar[str] = f"{TEST_GRAPH_DIRECTORY}/cv_matching_graph.json"

    # Test cases: (topic, graph_json_path)
    GRAPH_JSON_TEST_CASES: ClassVar[list[tuple[str, str]]] = [
        ("CV Matching", CV_MATCHING_GRAPH_JSON),
    ]
