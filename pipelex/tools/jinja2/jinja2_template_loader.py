"""Centralized template loader for Jinja2 templates.

This module provides two mechanisms for loading Jinja2 templates:

1. TemplateLoader class: Centralized loader that loads predefined template sets
   into the TemplateRegistry during Pipelex boot. Use this for templates that
   need to be pre-loaded before Temporal sandbox execution.

2. load_template() function: Simple utility to load a template by package/name.
   Use this for ad-hoc template loading outside sandboxed contexts.

Usage (TemplateLoader - for boot-time loading):
    from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
    TemplateLoader.load_all()  # During Pipelex.setup()

Usage (load_template - for ad-hoc loading):
    from pipelex.tools.jinja2.jinja2_template_loader import load_template
    template_source = load_template("mypackage.templates", "template.jinja2")
"""

import importlib.resources
from typing import ClassVar

from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry

# -----------------------------------------------------------------------------
# Simple template loading utility (for ad-hoc use)
# -----------------------------------------------------------------------------

# Cache for loaded templates to avoid repeated file reads
_template_cache: dict[str, str] = {}


def load_template(package: str, template_name: str) -> str:
    """Load a template file from a Python package.

    Uses importlib.resources.files() for package-safe file access.
    Templates are cached after first load.

    Note: This function performs I/O and should not be called inside
    Temporal sandboxes. For sandbox-safe access, use TemplateLoader to
    pre-load templates, then retrieve from TemplateRegistry.

    Args:
        package: The dotted package path (e.g., "pipelex.graph.templates").
        template_name: The template filename (e.g., "template.html.jinja2").

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


# -----------------------------------------------------------------------------
# Centralized template loader (for boot-time loading)
# -----------------------------------------------------------------------------


class TemplateLoader:
    """Centralized loader for all Jinja2 template sets.

    Template sets are registered at boot time by feature modules,
    then loaded into the TemplateRegistry for sandbox-safe rendering.
    """

    # Template set definitions: name -> (package, [(filename, registry_key), ...])
    _TEMPLATE_SETS: ClassVar[dict[str, tuple[str, list[tuple[str, str]]]]] = {}

    _loaded: ClassVar[set[str]] = set()

    @classmethod
    def register_set(
        cls,
        name: str,
        package: str,
        templates: list[tuple[str, str]],
    ) -> None:
        """Register a template set for loading.

        This method is idempotent - registering the same set multiple times
        is safe and will not raise an error.

        Args:
            name: The template set name (e.g., "reactflow").
            package: The package path where templates are located.
            templates: List of (filename, registry_key) tuples.
        """
        if name in cls._TEMPLATE_SETS:
            # Idempotent - already registered
            return
        cls._TEMPLATE_SETS[name] = (package, templates)

    @classmethod
    def load(cls, name: str) -> None:
        """Load a specific template set into the registry.

        This function is idempotent - calling it multiple times has no effect
        after the first successful load.

        Args:
            name: The template set name (e.g., "reactflow", "mermaid").

        Raises:
            ValueError: If the template set name is not defined.
        """
        if name in cls._loaded:
            return

        if name not in cls._TEMPLATE_SETS:
            available = list(cls._TEMPLATE_SETS.keys())
            msg = f"Unknown template set '{name}'. Available: {available}"
            raise ValueError(msg)

        package, templates = cls._TEMPLATE_SETS[name]
        package_files = importlib.resources.files(package)

        for filename, registry_key in templates:
            template_path = package_files / filename
            template_source = template_path.read_text(encoding="utf-8")
            TemplateRegistry.register(registry_key, template_source)

        cls._loaded.add(name)

    @classmethod
    def load_all(cls) -> None:
        """Load all defined template sets into the registry.

        This function is idempotent for each template set.
        """
        for name in cls._TEMPLATE_SETS:
            cls.load(name)

    @classmethod
    def reload(cls, name: str | None = None) -> None:
        """Force reload of templates from disk.

        Useful for development and testing.

        Args:
            name: Specific template set to reload, or None to reload all.
        """
        if name is None:
            cls._loaded.clear()
            cls.load_all()
        else:
            cls._loaded.discard(name)
            cls.load(name)

    @classmethod
    def is_loaded(cls, name: str) -> bool:
        """Check if a template set has been loaded.

        Args:
            name: The template set name.

        Returns:
            True if the template set has been loaded.
        """
        return name in cls._loaded

    @classmethod
    def available_sets(cls) -> list[str]:
        """Get list of available template set names.

        Returns:
            List of defined template set names.
        """
        return list(cls._TEMPLATE_SETS.keys())

    @classmethod
    def reset(cls) -> None:
        """Reset the loader state.

        Clears both the registered template sets and loaded tracking.
        Does not clear the registry itself. Useful for testing.
        """
        cls._TEMPLATE_SETS.clear()
        cls._loaded.clear()
