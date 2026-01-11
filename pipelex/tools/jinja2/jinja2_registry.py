"""Registry for Jinja2 type-checking functions to avoid circular imports.

This module provides a registry pattern to decouple low-level Jinja2 filters
from high-level domain types (StuffArtefact, ImageContent, etc.).

The registry holds callable functions that are registered during application
boot, allowing the filters to check types without importing the actual classes.
"""

from collections.abc import Callable
from typing import Any

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.system.registries.singleton import MetaSingleton
from pipelex.tools.jinja2.image_registry import ImageRegistry


class Jinja2Registry(metaclass=MetaSingleton):
    """Singleton registry for Jinja2 type-checking and rendering functions."""

    def __init__(self) -> None:
        self._can_contain_images: Callable[[Any], bool] | None = None
        self._render_value_with_images: Callable[[Any, ImageRegistry, TextFormat], str] | None = None

    def register_can_contain_images(self, func: Callable[[Any], bool]) -> None:
        """Register the function that checks if a value can contain images."""
        self._can_contain_images = func

    def register_render_value_with_images(self, func: Callable[[Any, ImageRegistry, TextFormat], str]) -> None:
        """Register the function that renders a value with image placeholders."""
        self._render_value_with_images = func

    def can_contain_images(self, value: Any) -> bool:
        """Check if a value can potentially contain images.

        Raises:
            RuntimeError: If the function has not been registered.
        """
        if self._can_contain_images is None:
            msg = "can_contain_images function not registered. Call register_can_contain_images during setup."
            raise RuntimeError(msg)
        return self._can_contain_images(value)

    def render_value_with_images(self, value: Any, registry: ImageRegistry, text_format: TextFormat) -> str:
        """Render a value, extracting images and replacing with placeholders.

        Raises:
            RuntimeError: If the function has not been registered.
        """
        if self._render_value_with_images is None:
            msg = "render_value_with_images function not registered. Call register_render_value_with_images during setup."
            raise RuntimeError(msg)
        return self._render_value_with_images(value, registry, text_format)


def get_jinja2_registry() -> Jinja2Registry:
    """Get the Jinja2Registry singleton instance."""
    return Jinja2Registry()
