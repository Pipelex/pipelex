import pytest
from pydantic import ValidationError

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, SizeTier


class TestImgGenSizeParsing:
    @pytest.mark.parametrize(
        ("size_input", "expected_tier"),
        [
            ("0.5k", SizeTier.HALF_K),
            ("1k", SizeTier.ONE_K),
            ("2k", SizeTier.TWO_K),
            ("4k", SizeTier.FOUR_K),
        ],
    )
    def test_parse_tier_token(self, size_input: str, expected_tier: SizeTier):
        """A tier token string parses to the matching SizeTier member."""
        params = ImgGenJobParams.model_validate({"aspect_ratio": "square", "background": "auto", "size": size_input})
        assert params.size is expected_tier

    @pytest.mark.parametrize(
        ("size_input", "expected_width", "expected_height"),
        [
            ("1024x768", 1024, 768),
            ("2048x1152", 2048, 1152),
            ("16x16", 16, 16),
        ],
    )
    def test_parse_exact_size(self, size_input: str, expected_width: int, expected_height: int):
        """A 'WxH' string parses to an ImageSize with the given dimensions."""
        params = ImgGenJobParams.model_validate({"aspect_ratio": "square", "background": "auto", "size": size_input})
        assert params.size == ImageSize(width=expected_width, height=expected_height)

    @pytest.mark.parametrize(
        "size_input",
        [
            "huge",
            "3k",
            "1.5k",
            "1024",
            "1024x",
            "x768",
            "0x0",
            "0x768",
            "1024 x 768",
            "1024X768",
            "",
        ],
    )
    def test_parse_garbage_raises(self, size_input: str):
        """Anything that is neither a tier token nor a positive 'WxH' raises a clear error."""
        with pytest.raises(ValidationError, match="expected a size tier"):
            ImgGenJobParams.model_validate({"aspect_ratio": "square", "background": "auto", "size": size_input})

    @pytest.mark.parametrize(
        "size_table",
        [
            {"width": 0, "height": 768},
            {"width": 1024, "height": 0},
            {"width": -1024, "height": 768},
            {"width": 1024, "height": -768},
        ],
    )
    def test_non_positive_exact_size_table_rejected(self, size_table: dict[str, int]):
        """The table wire form bypasses the 'WxH' string regex, so ImageSize itself must reject non-positive dims."""
        with pytest.raises(ValidationError, match="greater than 0"):
            ImgGenJobParams.model_validate({"aspect_ratio": "square", "background": "auto", "size": size_table})

    def test_native_values_pass_through(self):
        """SizeTier and ImageSize instances (and None) are accepted as-is."""
        tier_params = ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO, size=SizeTier.TWO_K)
        assert tier_params.size is SizeTier.TWO_K

        exact_params = ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO, size=ImageSize(width=1024, height=1024))
        assert exact_params.size == ImageSize(width=1024, height=1024)

        unset_params = ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO)
        assert unset_params.size is None

    @pytest.mark.parametrize(
        "size_value",
        [
            SizeTier.HALF_K,
            SizeTier.ONE_K,
            SizeTier.TWO_K,
            SizeTier.FOUR_K,
            ImageSize(width=2048, height=1152),
        ],
    )
    def test_serialization_round_trip(self, size_value: SizeTier | ImageSize):
        """Both union arms survive a JSON-mode dump/validate round trip with the expected wire shape."""
        params = ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO, size=size_value)
        dumped = params.model_dump(mode="json")
        if isinstance(size_value, SizeTier):
            assert dumped["size"] == str(size_value)
        else:
            assert dumped["size"] == {"width": size_value.width, "height": size_value.height}
        restored = ImgGenJobParams.model_validate(dumped)
        assert restored.size == params.size
        assert restored == params

    def test_unset_size_round_trip(self):
        """An unset size stays None through a JSON-mode round trip."""
        params = ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO)
        dumped = params.model_dump(mode="json")
        assert dumped["size"] is None
        restored = ImgGenJobParams.model_validate(dumped)
        assert restored.size is None
