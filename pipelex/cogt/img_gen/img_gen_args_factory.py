from typing import Any

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat, Quality
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    BackgroundTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    NumImagesTaxonomy,
    OutputFormatTaxonomy,
    SafetyCheckerTaxonomy,
    SpecificTaxonomy,
)
from pipelex.config import get_config
from pipelex.plugins.openai.openai_img_gen_factory import OpenAIImgGenFactory


class ImgGenArgsFactory:
    @classmethod
    def make_args_for_model(
        cls,
        model_rules: ImgGenModelRules,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> dict[str, Any]:
        job_params = img_gen_job.job_params

        # Common args that don't need rules
        args_dict: dict[str, Any] = {
            "prompt": img_gen_job.img_gen_prompt.positive_text,
        }

        for topic, taxonomy_value in model_rules.items():
            match topic:
                case ImgGenArgTopic.NUM_IMAGES:
                    num_images_taxonomy = NumImagesTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_num_images(
                            num_images_taxonomy=num_images_taxonomy,
                            nb_images=nb_images,
                        )
                    )
                case ImgGenArgTopic.ASPECT_RATIO:
                    aspect_ratio_taxonomy = AspectRatioTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_aspect_ratio(
                            aspect_ratio_taxonomy=aspect_ratio_taxonomy,
                            aspect_ratio=job_params.aspect_ratio,
                        )
                    )
                case ImgGenArgTopic.BACKGROUND:
                    background_taxonomy = BackgroundTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_background(
                            background_taxonomy=background_taxonomy,
                            background=job_params.background,
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
                case ImgGenArgTopic.OUTPUT_FORMAT:
                    output_format_taxonomy = OutputFormatTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_output_format(
                            output_format_taxonomy=output_format_taxonomy,
                            output_format=job_params.output_format,
                        )
                    )
                case ImgGenArgTopic.SPECIFIC:
                    specific_taxonomy = SpecificTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_specific(
                            specific_taxonomy=specific_taxonomy,
                        )
                    )

        return args_dict

    @classmethod
    def make_args_from_num_images(cls, num_images_taxonomy: NumImagesTaxonomy, nb_images: int) -> dict[str, Any]:
        match num_images_taxonomy:
            case NumImagesTaxonomy.FAL:
                return {"num_images": nb_images}
            case NumImagesTaxonomy.GPT:
                return {"n": nb_images}

    @classmethod
    def make_args_from_specific(cls, specific_taxonomy: SpecificTaxonomy) -> dict[str, Any]:
        match specific_taxonomy:
            case SpecificTaxonomy.FAL:
                return {"sync_mode": False}

    @classmethod
    def make_args_from_background(cls, background_taxonomy: BackgroundTaxonomy, background: Background) -> dict[str, Any]:
        match background_taxonomy:
            case BackgroundTaxonomy.GPT:
                return {"background": background.value}

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
            case AspectRatioTaxonomy.GPT:
                key = "size"
                value = OpenAIImgGenFactory.image_size_for_gpt_image_1(aspect_ratio)[0]
        return {key: value}

    @classmethod
    def make_args_from_inference(
        cls,
        inference_taxonomy: InferenceTaxonomy,
        num_inference_steps: int | None,
        quality: Quality | None,
        guidance_scale: float | None,
        is_raw: bool | None,
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
            case InferenceTaxonomy.GPT:
                if quality:
                    args_dict["quality"] = quality.value
        return args_dict

    @classmethod
    def make_args_from_safety_checker(
        cls,
        safety_checker_taxonomy: SafetyCheckerTaxonomy,
        is_moderated: bool | None,
        safety_tolerance: int | None,
    ) -> dict[str, Any]:
        args_dict: dict[str, Any] = {}
        match safety_checker_taxonomy:
            case SafetyCheckerTaxonomy.UNAVAILABLE:
                pass
            case SafetyCheckerTaxonomy.AVAILABLE:
                if is_moderated is not None:
                    args_dict["enable_safety_checker"] = is_moderated
                if safety_tolerance is not None:
                    args_dict["safety_tolerance"] = safety_tolerance
        return args_dict

    @classmethod
    def make_args_from_output_format(
        cls,
        output_format_taxonomy: OutputFormatTaxonomy,
        output_format: OutputFormat,
    ) -> dict[str, Any]:
        key: str
        value: str
        match output_format_taxonomy:
            case OutputFormatTaxonomy.SDXL:
                key = "format"
                match output_format:
                    case OutputFormat.PNG:
                        value = "png"
                    case OutputFormat.JPEG:
                        value = "jpeg"
                    case OutputFormat.WEBP:
                        msg = "Output format WebP is not supported by SDXL image generation models"
                        raise ImgGenParameterError(msg)
            case OutputFormatTaxonomy.FLUX_1:
                key = "output_format"
                match output_format:
                    case OutputFormat.PNG:
                        value = "png"
                    case OutputFormat.JPEG:
                        value = "jpeg"
                    case OutputFormat.WEBP:
                        msg = "Output format WebP is not supported by Flux 1 image generation models"
                        raise ImgGenParameterError(msg)
            case OutputFormatTaxonomy.FLUX_2:
                key = "output_format"
                value = output_format
            case OutputFormatTaxonomy.GPT:
                key = "output_format"
                value = output_format
        return {key: value}
