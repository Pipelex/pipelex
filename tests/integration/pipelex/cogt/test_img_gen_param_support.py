"""Integration tests for ImgGenParamSupport against the real loaded model deck.

These run without contacting any inference API: they only read rules from the
deck and verify the helper produces the expected accept/reject verdicts for
parameter values that real users would reasonably try.
"""

from __future__ import annotations

import pytest

from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobParams,
    InputFidelity,
)
from pipelex.cogt.img_gen.img_gen_param_support import ImgGenParamSupport
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.runtime_hub import get_model_deck
from pipelex.tools.misc.image_utils import ImageFormat


class TestImgGenParamSupportIntegration:
    """Verifies ImgGenParamSupport against rules loaded from the real model deck."""

    @pytest.mark.parametrize(
        "model_handle",
        ["gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"],
    )
    def test_legacy_openai_rejects_landscape_4_3(self, model_handle: str) -> None:
        spec = get_model_deck().get_optional_inference_model(model_handle=model_handle, model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip(f"Model '{model_handle}' not in current deck")
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=spec.rules,
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            size=None,
            model_name=spec.name,
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert spec.name in check.reason

    @pytest.mark.parametrize(
        "model_handle",
        ["gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"],
    )
    def test_legacy_openai_accepts_square(self, model_handle: str) -> None:
        spec = get_model_deck().get_optional_inference_model(model_handle=model_handle, model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip(f"Model '{model_handle}' not in current deck")
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=spec.rules,
            aspect_ratio=AspectRatio.SQUARE,
            size=None,
            model_name=spec.name,
        )
        assert check.is_supported is True

    def test_gpt_image_2_rejects_transparent_background(self) -> None:
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-2", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("Model 'gpt-image-2' not in current deck")
        check = ImgGenParamSupport.check_background(
            rules=spec.rules,
            background=Background.TRANSPARENT,
            model_name=spec.name,
        )
        assert check.is_supported is False
        assert check.reason is not None
        assert "transparent" in check.reason.lower()

    def test_gpt_image_2_rejects_explicit_input_fidelity(self) -> None:
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-2", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("Model 'gpt-image-2' not in current deck")
        check = ImgGenParamSupport.check_input_fidelity(
            rules=spec.rules,
            input_fidelity=InputFidelity.HIGH,
            model_name=spec.name,
        )
        assert check.is_supported is False

    @pytest.mark.parametrize(
        "aspect_ratio",
        [
            AspectRatio.SQUARE,
            AspectRatio.LANDSCAPE_4_3,
            AspectRatio.LANDSCAPE_16_9,
            AspectRatio.PORTRAIT_3_4,
            AspectRatio.PORTRAIT_9_16,
        ],
    )
    def test_gpt_image_2_supports_broader_aspect_ratios(self, aspect_ratio: AspectRatio) -> None:
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-2", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("Model 'gpt-image-2' not in current deck")
        check = ImgGenParamSupport.check_aspect_ratio(
            rules=spec.rules,
            aspect_ratio=aspect_ratio,
            size=None,
            model_name=spec.name,
        )
        assert check.is_supported is True

    def test_check_job_params_legacy_openai_with_unsupported_combo(self) -> None:
        """Reproduces the C.2 probe failure for img_gen_job_params2 (LANDSCAPE_4_3, JPEG)."""
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("Model 'gpt-image-1' not in current deck")
        params = ImgGenJobParams(
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            background=Background.OPAQUE,
            output_format=ImageFormat.JPEG,
        )
        reasons = ImgGenParamSupport.check_job_params(
            inference_model=spec,
            params=params,
        )
        assert len(reasons) >= 1
        assert any("landscape_4_3" in reason.lower() for reason in reasons)

    def test_check_job_params_legacy_openai_with_supported_combo(self) -> None:
        """Square + opaque + PNG should be supported by every legacy OpenAI img-gen model."""
        spec = get_model_deck().get_optional_inference_model(model_handle="gpt-image-1", model_type=ModelType.IMG_GEN)
        if spec is None or spec.rules is None:
            pytest.skip("Model 'gpt-image-1' not in current deck")
        params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )
        reasons = ImgGenParamSupport.check_job_params(
            inference_model=spec,
            params=params,
        )
        assert reasons == []

    def test_every_img_gen_model_in_deck_accepts_some_aspect_ratio(self) -> None:
        """Sanity check: every img_gen model in the deck should accept at least one aspect ratio.

        Catches accidental rule mistakes that would mark every aspect ratio unsupported.
        """
        deck = get_model_deck()
        img_gen_models = [
            (handle, spec) for handle, spec in deck.inference_models.items() if spec.model_type == ModelType.IMG_GEN and spec.rules is not None
        ]
        assert img_gen_models, "Expected at least one img-gen model with rules in the deck"
        for handle, spec in img_gen_models:
            assert spec.rules is not None
            supports_at_least_one = False
            for aspect_ratio in AspectRatio:
                check = ImgGenParamSupport.check_aspect_ratio(
                    rules=spec.rules,
                    aspect_ratio=aspect_ratio,
                    size=None,
                    model_name=spec.name,
                )
                if check.is_supported:
                    supports_at_least_one = True
                    break
            assert supports_at_least_one, f"Model '{handle}' rejects every aspect ratio — likely a rules misconfiguration"
