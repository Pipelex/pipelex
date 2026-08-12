"""Tests for the config-level size default resolution against a step's explicit aspect_ratio."""

import pytest

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.kernel.img_gen_ops import resolve_default_size


class TestResolveDefaultSize:
    @pytest.mark.parametrize(
        ("explicit_aspect_ratio", "default_size", "expected"),
        [
            pytest.param(AspectRatio.LANDSCAPE_16_9, ImageSize(width=2048, height=1152), None, id="explicit-ratio-suppresses-exact-default"),
            pytest.param(AspectRatio.LANDSCAPE_16_9, SizeTier.TWO_K, SizeTier.TWO_K, id="tier-default-composes-with-explicit-ratio"),
            pytest.param(None, ImageSize(width=2048, height=1152), ImageSize(width=2048, height=1152), id="exact-default-applies-without-ratio"),
            pytest.param(None, SizeTier.TWO_K, SizeTier.TWO_K, id="tier-default-applies-without-ratio"),
            pytest.param(AspectRatio.SQUARE, None, None, id="no-default-stays-none"),
        ],
    )
    def test_resolve_default_size(
        self,
        explicit_aspect_ratio: AspectRatio | None,
        default_size: SizeTier | ImageSize | None,
        expected: SizeTier | ImageSize | None,
    ):
        """An exact-size deck default must not silently defeat a pipe's explicit aspect_ratio; tiers always compose."""
        assert resolve_default_size(explicit_aspect_ratio=explicit_aspect_ratio, default_size=default_size) == expected
