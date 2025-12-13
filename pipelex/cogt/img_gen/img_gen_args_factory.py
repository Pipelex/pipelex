from typing import Any

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, ImgGenJobParams, Quality
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    SafetyCheckerTaxonomy,
)
from pipelex.config import get_config


class ImgGenArgsFactory:
    @classmethod
    def make_args_for_model(
        cls,
        model_rules: ImgGenModelRules,
        job_params: ImgGenJobParams,
    ) -> dict[str, Any]:
        args_dict: dict[str, Any] = {}

        for topic, taxonomy_value in model_rules.items():
            match topic:
                case ImgGenArgTopic.ASPECT_RATIO:
                    aspect_ratio_taxonomy = AspectRatioTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_aspect_ratio(
                            aspect_ratio_taxonomy=aspect_ratio_taxonomy,
                            aspect_ratio=job_params.aspect_ratio,
                        )
                    )
                case ImgGenArgTopic.INFERENCE:
                    inference_taxonomy = InferenceTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_inference(
                            inference_taxonomy=inference_taxonomy,
                            num_inference_steps=job_params.nb_steps,
                            quality=job_params.quality,
                            guidance_scale=job_params.guidance_scale,
                            is_raw=job_params.is_raw,
                        )
                    )
                case ImgGenArgTopic.SAFETY_CHECKER:
                    safety_checker_taxonomy = SafetyCheckerTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_safety_checker(
                            safety_checker_taxonomy=safety_checker_taxonomy,
                            is_moderated=job_params.is_moderated,
                            safety_tolerance=job_params.safety_tolerance,
                        )
                    )

        return args_dict

    @classmethod
    def make_args_from_aspect_ratio(cls, aspect_ratio_taxonomy: AspectRatioTaxonomy, aspect_ratio: AspectRatio) -> dict[str, Any]:
        key: str
        value: Any
        match aspect_ratio_taxonomy:
            case AspectRatioTaxonomy.FLUX:
                key = "image_size"
                match aspect_ratio:
                    case AspectRatio.SQUARE:
                        value = "square_hd"
                    case AspectRatio.LANDSCAPE_4_3:
                        value = "landscape_4_3"
                    case AspectRatio.LANDSCAPE_16_9:
                        value = "landscape_16_9"
                    case AspectRatio.LANDSCAPE_21_9:
                        value = "landscape_21_9"
                    case AspectRatio.PORTRAIT_3_4:
                        value = "portrait_4_3"
                    case AspectRatio.PORTRAIT_9_16:
                        value = "portrait_16_9"
                    case AspectRatio.PORTRAIT_9_21:
                        value = "portrait_21_9"
                    case AspectRatio.LANDSCAPE_3_2 | AspectRatio.PORTRAIT_2_3:
                        msg = f"Aspect ratio '{aspect_ratio}' is not supported by Flux-1 image generation model"
                        raise ImgGenParameterError(msg)
            case AspectRatioTaxonomy.FLUX_11_ULTRA:
                key = "aspect_ratio"
                match aspect_ratio:
                    case AspectRatio.SQUARE:
                        value = "1:1"
                    case AspectRatio.LANDSCAPE_4_3:
                        value = "4:3"
                    case AspectRatio.LANDSCAPE_16_9:
                        value = "16:9"
                    case AspectRatio.LANDSCAPE_21_9:
                        value = "21:9"
                    case AspectRatio.PORTRAIT_3_4:
                        value = "3:4"
                    case AspectRatio.PORTRAIT_9_16:
                        value = "9:16"
                    case AspectRatio.PORTRAIT_9_21:
                        value = "9:21"
                    case AspectRatio.LANDSCAPE_3_2 | AspectRatio.PORTRAIT_2_3:
                        msg = f"Aspect ratio '{aspect_ratio}' is not supported by Flux-1.1 Ultra image generation model"
                        raise ImgGenParameterError(msg)
        return {key: value}

    @classmethod
    def make_args_from_inference(
        cls,
        inference_taxonomy: InferenceTaxonomy,
        num_inference_steps: int | None,
        quality: Quality | None,
        guidance_scale: float | None,
        is_raw: bool,
    ) -> dict[str, Any]:
        args_dict: dict[str, Any] = {}
        match inference_taxonomy:
            case InferenceTaxonomy.SDXL_LIGHTNING:
                if num_inference_steps:
                    acceptable_steps = [1, 2, 4, 8]
                    if num_inference_steps not in acceptable_steps:
                        # TODO: prevent this when building presets and params
                        log.warning(f"Number of inference steps {num_inference_steps} for SDXL Lightning must be one of {acceptable_steps}")
                        num_inference_steps = 4
                    args_dict["num_inference_steps"] = num_inference_steps
                else:
                    sdxl_lightning_map_quality_to_steps = get_config().cogt.img_gen_config.fal_config.sdxl_lightning_map_quality_to_steps
                    num_inference_steps = sdxl_lightning_map_quality_to_steps[quality or Quality.MEDIUM]
                    args_dict["num_inference_steps"] = num_inference_steps
            case InferenceTaxonomy.FLUX:
                if num_inference_steps:
                    args_dict["num_inference_steps"] = num_inference_steps
                else:
                    flux_map_quality_to_steps = get_config().cogt.img_gen_config.fal_config.flux_map_quality_to_steps
                    num_inference_steps = flux_map_quality_to_steps[quality or Quality.MEDIUM]
                    args_dict["num_inference_steps"] = num_inference_steps
                if guidance_scale:
                    args_dict["guidance_scale"] = guidance_scale
            case InferenceTaxonomy.FLUX_11_ULTRA:
                if is_raw:
                    args_dict["raw"] = is_raw
        return args_dict

    @classmethod
    def make_args_from_safety_checker(
        cls, safety_checker_taxonomy: SafetyCheckerTaxonomy, is_moderated: bool, safety_tolerance: int | None
    ) -> dict[str, Any]:
        args_dict: dict[str, Any] = {}
        match safety_checker_taxonomy:
            case SafetyCheckerTaxonomy.UNAVAILABLE:
                pass
            case SafetyCheckerTaxonomy.AVAILABLE:
                if is_moderated:
                    args_dict["enable_safety_checker"] = is_moderated
                if safety_tolerance:
                    args_dict["safety_tolerance"] = safety_tolerance
        return args_dict
