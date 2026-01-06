"""Template loader utility using importlib.resources.

This module provides a simple, package-safe way to load Jinja2 template files
from within Python packages using importlib.resources (Python 3.9+).

Note: This does NOT use Jinja2's native template loading mechanisms.
Templates are loaded as raw strings and then passed to our existing
render_jinja2_* functions.
"""

import importlib.resources

# Cache for loaded templates to avoid repeated file reads
_template_cache: dict[str, str] = {}


def load_template(package: str, template_name: str) -> str:
    """Load a template file from a Python package.

    Uses importlib.resources.files() for package-safe file access.
    Templates are cached after first load.

    Args:
        package: The dotted package path (e.g., "pipelex.graph.templates").
        template_name: The template filename (e.g., "mermaid_basic.html.jinja2").

    Returns:
        The template contents as a string.

    Raises:
        FileNotFoundError: If the template file doesn't exist.
    """
    cache_key = f"{package}:{template_name}"

    if cache_key in _template_cache:
        return _template_cache[cache_key]

    package_files = importlib.resources.files(package)
    template_path = package_files / template_name

    template_source = template_path.read_text(encoding="utf-8")
    _template_cache[cache_key] = template_source

    return template_source


def clear_template_cache() -> None:
    """Clear the template cache.

    Useful for testing or when templates may have changed.
    """
    _template_cache.clear()
