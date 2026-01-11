import pytest

from pipelex.tools.jinja2.image_registry import ImageRegistry


class MockImageContent:
    """Mock ImageContent for testing without importing the real class."""

    def __init__(self, url: str) -> None:
        self.url = url


class TestImageRegistry:
    """Tests for ImageRegistry class used by the | with_images filter."""

    def test_register_single_image_returns_index_0(self) -> None:
        """First registered image should get index 0."""
        registry = ImageRegistry()
        image = MockImageContent(url="http://example.com/image1.png")

        result = registry.register_image(image)

        assert result == 0

    def test_register_second_image_returns_index_1(self) -> None:
        """Second registered image should get index 1."""
        registry = ImageRegistry()
        image1 = MockImageContent(url="http://example.com/image1.png")
        image2 = MockImageContent(url="http://example.com/image2.png")

        registry.register_image(image1)
        result = registry.register_image(image2)

        assert result == 1

    def test_register_same_url_twice_returns_same_index(self) -> None:
        """Registering the same URL twice should return the original index."""
        registry = ImageRegistry()
        image1 = MockImageContent(url="http://example.com/same.png")
        image2 = MockImageContent(url="http://example.com/same.png")

        first_result = registry.register_image(image1)
        second_result = registry.register_image(image2)

        assert first_result == 0
        assert second_result == 0
        # Should only have one image in the registry
        assert len(registry.images) == 1

    def test_register_multiple_images_sequential_indexing(self) -> None:
        """Multiple different images should get sequential 0-based indexes."""
        registry = ImageRegistry()
        urls = [
            "http://example.com/a.png",
            "http://example.com/b.png",
            "http://example.com/c.png",
            "http://example.com/d.png",
        ]

        results: list[int] = []
        for url in urls:
            image = MockImageContent(url=url)
            results.append(registry.register_image(image))

        assert results == [0, 1, 2, 3]

    def test_images_property_returns_copy(self) -> None:
        """The images property should return a copy, not the internal list."""
        registry = ImageRegistry()
        image = MockImageContent(url="http://example.com/test.png")
        registry.register_image(image)

        images_copy = registry.images
        images_copy.append(MockImageContent(url="http://example.com/extra.png"))

        # Original registry should be unchanged
        assert len(registry.images) == 1

    def test_images_returns_correct_order(self) -> None:
        """Images should be returned in registration order."""
        registry = ImageRegistry()
        urls = ["http://example.com/first.png", "http://example.com/second.png", "http://example.com/third.png"]

        for url in urls:
            registry.register_image(MockImageContent(url=url))

        images = registry.images
        assert len(images) == 3
        assert images[0].url == "http://example.com/first.png"
        assert images[1].url == "http://example.com/second.png"
        assert images[2].url == "http://example.com/third.png"

    def test_empty_registry_returns_empty_list(self) -> None:
        """An empty registry should return an empty list."""
        registry = ImageRegistry()

        assert registry.images == []

    def test_duplicate_url_not_added_to_images_list(self) -> None:
        """Duplicate URLs should not result in duplicate entries in images list."""
        registry = ImageRegistry()
        url = "http://example.com/duplicate.png"

        registry.register_image(MockImageContent(url=url))
        registry.register_image(MockImageContent(url=url))
        registry.register_image(MockImageContent(url=url))

        assert len(registry.images) == 1

    @pytest.mark.parametrize(
        ("topic", "urls", "expected_count"),
        [
            ("single", ["http://a.com/1.png"], 1),
            ("two_unique", ["http://a.com/1.png", "http://a.com/2.png"], 2),
            ("three_with_duplicate", ["http://a.com/1.png", "http://a.com/2.png", "http://a.com/1.png"], 2),
            ("all_duplicates", ["http://same.com/x.png", "http://same.com/x.png", "http://same.com/x.png"], 1),
        ],
    )
    def test_deduplication_scenarios(self, topic: str, urls: list[str], expected_count: int) -> None:
        """Test various deduplication scenarios."""
        registry = ImageRegistry()

        for url in urls:
            registry.register_image(MockImageContent(url=url))

        assert len(registry.images) == expected_count, f"Failed for {topic}"
