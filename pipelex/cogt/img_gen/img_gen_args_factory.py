from typing import Any, cast

from pydantic import ValidationError

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, ImgGenJobConfig, ImgGenJobParams, ImgGenJobReport, OutputFormat, Quality
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata
from pipelex.types import StrEnum


class ImgGenArgTopic(StrEnum):
    ASPECT_RATIO = "aspect_ratio"
    INFERENCE = "inference"
    SAFETY_CHECKER = "safety_checker"


class AspectRatioTaxonomy(StrEnum):
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"


class InferenceTaxonomy(StrEnum):
    SDXL_LIGHTNING = "sdxl_lightning"
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"


class SafetyCheckerTaxonomy(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


ImgGenModelRules = dict[ImgGenArgTopic, str]


class ImgGenArgsFactory:
    @classmethod
    def make_args_for_model(
        cls,
        model_name: str,
        jop_params: ImgGenJobParams,
    ) -> dict[str, Any]:
        args_dict: dict[str, Any]
        num_inference_steps: int | None

        match model_name:
            case "fast-lightning-sdxl":
                num_inference_steps = jop_params.nb_steps
                if not num_inference_steps and (quality := jop_params.quality):
                    num_inference_steps = cls.make_nb_steps_from_quality_for_sdxl_lightning(quality=quality)
                acceptable_steps = [1, 2, 4, 8]
                if num_inference_steps not in acceptable_steps:
                    log.warning("Number of inference steps %s' for SDXL Lightning must be one of %s", num_inference_steps, acceptable_steps)
                    num_inference_steps = 8
                args_dict = {
                    **cls.make_args_from_aspect_ratio(aspect_ratio_taxonomy=AspectRatioTaxonomy.FLUX, aspect_ratio=jop_params.aspect_ratio),
                    "num_inference_steps": num_inference_steps,
                }
            case "flux-pro" | "flux-pro/v1.1":
                num_inference_steps = jop_params.nb_steps
                if not num_inference_steps:
                    if not jop_params.quality:
                        msg = f"Either nb_steps or quality must be set for image generation with '{model_name}'"
                        raise ImgGenParameterError(msg)
                    num_inference_steps = cls.make_nb_steps_from_quality_for_flux(quality=jop_params.quality)

                args_dict = {
                    "image_size": cls.make_image_size_for_flux_1(jop_params.aspect_ratio),
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": jop_params.guidance_scale,
                    "enable_safety_checker": jop_params.is_moderated,
                    "safety_tolerance": jop_params.safety_tolerance,
                }
            case "flux-pro/v1.1-ultra":
                args_dict = {
                    "aspect_ratio": cls.make_aspect_ratio_for_flux_1_1_ultra(jop_params.aspect_ratio),
                    "enable_safety_checker": jop_params.is_moderated,
                    "safety_tolerance": jop_params.safety_tolerance,
                    "raw": jop_params.is_raw,
                }
            case "flux-2":
                num_inference_steps = jop_params.nb_steps
                if not num_inference_steps:
                    if not jop_params.quality:
                        msg = f"Either nb_steps or quality must be set for image generation with '{model_name}'"
                        raise ImgGenParameterError(msg)
                    num_inference_steps = cls.make_nb_steps_from_quality_for_flux(quality=jop_params.quality)

                args_dict = {
                    "image_size": cls.make_image_size_for_flux_1(jop_params.aspect_ratio),
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": jop_params.guidance_scale,
                    "enable_safety_checker": jop_params.is_moderated,
                    "safety_tolerance": jop_params.safety_tolerance,
                }
            case _:
                msg = f"Invalid fal model id: '{model_name}'"
                raise ImgGenParameterError(msg)

        return args_dict

    @classmethod
    def make_nb_steps_from_quality_for_sdxl_lightning(cls, quality: Quality) -> int:
        sdxl_lightning_map_quality_to_steps = get_config().cogt.img_gen_config.fal_config.sdxl_lightning_map_quality_to_steps
        return sdxl_lightning_map_quality_to_steps[quality]

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
