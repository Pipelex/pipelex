import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.image_content import ImageContent
from tests.unit.pipelex.core.stuffs.image_content.test_data import TestData


class TestImageContentDimensions:
    @pytest.mark.parametrize(
        ("width", "height"),
        [
            pytest.param(640, None, id="width-only"),
            pytest.param(None, 480, id="height-only"),
            pytest.param(0, 480, id="zero-width"),
            pytest.param(640, -1, id="negative-height"),
        ],
    )
    def test_rejects_unpaired_or_non_positive_dimensions(self, width: int | None, height: int | None) -> None:
        with pytest.raises(ValidationError):
            ImageContent(url=TestData.SAMPLE_URL, width=width, height=height)

    @pytest.mark.parametrize(
        ("width", "height"),
        [
            pytest.param(None, None, id="dimensions-unknown"),
            pytest.param(640, 480, id="dimensions-known"),
        ],
    )
    def test_accepts_both_dimensions_or_neither(self, width: int | None, height: int | None) -> None:
        image = ImageContent(url=TestData.SAMPLE_URL, width=width, height=height)
        assert image.width == width
        assert image.height == height
