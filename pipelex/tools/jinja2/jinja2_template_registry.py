"""Template registry for sandbox-safe Jinja2 rendering.

This module provides a pre-loaded template registry that enables Jinja2 template
rendering without filesystem access at render time. Templates are registered
at module import time (outside Temporal sandboxes) and served via DictLoader.

Key benefits:
- Temporal.io sandbox compatible (no I/O at render time)
- Supports {% include %} statements via DictLoader
- Templates cached in memory after first load
"""

from typing import ClassVar

from jinja2 import DictLoader


class TemplateRegistry:
    """Pre-loaded template registry for sandbox-safe Jinja2 rendering.

    Templates are registered by key and served from an in-memory dictionary.
    This allows Jinja2's DictLoader to resolve {% include %} statements
    without filesystem access.

    Usage:
        # At module import time (outside sandbox):
        TemplateRegistry.register("myapp/base.html.jinja2", template_source)

        # At render time (inside sandbox):
        template_source = TemplateRegistry.get("myapp/base.html.jinja2")
        # Or use get_dict_loader() for {% include %} support
    """

    _templates: ClassVar[dict[str, str]] = {}

    @classmethod
    def register(cls, key: str, template_source: str) -> None:
        """Register a template string under a key.

        Args:
            key: Unique identifier for the template (e.g., "reactflow/main.html.jinja2").
            template_source: The template content as a string.
        """
        cls._templates[key] = template_source

    @classmethod
    def get(cls, key: str) -> str:
        """Get a pre-loaded template by key.

        Args:
            key: The template key used during registration.

        Returns:
            The template content as a string.

        Raises:
            KeyError: If the template key is not registered.
        """
        if key not in cls._templates:
            msg = f"Template '{key}' not found in registry. Available: {list(cls._templates.keys())}"
            raise KeyError(msg)
        return cls._templates[key]

    @classmethod
    def get_dict_loader(cls) -> DictLoader:
        """Get a DictLoader serving all registered templates.

        The DictLoader enables {% include %} statements to resolve templates
        from the registry without filesystem access.

        Returns:
            A Jinja2 DictLoader backed by the registry.
        """
        return DictLoader(cls._templates)

    @classmethod
    def is_registered(cls, key: str) -> bool:
        """Check if a template is registered.

        Args:
            key: The template key to check.

        Returns:
            True if the template is registered, False otherwise.
        """
        return key in cls._templates

    @classmethod
    def clear(cls) -> None:
        """Clear all registered templates.

        Useful for testing to reset state between tests.
        """
        cls._templates.clear()

    @classmethod
    def keys(cls) -> list[str]:
        """Get all registered template keys.

        Returns:
            List of registered template keys.
        """
        return list(cls._templates.keys())
