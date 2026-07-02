"""Unit tests for ImgGenParamSupport — capability checks against synthetic rules dicts."""

from __future__ import annotations

import pytest

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobParams,
    InputFidelity,
    SizeTier,
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


def _make_aspect_ratio_rules(taxonomy: AspectRatioTaxonomy) -> ImgGenModelRules:
    """Minimal rules dict carrying only the aspect_ratio topic — enough for geometry checks."""
    return {ImgGenArgTopic.ASPECT_RATIO: taxonomy}


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
        "aspect_ratio",
        [
            AspectRatio.LANDSCAPE_4_1,
            AspectRatio.LANDSCAPE_8_1,
            AspectRatio.PORTRAIT_1_4,
            AspectRatio.PORTRAIT_1_8,
        ],
    )
    def test_check_aspect_ratio_gpt_image_2_rejects_banner_ratios(self, aspect_ratio: AspectRatio) -> None:
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_gpt_image_2_rules(),
            aspect_ratio=aspect_ratio,
            size=None,
            model_name="gpt-image-2",
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "gpt-image-2" in check.reason

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
            size=None,
            background=None,
            output_format=None,
            model_name="gpt-image-1",
        )
        assert reasons == []

    def test_check_blueprint_params_flags_unsupported_aspect_ratio(self) -> None:
        reasons = ImgGenParamSupport.check_blueprint_params(
            rules=_make_legacy_openai_rules(),
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            size=None,
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

    @pytest.mark.parametrize(
        "taxonomy",
        [
            AspectRatioTaxonomy.FLUX,
            AspectRatioTaxonomy.FLUX_11_ULTRA,
            AspectRatioTaxonomy.QWEN_IMAGE,
            AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
            AspectRatioTaxonomy.GPT_IMAGE_2,
            AspectRatioTaxonomy.GEMINI_2_5,
            AspectRatioTaxonomy.GEMINI_3_PRO,
            AspectRatioTaxonomy.GEMINI_3_FLASH,
            AspectRatioTaxonomy.GEMINI_3_FLASH_LITE,
        ],
    )
    def test_tier_1k_is_satisfiable_everywhere(self, taxonomy: AspectRatioTaxonomy) -> None:
        """The '1k' tier is a portable no-op: every model natively produces a 1K-class image."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(taxonomy),
            aspect_ratio=AspectRatio.SQUARE,
            size=SizeTier.ONE_K,
            model_name="model-under-test",
        )
        assert check == SupportCheck(is_supported=True, reason=None)

    @pytest.mark.parametrize(
        ("taxonomy", "expected_supported"),
        [
            (AspectRatioTaxonomy.FLUX, False),
            (AspectRatioTaxonomy.FLUX_11_ULTRA, False),
            (AspectRatioTaxonomy.QWEN_IMAGE, False),
            (AspectRatioTaxonomy.GPT_IMAGE_LEGACY, False),
            (AspectRatioTaxonomy.GPT_IMAGE_2, True),
            (AspectRatioTaxonomy.GEMINI_2_5, False),
            (AspectRatioTaxonomy.GEMINI_3_PRO, True),
            (AspectRatioTaxonomy.GEMINI_3_FLASH, True),
            (AspectRatioTaxonomy.GEMINI_3_FLASH_LITE, False),
        ],
    )
    def test_tier_2k_support_matrix(self, taxonomy: AspectRatioTaxonomy, expected_supported: bool) -> None:
        """'2k' is satisfiable only on gpt-image-2 and the Gemini 3 (non-lite) generations."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(taxonomy),
            aspect_ratio=AspectRatio.SQUARE,
            size=SizeTier.TWO_K,
            model_name="model-under-test",
        )
        assert check.is_supported is expected_supported
        if not expected_supported:
            assert check.reason is not None

    @pytest.mark.parametrize(
        ("taxonomy", "expected_supported"),
        [
            (AspectRatioTaxonomy.FLUX, False),
            (AspectRatioTaxonomy.FLUX_11_ULTRA, False),
            (AspectRatioTaxonomy.QWEN_IMAGE, False),
            (AspectRatioTaxonomy.GPT_IMAGE_LEGACY, False),
            (AspectRatioTaxonomy.GPT_IMAGE_2, False),
            (AspectRatioTaxonomy.GEMINI_2_5, False),
            (AspectRatioTaxonomy.GEMINI_3_PRO, True),
            (AspectRatioTaxonomy.GEMINI_3_FLASH, True),
            (AspectRatioTaxonomy.GEMINI_3_FLASH_LITE, False),
        ],
    )
    def test_tier_4k_support_matrix(self, taxonomy: AspectRatioTaxonomy, expected_supported: bool) -> None:
        """'4k' is Gemini-3-only: gpt-image-2 caps out below 4K (honest refusal, no silent downgrade)."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(taxonomy),
            aspect_ratio=AspectRatio.SQUARE,
            size=SizeTier.FOUR_K,
            model_name="model-under-test",
        )
        assert check.is_supported is expected_supported
        if not expected_supported:
            assert check.reason is not None

    @pytest.mark.parametrize(
        "taxonomy",
        [
            AspectRatioTaxonomy.FLUX,
            AspectRatioTaxonomy.FLUX_11_ULTRA,
            AspectRatioTaxonomy.QWEN_IMAGE,
            AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
            AspectRatioTaxonomy.GPT_IMAGE_2,
            AspectRatioTaxonomy.GEMINI_2_5,
            AspectRatioTaxonomy.GEMINI_3_PRO,
            AspectRatioTaxonomy.GEMINI_3_FLASH,
            AspectRatioTaxonomy.GEMINI_3_FLASH_LITE,
        ],
    )
    def test_tier_half_k_rejected_everywhere(self, taxonomy: AspectRatioTaxonomy) -> None:
        """'0.5k' is a validation error on every model until the Gemini wire token is verified."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(taxonomy),
            aspect_ratio=AspectRatio.SQUARE,
            size=SizeTier.HALF_K,
            model_name="model-under-test",
        )
        assert check.is_supported is False
        assert check.reason is not None

    def test_gemini_3_pro_rejects_banner_ratio_even_at_1k(self) -> None:
        """Tier support does not override ratio gating: Pro has no banner ratios."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.GEMINI_3_PRO),
            aspect_ratio=AspectRatio.LANDSCAPE_4_1,
            size=SizeTier.ONE_K,
            model_name="nano-banana-pro",
        )
        assert check.is_supported is False

    def test_gemini_3_flash_supports_banner_ratio_at_2k(self) -> None:
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.GEMINI_3_FLASH),
            aspect_ratio=AspectRatio.LANDSCAPE_4_1,
            size=SizeTier.TWO_K,
            model_name="nano-banana-2",
        )
        assert check == SupportCheck(is_supported=True, reason=None)

    def test_exact_size_grid_hit_on_gemini_3_flash(self) -> None:
        """Worked example: a gpt-image-2 bundle with size '2048x2048' runs on nano-banana-2 (1:1 @ 2K)."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.GEMINI_3_FLASH),
            aspect_ratio=AspectRatio.SQUARE,
            size=ImageSize(width=2048, height=2048),
            model_name="nano-banana-2",
        )
        assert check == SupportCheck(is_supported=True, reason=None)

    def test_exact_size_grid_miss_on_gemini_3_flash_names_nearest_cells(self) -> None:
        """Worked example: '2000x2000' errors suggesting the nearest grid cell, never silently snaps."""
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.GEMINI_3_FLASH),
            aspect_ratio=AspectRatio.SQUARE,
            size=ImageSize(width=2000, height=2000),
            model_name="nano-banana-2",
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "2048x2048" in check.reason

    def test_exact_size_rejected_on_preset_only_taxonomy(self) -> None:
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.FLUX),
            aspect_ratio=AspectRatio.SQUARE,
            size=ImageSize(width=2048, height=2048),
            model_name="flux-dev",
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "exact image sizes" in check.reason

    def test_worked_example_16_9_at_2k_portability(self) -> None:
        """Design acceptance bar: 16:9 + '2k' runs on gemini_3_flash and gpt_image_2, fails on flux."""
        for taxonomy in [AspectRatioTaxonomy.GEMINI_3_FLASH, AspectRatioTaxonomy.GPT_IMAGE_2]:
            check = ImgGenParamSupport.check_aspect_ratio(
                rules=_make_aspect_ratio_rules(taxonomy),
                aspect_ratio=AspectRatio.LANDSCAPE_16_9,
                size=SizeTier.TWO_K,
                model_name="model-under-test",
            )
            assert check.is_supported is True, taxonomy
        flux_check = ImgGenParamSupport.check_aspect_ratio(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.FLUX),
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
            size=SizeTier.TWO_K,
            model_name="flux-pro",
        )
        assert flux_check.is_supported is False

    def test_check_blueprint_params_checks_explicit_size_without_aspect_ratio(self) -> None:
        """An explicitly-set size is checked even when aspect_ratio defers to the deck default."""
        reasons = ImgGenParamSupport.check_blueprint_params(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.FLUX),
            aspect_ratio=None,
            size=SizeTier.TWO_K,
            background=None,
            output_format=None,
            model_name="flux-dev",
        )
        assert len(reasons) == 1
        assert "flux-dev" in reasons[0]

    def test_check_blueprint_params_joint_aspect_ratio_and_tier(self) -> None:
        reasons = ImgGenParamSupport.check_blueprint_params(
            rules=_make_aspect_ratio_rules(AspectRatioTaxonomy.GEMINI_3_FLASH),
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
            size=SizeTier.TWO_K,
            background=None,
            output_format=None,
            model_name="nano-banana-2",
        )
        assert reasons == []
