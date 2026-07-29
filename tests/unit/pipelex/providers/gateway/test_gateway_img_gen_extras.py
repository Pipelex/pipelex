"""Tests for GatewayFactory.make_extras on gemini-routed image generation jobs.

The gateway threads the portable size into `extra_body["image_config"]`: a tier maps to
Google's `image_size` token, an exact size derives its grid cell from the model's taxonomy
rules, and an unset size omits `image_size` entirely (provider default, never an upgrade).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy, ImgGenArgTopic
from pipelex.providers.gateway.gateway_factory import GatewayFactory

GEMINI_RULES: dict[str, str] = {ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GEMINI_3_FLASH}


def _make_model(mocker: MockerFixture, *, model_id: str = "gemini-3-flash-image", rules: dict[str, str] | None = None) -> Any:
    model = mocker.MagicMock()
    model.model_id = model_id
    model.name = "nano-banana-2"
    model.backend_name = "google"
    model.extra_headers = {}
    model.rules = rules
    return model


def _make_img_gen_job(mocker: MockerFixture, *, aspect_ratio: AspectRatio, size: SizeTier | ImageSize | None) -> Any:
    job = mocker.MagicMock(spec=ImgGenJob)
    job.job_params = ImgGenJobParams(aspect_ratio=aspect_ratio, size=size, background=Background.AUTO)
    return job


@pytest.fixture
def disable_gateway_telemetry(mocker: MockerFixture) -> None:
    telemetry_manager = mocker.MagicMock()
    telemetry_manager.is_pipelex_gateway_portkey_tracing_enabled.return_value = False
    mocker.patch("pipelex.providers.gateway.gateway_factory.get_telemetry_manager", return_value=telemetry_manager)


@pytest.mark.usefixtures("disable_gateway_telemetry")
class TestGatewayImgGenExtras:
    def test_tier_threads_image_size_token(self, mocker: MockerFixture) -> None:
        """A portable tier lands in extra_body as Google's `image_size` wire token."""
        model = _make_model(mocker, rules=GEMINI_RULES)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=SizeTier.TWO_K)

        _, extra_body = GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

        assert extra_body == {"image_config": {"aspect_ratio": "1:1", "image_size": "2K"}}

    def test_unset_size_omits_image_size(self, mocker: MockerFixture) -> None:
        """No size on the job -> no `image_size` key at all; the provider applies its own default."""
        model = _make_model(mocker, rules=GEMINI_RULES)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.LANDSCAPE_16_9, size=None)

        _, extra_body = GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

        assert extra_body == {"image_config": {"aspect_ratio": "16:9"}}

    def test_exact_size_derives_grid_cell_from_rules(self, mocker: MockerFixture) -> None:
        """An exact WxH derives its (ratio, size) grid cell via the model's taxonomy rules."""
        model = _make_model(mocker, rules=GEMINI_RULES)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=ImageSize(width=2752, height=1536))

        _, extra_body = GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

        assert extra_body == {"image_config": {"aspect_ratio": "16:9", "image_size": "2K"}}

    def test_exact_size_without_rules_raises(self, mocker: MockerFixture) -> None:
        """An exact size cannot be derived without taxonomy rules — clear error, never a silent drop."""
        model = _make_model(mocker, rules=None)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=ImageSize(width=2752, height=1536))

        with pytest.raises(ImgGenParameterError, match="rules"):
            GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

    def test_tier_without_rules_raises(self, mocker: MockerFixture) -> None:
        """A tier cannot be validated without taxonomy rules — clear error, never a silent forward."""
        model = _make_model(mocker, rules=None)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=SizeTier.FOUR_K)

        with pytest.raises(ImgGenParameterError, match="rules"):
            GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

    def test_tier_beyond_taxonomy_raises(self, mocker: MockerFixture) -> None:
        """A tier the model's taxonomy cannot produce is rejected client-side, same as the native worker."""
        model = _make_model(mocker, rules={ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GEMINI_2_5})
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=SizeTier.TWO_K)

        with pytest.raises(ImgGenParameterError, match="does not support image size"):
            GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

    def test_unset_size_without_rules_keeps_ratio_only_mapping(self, mocker: MockerFixture) -> None:
        """With no size requested and no rules to validate against, the plain ratio mapping is kept."""
        model = _make_model(mocker, rules=None)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.PORTRAIT_9_16, size=None)

        _, extra_body = GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

        assert extra_body == {"image_config": {"aspect_ratio": "9:16"}}

    def test_unset_size_with_unknown_taxonomy_keeps_ratio_only_mapping(self, mocker: MockerFixture) -> None:
        """A remotely-fetched spec may carry a taxonomy string that predates this factory: with no size
        requested, the wire path must abstain (like the support checks) and keep the plain ratio mapping.
        """
        model = _make_model(mocker, rules={ImgGenArgTopic.ASPECT_RATIO: "legacy_gateway_taxonomy"})
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.PORTRAIT_9_16, size=None)

        _, extra_body = GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

        assert extra_body == {"image_config": {"aspect_ratio": "9:16"}}

    def test_sized_request_with_unknown_taxonomy_raises(self, mocker: MockerFixture) -> None:
        """A size cannot be validated against an unknown taxonomy — clear error, never a silent forward."""
        model = _make_model(mocker, rules={ImgGenArgTopic.ASPECT_RATIO: "legacy_gateway_taxonomy"})
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=SizeTier.TWO_K)

        with pytest.raises(ImgGenParameterError, match="unknown aspect_ratio taxonomy"):
            GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

    def test_non_gemini_img_gen_job_gets_no_image_config(self, mocker: MockerFixture) -> None:
        """Only gemini-routed img-gen jobs get an `image_config` block."""
        model = _make_model(mocker, model_id="gpt-image-1", rules=None)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=SizeTier.TWO_K)

        _, extra_body = GatewayFactory.make_extras(model, inference_job=job, output_desc="Image")

        assert extra_body == {}
