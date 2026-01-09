"""Image registry for tracking images in Jinja2 templates.

This module is kept separate to avoid circular imports.
The ImageContent type is referenced using Any to prevent import cycles.
"""

from typing import Any


class ImageRegistry:
    """Registry for tracking images and their assigned numbers in templates.

    Used by the `with_images` filter to:
    1. Track images that have been encountered
    2. Assign unique numbers to each image
    3. Provide the final list of images in order

    Note: Images are stored as Any to avoid circular imports with ImageContent.
    At runtime, they are expected to be ImageContent instances with a `url` attribute.
    """

    def __init__(self) -> None:
        self._images: list[Any] = []
        self._image_urls: set[str] = set()

    def register_image(self, image: Any) -> int:
        """Register an image and return its assigned number (1-indexed).

        Args:
            image: An ImageContent instance with a `url` attribute

        Returns:
            The assigned image number (1-indexed)

        Note: If the image URL was already registered, returns the existing number.
        """
        if image.url in self._image_urls:
            # Find existing index
            for idx, existing in enumerate(self._images):
                if existing.url == image.url:
                    # KLUDGE: avoid 1-indexing until it's a token
                    return idx + 1
        self._images.append(image)
        self._image_urls.add(image.url)
        return len(self._images)

    @property
    def images(self) -> list[Any]:
        """Return all registered images in order.

        Returns:
            A copy of the list of registered ImageContent instances.
        """
        return self._images.copy()
