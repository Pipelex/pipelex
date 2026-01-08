"""Mermaidflow utilities for graph visualization.

This module provides utility functions for Mermaid graph rendering.
"""

from pipelex.tools.mermaid.mermaid_utils import sanitize_mermaid_id


def make_stuff_id(digest: str) -> str:
    """Create a stuff ID from a digest.

    Stuff IDs follow the format 's_xxx' which is the standard format
    used across graph visualization components.

    Args:
        digest: The stuff digest (unique identifier).

    Returns:
        A stuff ID in the format 's_xxx'.
    """
    return f"s_{sanitize_mermaid_id(digest)[2:]}"
