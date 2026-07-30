"""Tests for ImgGenArgsFactory inference-steps and safety-checker argument mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_model_rules import (
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    SafetyCheckerTaxonomy,
)
from tests.unit.pipelex.cogt.img_gen.conftest import make_img_gen_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestImgGenArgsInferenceSafety:
    @pytest.mark.parametrize("nb_steps", [1, 2, 4, 8])
    def test_sdxl_lightning_accepts_valid_steps_without_config_lookup(self, mocker: MockerFixture, nb_steps: int) -> None:
        """SDXL Lightning passes valid step counts through without consulting the config."""
        mock_config = mocker.MagicMock()
        mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.get_config", return_value=mock_config)

        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=InferenceTaxonomy.SDXL_LIGHTNING,
            num_inference_steps=nb_steps,
            quality=None,
            guidance_scale=None,
            is_raw=None,
        )

        assert result == {"num_inference_steps": nb_steps}
        mock_config.cogt.img_gen_config.get_num_inference_steps.assert_not_called()

    @pytest.mark.parametrize("nb_steps", [3, 5, 16])
    def test_sdxl_lightning_coerces_invalid_steps_to_four(self, mocker: MockerFixture, nb_steps: int) -> None:
        """SDXL Lightning coerces step counts outside its accepted set to its safe default with a warning."""
        mock_log = mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.log")

        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=InferenceTaxonomy.SDXL_LIGHTNING,
            num_inference_steps=nb_steps,
            quality=None,
            guidance_scale=None,
            is_raw=None,
        )

        assert result == {"num_inference_steps": 4}
        mock_log.warning.assert_called_once()

    @pytest.mark.parametrize(
        ("quality", "expected_quality"),
        [
            (None, Quality.MEDIUM),
            (Quality.HIGH, Quality.HIGH),
        ],
    )
    def test_sdxl_lightning_none_steps_uses_config_lookup(self, mocker: MockerFixture, quality: Quality | None, expected_quality: Quality) -> None:
        """SDXL Lightning derives missing steps from the config, defaulting quality to MEDIUM."""
        mock_config = mocker.MagicMock()
        mock_config.cogt.img_gen_config.get_num_inference_steps.return_value = 8
        mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.get_config", return_value=mock_config)

        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=InferenceTaxonomy.SDXL_LIGHTNING,
            num_inference_steps=None,
            quality=quality,
            guidance_scale=None,
            is_raw=None,
        )

        assert result == {"num_inference_steps": 8}
        mock_config.cogt.img_gen_config.get_num_inference_steps.assert_called_once_with(
            model_name="sdxl_lightning",
            quality=expected_quality,
        )

    @pytest.mark.parametrize(
        ("inference_taxonomy", "guidance_scale", "expected_args"),
        [
            (InferenceTaxonomy.FLUX, 3.5, {"num_inference_steps": 28, "guidance_scale": 3.5}),
            (InferenceTaxonomy.FLUX, None, {"num_inference_steps": 28}),
            (InferenceTaxonomy.FLUX, 0.0, {"num_inference_steps": 28}),
            (InferenceTaxonomy.QWEN_IMAGE, 4.0, {"num_inference_steps": 28, "guidance_scale": 4.0}),
            (InferenceTaxonomy.QWEN_IMAGE, None, {"num_inference_steps": 28}),
        ],
    )
    def test_flux_and_qwen_explicit_steps_win_and_guidance_only_when_truthy(
        self,
        mocker: MockerFixture,
        inference_taxonomy: InferenceTaxonomy,
        guidance_scale: float | None,
        expected_args: dict[str, Any],
    ) -> None:
        """Flux and Qwen forward explicit steps without config lookup; guidance_scale appears only when truthy."""
        mock_config = mocker.MagicMock()
        mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.get_config", return_value=mock_config)

        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=inference_taxonomy,
            num_inference_steps=28,
            quality=None,
            guidance_scale=guidance_scale,
            is_raw=None,
        )

        assert result == expected_args
        mock_config.cogt.img_gen_config.get_num_inference_steps.assert_not_called()

    @pytest.mark.parametrize(
        ("inference_taxonomy", "expected_model_name"),
        [
            (InferenceTaxonomy.FLUX, "flux"),
            (InferenceTaxonomy.QWEN_IMAGE, "qwen_image"),
        ],
    )
    def test_flux_and_qwen_none_steps_use_config_lookup(
        self,
        mocker: MockerFixture,
        inference_taxonomy: InferenceTaxonomy,
        expected_model_name: str,
    ) -> None:
        """Flux and Qwen derive missing steps from the config using their own model_name key."""
        mock_config = mocker.MagicMock()
        mock_config.cogt.img_gen_config.get_num_inference_steps.return_value = 12
        mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.get_config", return_value=mock_config)

        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=inference_taxonomy,
            num_inference_steps=None,
            quality=Quality.LOW,
            guidance_scale=None,
            is_raw=None,
        )

        assert result == {"num_inference_steps": 12}
        mock_config.cogt.img_gen_config.get_num_inference_steps.assert_called_once_with(
            model_name=expected_model_name,
            quality=Quality.LOW,
        )

    @pytest.mark.parametrize(
        ("is_raw", "expected_args"),
        [
            (True, {"raw": True}),
            (False, {}),
            (None, {}),
        ],
    )
    def test_flux_11_ultra_emits_raw_only_when_true(self, is_raw: bool | None, expected_args: dict[str, Any]) -> None:
        """Flux-1.1 Ultra emits the `raw` flag only when is_raw is set to True."""
        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=InferenceTaxonomy.FLUX_11_ULTRA,
            num_inference_steps=None,
            quality=None,
            guidance_scale=None,
            is_raw=is_raw,
        )

        assert result == expected_args

    @pytest.mark.parametrize(
        ("quality", "expected_value"),
        [
            (Quality.LOW, "low"),
            (Quality.HIGH, "high"),
        ],
    )
    def test_gpt_image_forwards_explicit_quality(self, quality: Quality, expected_value: str) -> None:
        """GPT Image taxonomy forwards explicit quality as its string value."""
        result = ImgGenArgsFactory.make_args_from_inference(
            inference_taxonomy=InferenceTaxonomy.GPT_IMAGE,
            num_inference_steps=None,
            quality=quality,
            guidance_scale=None,
            is_raw=None,
        )

        assert result == {"quality": expected_value}

    @pytest.mark.parametrize(
        ("is_moderated", "safety_tolerance", "expected_args"),
        [
            (True, None, {"enable_safety_checker": True}),
            (False, None, {"enable_safety_checker": False}),
            (None, 3, {"safety_tolerance": 3}),
            (True, 5, {"enable_safety_checker": True, "safety_tolerance": 5}),
            (None, None, {}),
        ],
    )
    def test_safety_available_emits_each_parameter_independently(
        self,
        is_moderated: bool | None,
        safety_tolerance: int | None,
        expected_args: dict[str, Any],
    ) -> None:
        """AVAILABLE safety taxonomy emits enable_safety_checker and safety_tolerance independently when set."""
        result = ImgGenArgsFactory.make_args_from_safety_checker(
            safety_checker_taxonomy=SafetyCheckerTaxonomy.AVAILABLE,
            is_moderated=is_moderated,
            safety_tolerance=safety_tolerance,
        )

        assert result == expected_args

    def test_safety_unavailable_emits_nothing_even_with_values(self) -> None:
        """UNAVAILABLE safety taxonomy skips all safety parameters even when values are provided."""
        result = ImgGenArgsFactory.make_args_from_safety_checker(
            safety_checker_taxonomy=SafetyCheckerTaxonomy.UNAVAILABLE,
            is_moderated=True,
            safety_tolerance=4,
        )

        assert result == {}

    @pytest.mark.parametrize(
        ("is_moderated", "expected_args"),
        [
            (None, {}),
            (True, {"moderation": "auto"}),
            (False, {"moderation": "low"}),
        ],
    )
    def test_safety_openai_moderation_mapping(self, is_moderated: bool | None, expected_args: dict[str, Any]) -> None:
        """OPENAI_MODERATION maps moderation enabled to standard filtering ("auto") and disabled to less restrictive ("low"),
        and emits no key at all when unset so the provider applies its own default.
        """
        result = ImgGenArgsFactory.make_args_from_safety_checker(
            safety_checker_taxonomy=SafetyCheckerTaxonomy.OPENAI_MODERATION,
            is_moderated=is_moderated,
            safety_tolerance=None,
        )

        assert result == expected_args

    @pytest.mark.asyncio
    async def test_full_flux_11_ultra_job_emits_raw_flag(self) -> None:
        """A full job with Flux-1.1 Ultra inference rules dispatches is_raw through to the args dict."""
        model_rules: ImgGenModelRules = {
            ImgGenArgTopic.INFERENCE: InferenceTaxonomy.FLUX_11_ULTRA,
        }
        img_gen_job = make_img_gen_job(is_raw=True)

        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=model_rules,
            img_gen_job=img_gen_job,
            nb_images=1,
            model_id="fal-ai/flux-pro/v1.1-ultra",
            model_name="flux-1.1-ultra",
        )

        assert result == {"raw": True}
