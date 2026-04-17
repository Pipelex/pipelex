"""Standalone GraphViewer asset loader.

Loads the pre-built JS and CSS bundles from mthds-ui for embedding
in Jinja2 templates via the standard template rendering pipeline.
"""

import importlib.resources
from functools import cache

_ASSET_PACKAGE = "pipelex.graph.reactflow.assets"


@cache
def get_standalone_js() -> str:
    """Load the pre-built GraphViewer JS bundle (IIFE).

    Returns:
        The JS bundle as a string, cached after first load.
    """
    package_files = importlib.resources.files(_ASSET_PACKAGE)
    return (package_files / "graph-viewer.js").read_text(encoding="utf-8")


@cache
def get_standalone_css() -> str:
    """Load the pre-built GraphViewer CSS bundle.

    Returns:
        The CSS bundle as a string, cached after first load.
    """
    package_files = importlib.resources.files(_ASSET_PACKAGE)
    return (package_files / "graph-viewer.css").read_text(encoding="utf-8")
