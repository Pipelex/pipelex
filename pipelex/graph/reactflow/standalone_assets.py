"""Standalone GraphViewer HTML template loader.

Loads the pre-built HTML template from mthds-ui that has JS and CSS
already inlined. Python just injects GraphSpec data and config.
"""

import importlib.resources

_ASSET_PACKAGE = "pipelex.graph.reactflow.assets"
_TEMPLATE_FILENAME = "graph-standalone.html"

_cached_template: str | None = None


def get_standalone_template() -> str:
    """Load the pre-built standalone HTML template.

    The template contains JS + CSS inlined from mthds-ui's GraphViewer bundle.
    Sentinels (<!--PIPELEX_TITLE-->, <!--PIPELEX_GRAPHSPEC-->, etc.) are replaced
    by the caller with actual data.

    Returns:
        The HTML template as a string, cached after first load.
    """
    global _cached_template  # noqa: PLW0603
    if _cached_template is None:
        package_files = importlib.resources.files(_ASSET_PACKAGE)
        template_path = package_files / _TEMPLATE_FILENAME
        _cached_template = template_path.read_text(encoding="utf-8")
    return _cached_template
