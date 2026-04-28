"""Unit tests for ImgGenParamSupport — capability checks against synthetic rules dicts."""

from __future__ import annotations

import pytest

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobParams,
    InputFidelity,
)
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    BackgroundTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    InputFidelityTaxonomy,
    InputImagesTaxonomy,
    ModelChoiceTaxonomy,
    NumImagesTaxonomy,
    OutputFormatTaxonomy,
    PromptTaxonomy,
    SafetyCheckerTaxonomy,
)
from pipelex.cogt.img_gen.img_gen_param_support import ImgGenParamSupport, SupportCheck
from pipelex.tools.misc.image_utils import ImageFormat


def _make_legacy_openai_rules() -> ImgGenModelRules:
    """Rules matching gpt-image-1 / gpt-image-1-mini / gpt-image-1.5."""
    return {
        ImgGenArgTopic.MODEL_CHOICE: ModelChoiceTaxonomy.MODEL_ID,
        ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY,
        ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.GPT_IMAGE,
        ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
        ImgGenArgTopic.BACKGROUND: BackgroundTaxonomy.AVAILABLE,
        ImgGenArgTopic.INFERENCE: InferenceTaxonomy.GPT_IMAGE,
        ImgGenArgTopic.SAFETY_CHECKER: SafetyCheckerTaxonomy.OPENAI_MODERATION,
        ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.GPT_IMAGE_LEGACY,
        ImgGenArgTopic.INPUT_IMAGES: InputImagesTaxonomy.GPT_IMAGE,
        ImgGenArgTopic.INPUT_FIDELITY: InputFidelityTaxonomy.GPT_IMAGE_LEGACY,
    }


def _make_gpt_image_2_rules() -> ImgGenModelRules:
    """Rules matching gpt-image-2."""
    return {
        ImgGenArgTopic.MODEL_CHOICE: ModelChoiceTaxonomy.MODEL_ID,
        ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY,
        ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.GPT_IMAGE,
        ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GPT_IMAGE_2,
        ImgGenArgTopic.BACKGROUND: BackgroundTaxonomy.UNAVAILABLE,
        ImgGenArgTopic.INFERENCE: InferenceTaxonomy.GPT_IMAGE,
        ImgGenArgTopic.SAFETY_CHECKER: SafetyCheckerTaxonomy.UNAVAILABLE,
        ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.UNAVAILABLE,
        ImgGenArgTopic.INPUT_IMAGES: InputImagesTaxonomy.GPT_IMAGE,
        ImgGenArgTopic.INPUT_FIDELITY: InputFidelityTaxonomy.UNAVAILABLE,
    }


def _make_sdxl_rules() -> ImgGenModelRules:
    """Rules matching SDXL family — uses different output_format taxonomy that rejects WEBP."""
    return {
        ImgGenArgTopic.PROMPT: PromptTaxonomy.WITH_NEGATIVE,
        ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.FAL,
        ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.SDXL,
    }


