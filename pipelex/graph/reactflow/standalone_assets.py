"""Standalone GraphViewer asset loader.

Loads the pre-built JS and CSS bundles from mthds-ui for embedding
in Jinja2 templates via the standard template rendering pipeline.
"""

import importlib.resources

_ASSET_PACKAGE = "pipelex.graph.reactflow.assets"

_cached_js: str | None = None
_cached_css: str | None = None


def get_standalone_js() -> str:
    """Load the pre-built GraphViewer JS bundle (IIFE).

    Returns:
        The JS bundle as a string, cached after first load.
    """
    global _cached_js  # noqa: PLW0603
    if _cached_js is None:
        package_files = importlib.resources.files(_ASSET_PACKAGE)
        _cached_js = (package_files / "graph-viewer.js").read_text(encoding="utf-8")
    return _cached_js


def get_standalone_css() -> str:
    """Load the pre-built GraphViewer CSS bundle.

    Returns:
        The CSS bundle as a string, cached after first load.
    """
    global _cached_css  # noqa: PLW0603
    if _cached_css is None:
        package_files = importlib.resources.files(_ASSET_PACKAGE)
        _cached_css = (package_files / "graph-viewer.css").read_text(encoding="utf-8")
    return _cached_css
