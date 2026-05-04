"""Standalone GraphViewer asset loader.

Loads the pre-built JS and CSS bundles from mthds-ui for embedding
in Jinja2 templates via the standard template rendering pipeline.
"""

import importlib.resources
from functools import lru_cache

_ASSET_PACKAGE = "pipelex.graph.reactflow.assets"


# @lru_cache(maxsize=1) memoizes the no-arg call: file is read once, then served from cache.
@lru_cache(maxsize=1)
def get_standalone_js() -> str:
    """Load the pre-built GraphViewer JS bundle (IIFE).

    Returns:
        The JS bundle as a string, cached after first load.
    """
    package_files = importlib.resources.files(_ASSET_PACKAGE)
    return (package_files / "graph-viewer.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def get_standalone_css() -> str:
    """Load the pre-built GraphViewer CSS bundle.

    Returns:
        The CSS bundle as a string, cached after first load.
    """
    package_files = importlib.resources.files(_ASSET_PACKAGE)
    return (package_files / "graph-viewer.css").read_text(encoding="utf-8")
