"""Protocol for types that can render with image extraction.

This module defines the ImageRenderable protocol, which enables the `with_images`
Jinja2 filter to work with any type that implements the `render_with_images` method.

The protocol uses `@runtime_checkable` to allow isinstance() checks at runtime,
which enables the filter to determine if a value can be rendered with image extraction
without importing concrete types (avoiding circular imports).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pipelex.cogt.templating.text_format import TextFormat
    from pipelex.tools.jinja2.image_registry import ImageRegistry


@runtime_checkable
class ImageRenderable(Protocol):
    """Protocol for types that can render with image extraction.

    Types implementing this protocol can be used with the `with_images` filter.
    The filter will call `render_with_images()` to get the rendered string
    with image tokens ([Image N]) in place of actual images.

    Implementations:
    - StuffContent (base): iterates model fields, recurses into nested content
    - ImageContent: registers itself and returns [Image N] token
    - ListContent: renders each item with images
    - TextAndImagesContent: renders text, then registers images
    - StuffArtefact: delegates to underlying content
    """

    def render_with_images(
        self,
        registry: ImageRegistry,
        text_format: TextFormat,
    ) -> str:
        """Render to string, registering images to the registry.

        Args:
            registry: ImageRegistry to track discovered images
            text_format: Format for rendering text content

        Returns:
            String representation with [Image N] tokens where images appear.
            Image indices are 1-based in the output (e.g., [Image 1], [Image 2]).
        """
        ...
