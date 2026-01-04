"""GraphSpec JSON serialization and persistence.

This module provides functions for serializing GraphSpec to/from JSON
and saving/loading from files.
"""

import json
from pathlib import Path
from typing import Any

from pipelex.graph.exceptions import GraphSpecVersionError
from pipelex.graph.graphspec import (
    SUPPORTED_SCHEMA_VERSIONS,
    GraphSpec,
)


def graphspec_to_json(graph: GraphSpec) -> str:
    """Serialize a GraphSpec to a JSON string.

    Args:
        graph: The GraphSpec instance to serialize.

    Returns:
        A human-readable JSON string with indentation.
    """
    return graph.model_dump_json(indent=2, by_alias=True)


def graphspec_from_json(data: str) -> GraphSpec:
    """Deserialize a GraphSpec from a JSON string.

    Args:
        data: The JSON string to deserialize.

    Returns:
        A validated GraphSpec instance.

    Raises:
        GraphSpecVersionError: If the schema_version is not supported.
        ValidationError: If the JSON does not conform to the GraphSpec schema.
    """
    # First, parse the JSON to check the version
    parsed: dict[str, Any] = json.loads(data)
    schema_version = parsed.get("schema_version")

    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        msg = f"Unsupported schema version '{schema_version}'. Supported versions: {SUPPORTED_SCHEMA_VERSIONS}"
        raise GraphSpecVersionError(msg)

    # Now validate and parse with Pydantic
    return GraphSpec.model_validate_json(data)


def save_graphspec(graph: GraphSpec, path: Path) -> None:
    """Save a GraphSpec to a JSON file.

    Args:
        graph: The GraphSpec instance to save.
        path: The file path to save to.
    """
    json_str = graphspec_to_json(graph)
    path.write_text(json_str, encoding="utf-8")


def load_graphspec(path: Path) -> GraphSpec:
    """Load a GraphSpec from a JSON file.

    Args:
        path: The file path to load from.

    Returns:
        A validated GraphSpec instance.

    Raises:
        GraphSpecVersionError: If the schema_version is not supported.
        ValidationError: If the JSON does not conform to the GraphSpec schema.
        FileNotFoundError: If the file does not exist.
    """
    json_str = path.read_text(encoding="utf-8")
    return graphspec_from_json(json_str)
