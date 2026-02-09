import pytest
from pydantic import ValidationError

from pipelex.cogt.image.prompt_image import PromptImageBase64, PromptImageUri
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.tools.misc.base64_utils import make_base64_url_from_path
from pipelex.tools.misc.http_utils import URL_MAX_LENGTH
from pipelex.urls import URLs
from tests.cases.images import ImageTestCases


class TestPromptImageFactoryDataUrl:
    """Test that PromptImageFactory correctly handles data URLs.

    Data URLs (data:image/...;base64,...) should be converted to PromptImageBase64,
    bypassing the URL_MAX_LENGTH (2048) validation that would otherwise fail
    for realistic-sized images.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("_topic", "image_path"),
        [
            ("png_solar_system", ImageTestCases.IMAGE_FILE_PATH_PNG_2),
            ("jpg_animal_lympics", ImageTestCases.IMAGE_FILE_PATH_JPG_1),
            ("png_ai_lympics", ImageTestCases.IMAGE_FILE_PATH_PNG_1),
            ("jpg_eiffel_tower", ImageTestCases.IMAGE_FILE_PATH_JPG_3),
        ],
    )
    async def test_make_prompt_image_with_realistic_data_url(
        self,
        _topic: str,
        image_path: str,
    ) -> None:
        """Test that realistic-sized data URLs work via the factory.

        These tests load actual image files (~100KB-600KB) and create data URLs.
        The data URLs will be tens to hundreds of thousands of characters,
        far exceeding URL_MAX_LENGTH (2048).
        Before the fix, this would fail with 'URI is too long'.
        """
        data_url = await make_base64_url_from_path(image_path)

        result = PromptImageFactory.make_prompt_image(uri=data_url)

        assert isinstance(result, PromptImageBase64)
        assert len(result.base64_data) > 100_000  # Realistic image size

    @pytest.mark.parametrize(
        ("_topic", "uri"),
        [
            ("http_url", URLs.png_example_1),
            ("https_url", URLs.jpg_example_1),
            ("local_absolute_path", "/path/to/image.png"),
            ("local_relative_path", "images/photo.jpg"),
            ("storage_uri", "pipelex-storage://images/test.png"),
        ],
    )
    def test_make_prompt_image_with_non_data_url_unchanged(
        self,
        _topic: str,
        uri: str,
    ) -> None:
        """Test that non-data URIs still create PromptImageUri.

        HTTP URLs, local paths, and storage URIs should continue to work
        and should NOT be converted to PromptImageBase64.
        """
        result = PromptImageFactory.make_prompt_image(uri=uri)

        assert isinstance(result, PromptImageUri)
        assert result.uri == uri

    def test_http_url_exceeding_max_length_fails(self) -> None:
        """Test that HTTP URLs exceeding URL_MAX_LENGTH still fail validation.

        Data URLs are exempt from URL_MAX_LENGTH, but HTTP URLs must still
        be validated to prevent excessively long URLs.
        """
        # Create an HTTP URL that exceeds the limit
        long_path = "a" * (URL_MAX_LENGTH + 100)
        long_http_url = f"https://example.com/{long_path}.png"

        with pytest.raises(ValidationError, match="URI is too long"):
            PromptImageFactory.make_prompt_image(uri=long_http_url)