class TestImgGenParamSupport:
    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_supported"),
        [
            (AspectRatio.SQUARE, True),
            (AspectRatio.LANDSCAPE_3_2, True),
            (AspectRatio.PORTRAIT_2_3, True),
            (AspectRatio.LANDSCAPE_4_3, False),
            (AspectRatio.PORTRAIT_9_16, False),
            (AspectRatio.LANDSCAPE_21_9, False),
        ],
    )
    def test_check_aspect_ratio_legacy_openai(self, aspect_ratio: AspectRatio, expected_supported: bool) -> None:
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_legacy_openai_rules(),
            aspect_ratio=aspect_ratio,
            size=None,
            model_name="gpt-image-1",
        )
        assert check.is_supported is expected_supported
        if not expected_supported:
            assert check.reason is not None
            assert "gpt-image-1" in check.reason

    @pytest.mark.parametrize(
        "aspect_ratio",
        [
            AspectRatio.SQUARE,
            AspectRatio.LANDSCAPE_4_3,
            AspectRatio.LANDSCAPE_16_9,
            AspectRatio.PORTRAIT_9_16,
            AspectRatio.LANDSCAPE_21_9,
        ],
    )
    def test_check_aspect_ratio_gpt_image_2_supports_all_listed(self, aspect_ratio: AspectRatio) -> None:
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_gpt_image_2_rules(),
            aspect_ratio=aspect_ratio,
            size=None,
            model_name="gpt-image-2",
        )
        assert check == SupportCheck(is_supported=True, reason=None)

    @pytest.mark.parametrize(
        ("background", "expected_supported"),
        [
            (Background.OPAQUE, True),
            (Background.AUTO, True),
            (Background.TRANSPARENT, False),
        ],
    )
    def test_check_background_unavailable_rejects_transparent(self, background: Background, expected_supported: bool) -> None:
        check = ImgGenParamSupport.check_background(
            rules=_make_gpt_image_2_rules(),
            background=background,
            model_name="gpt-image-2",
        )
        assert check.is_supported is expected_supported
        if not expected_supported:
            assert check.reason is not None
            assert "gpt-image-2" in check.reason
            assert "transparent" in check.reason.lower()

    @pytest.mark.parametrize(
        "background",
        [Background.OPAQUE, Background.AUTO, Background.TRANSPARENT],
    )
    def test_check_background_available_supports_all(self, background: Background) -> None:
        check = ImgGenParamSupport.check_background(
            rules=_make_legacy_openai_rules(),
            background=background,
            model_name="gpt-image-1",
        )
        assert check.is_supported is True

    def test_check_output_format_sdxl_rejects_webp(self) -> None:
        check = ImgGenParamSupport.check_output_format(
            rules=_make_sdxl_rules(),
            output_format=ImageFormat.WEBP,
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "WebP" in check.reason

    @pytest.mark.parametrize("output_format", [ImageFormat.PNG, ImageFormat.JPEG])
    def test_check_output_format_sdxl_accepts_png_jpeg(self, output_format: ImageFormat) -> None:
        check = ImgGenParamSupport.check_output_format(
            rules=_make_sdxl_rules(),
            output_format=output_format,
        )
        assert check.is_supported is True

    def test_check_output_format_none_is_supported(self) -> None:
        """None means provider default — always considered supported regardless of taxonomy."""
        for rules in [_make_legacy_openai_rules(), _make_gpt_image_2_rules(), _make_sdxl_rules()]:
            check = ImgGenParamSupport.check_output_format(rules=rules, output_format=None)
            assert check == SupportCheck(is_supported=True, reason=None)

    def test_check_input_fidelity_unavailable_rejects_set_value(self) -> None:
        check = ImgGenParamSupport.check_input_fidelity(
            rules=_make_gpt_image_2_rules(),
            input_fidelity=InputFidelity.HIGH,
            model_name="gpt-image-2",
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "gpt-image-2" in check.reason
        assert "input_fidelity" in check.reason

    def test_check_input_fidelity_unavailable_accepts_none(self) -> None:
        check = ImgGenParamSupport.check_input_fidelity(
            rules=_make_gpt_image_2_rules(),
            input_fidelity=None,
            model_name="gpt-image-2",
        )
        assert check.is_supported is True

    def test_check_input_fidelity_topic_missing_rejects_set_value(self) -> None:
        rules: ImgGenModelRules = {ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY}
        check = ImgGenParamSupport.check_input_fidelity(
            rules=rules,
            input_fidelity=InputFidelity.LOW,
            model_name="some-model",
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "some-model" in check.reason

    def test_check_input_images_topic_present_supports(self) -> None:
        check = ImgGenParamSupport.check_input_images_topic(rules=_make_legacy_openai_rules(), has_input_images=True)
        assert check.is_supported is True

    def test_check_input_images_topic_missing_rejects_when_provided(self) -> None:
        rules: ImgGenModelRules = {ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY}
        check = ImgGenParamSupport.check_input_images_topic(rules=rules, has_input_images=True)
        assert check.is_supported is False
        assert check.reason is not None
        assert "input_images" in check.reason

    def test_check_input_images_topic_missing_supports_when_none(self) -> None:
        rules: ImgGenModelRules = {ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY}
        check = ImgGenParamSupport.check_input_images_topic(rules=rules, has_input_images=False)
        assert check.is_supported is True

    def test_check_job_params_aggregate_legacy_openai_unsupported_aspect_ratio(self) -> None:
        params = ImgGenJobParams(
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )
        reasons = ImgGenParamSupport.check_job_params(
            rules=_make_legacy_openai_rules(),
            params=params,
            model_name="gpt-image-1",
        )
        assert len(reasons) == 1
        assert "LANDSCAPE_4_3" in reasons[0] or "landscape_4_3" in reasons[0]

    def test_check_job_params_aggregate_gpt_image_2_supports(self) -> None:
        params = ImgGenJobParams(
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )
        reasons = ImgGenParamSupport.check_job_params(
            rules=_make_gpt_image_2_rules(),
            params=params,
            model_name="gpt-image-2",
        )
        assert reasons == []

    def test_check_job_params_aggregate_multiple_unsupported(self) -> None:
        """gpt-image-2 rejects both transparent background and explicit input_fidelity."""
        params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.TRANSPARENT,
            input_fidelity=InputFidelity.HIGH,
            output_format=ImageFormat.PNG,
        )
        reasons = ImgGenParamSupport.check_job_params(
            rules=_make_gpt_image_2_rules(),
            params=params,
            model_name="gpt-image-2",
        )
        assert len(reasons) == 2

    def test_check_blueprint_params_skips_none_fields(self) -> None:
        """Blueprint defers to deck defaults when fields are None — those should NOT be flagged."""
        reasons = ImgGenParamSupport.check_blueprint_params(
            rules=_make_legacy_openai_rules(),
            aspect_ratio=None,
            background=None,
            output_format=None,
            model_name="gpt-image-1",
        )
        assert reasons == []

    def test_check_blueprint_params_flags_unsupported_aspect_ratio(self) -> None:
        reasons = ImgGenParamSupport.check_blueprint_params(
            rules=_make_legacy_openai_rules(),
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            background=None,
            output_format=None,
            model_name="gpt-image-1",
        )
        assert len(reasons) == 1
        assert "gpt-image-1" in reasons[0]

    def test_check_aspect_ratio_with_explicit_size(self) -> None:
        """For legacy OpenAI, explicit size also goes through the same checker."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_legacy_openai_rules(),
            aspect_ratio=AspectRatio.SQUARE,
            size=ImageSize(width=999, height=999),
            model_name="gpt-image-1",
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "999x999" in check.reason

    def test_empty_rules_supports_everything(self) -> None:
        """An empty rules dict (no topic configured) means no taxonomy check kicks in."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules={},
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            size=None,
            model_name="any-model",
        )
        assert check.is_supported is True
