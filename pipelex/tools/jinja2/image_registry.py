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
        """Register an image and return its 0-based index.

        Args:
            image: An ImageContent instance with a `url` attribute

        Returns:
            The 0-based index of the image in the registry.
            Convert to 1-based display number only at render time.

        Note: If the image URL was already registered, returns the existing index.
        """
        if image.url in self._image_urls:
            # Find existing index
            for index, existing in enumerate(self._images):
                if existing.url == image.url:
                    return index
        self._images.append(image)
        self._image_urls.add(image.url)
        return len(self._images) - 1

    def get_image_placeholder(self, image: Any) -> str | None:
        """Return the placeholder string for a registered image.

        Args:
            image: An ImageContent instance with a `url` attribute

        Returns:
            The placeholder string (e.g., "[Image 1]") if the image is registered,
            or None if the image is not in the registry.
        """
        for index, existing in enumerate(self._images):
            if existing.url == image.url:
                return f"[Image {index + 1}]"
        return None

    @property
    def images(self) -> list[Any]:
        """Return all registered images in order.

        Returns:
            A copy of the list of registered ImageContent instances.
        """
        return self._images.copy()
