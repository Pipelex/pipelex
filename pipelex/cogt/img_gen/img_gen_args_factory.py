"""Factory for building image generation API arguments from model rules.

This module translates high-level image generation parameters into provider-specific
API arguments using the taxonomy system defined in `img_gen_model_rules`.

The factory uses the model's rules (a mapping of topics to taxonomies) to determine
how each parameter should be formatted for the specific provider's API.
"""

from typing import Any

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, Quality
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    BackgroundTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    ModelNameTaxonomy,
    NumImagesTaxonomy,
    OutputFormatTaxonomy,
    PromptTaxonomy,
    SafetyCheckerTaxonomy,
    SpecificTaxonomy,
)
from pipelex.config import get_config
from pipelex.plugins.openai.openai_img_gen_factory import OpenAIImgGenFactory
from pipelex.tools.misc.image_utils import ImageFormat


class ImgGenArgsFactory:
    """Factory that builds provider-specific API arguments from model rules and job parameters.

    This factory iterates over the model's rules (topic -> taxonomy mappings) and uses
    the appropriate taxonomy handler to generate the correct API arguments for each topic.
    """

    @classmethod
    def make_args_for_model(
        cls,
        model_rules: ImgGenModelRules,
        img_gen_job: ImgGenJob,
        nb_images: int,
        model_id: str,
    ) -> dict[str, Any]:
        """Build provider-specific API arguments from model rules and job parameters.

        Iterates over each topic in the model's rules and applies the corresponding
        taxonomy handler to generate the correct API arguments.

        Args:
            model_rules: Mapping of argument topics to their taxonomy values for the target model
            img_gen_job: The image generation job containing prompt and parameters
            nb_images: Number of images to generate
            model_id: The model identifier to pass to the provider API

        Returns:
            Dictionary of API arguments ready to be passed to the provider's API
        """
        job_params = img_gen_job.job_params

        args_dict: dict[str, Any] = {}

        for topic, taxonomy_value in model_rules.items():
            match topic:
                case ImgGenArgTopic.PROMPT:
                    prompt_taxonomy = PromptTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_prompt(
                            prompt_taxonomy=prompt_taxonomy,
                            positive_text=img_gen_job.img_gen_prompt.positive_text,
                            negative_text=img_gen_job.img_gen_prompt.negative_text,
                        )
                    )
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
                    # TODO: test without imposing the format
                    args_dict.update(
                        cls.make_args_from_output_format(
                            output_format_taxonomy=output_format_taxonomy,
                            output_format=job_params.output_format or ImageFormat.PNG,
                        )
                    )
                case ImgGenArgTopic.SPECIFIC:
                    specific_taxonomy = SpecificTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_specific(
                            specific_taxonomy=specific_taxonomy,
                        )
                    )
                case ImgGenArgTopic.MODEL_NAME:
                    model_name_taxonomy = ModelNameTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_model_name(
                            model_name_taxonomy=model_name_taxonomy,
                            model_id=model_id,
                        )
                    )

        return args_dict

    @classmethod
    def make_args_from_num_images(cls, num_images_taxonomy: NumImagesTaxonomy, nb_images: int) -> dict[str, Any]:
        """Map number of images to provider-specific parameter name."""
        match num_images_taxonomy:
            case NumImagesTaxonomy.FAL:
                return {"num_images": nb_images}
            case NumImagesTaxonomy.GPT:
                return {"n": nb_images}

    @classmethod
    def make_args_from_prompt(
        cls,
        prompt_taxonomy: PromptTaxonomy,
        positive_text: str,
        negative_text: str | None,
    ) -> dict[str, Any]:
        """Map prompt parameters to provider-specific format."""
        match prompt_taxonomy:
            case PromptTaxonomy.POSITIVE_ONLY:
                return {"prompt": positive_text}
            case PromptTaxonomy.WITH_NEGATIVE:
                args_dict: dict[str, Any] = {"prompt": positive_text}
                if negative_text:
                    args_dict["negative_prompt"] = negative_text
                return args_dict

    @classmethod
    def make_args_from_specific(cls, specific_taxonomy: SpecificTaxonomy) -> dict[str, Any]:
        """Generate provider-specific parameters not covered by other taxonomies."""
        match specific_taxonomy:
            case SpecificTaxonomy.FAL:
                return {"sync_mode": False}

    @classmethod
    def make_args_from_model_name(
        cls,
        model_name_taxonomy: ModelNameTaxonomy,
        model_id: str,
    ) -> dict[str, Any]:
        """Map model identifier to provider-specific parameter."""
        match model_name_taxonomy:
            case ModelNameTaxonomy.STANDARD:
                return {"model": model_id}

    @classmethod
    def make_args_from_background(cls, background_taxonomy: BackgroundTaxonomy, background: Background) -> dict[str, Any]:
        """Map background setting to provider-specific parameter."""
        match background_taxonomy:
            case BackgroundTaxonomy.GPT:
                return {"background": background.value}

    @classmethod
    def make_args_from_aspect_ratio(cls, aspect_ratio_taxonomy: AspectRatioTaxonomy, aspect_ratio: AspectRatio) -> dict[str, Any]:
        """Map aspect ratio to provider-specific parameter name and value format.

        Raises:
            ImgGenParameterError: If the aspect ratio is not supported by the target model
        """
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
                        msg = f"Aspect ratio '{aspect_ratio}' is not supported by Flux image generation model"
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
            case AspectRatioTaxonomy.QWEN_IMAGE:
                width: int
                height: int
                aspect_ratio_string: str
                match aspect_ratio:
                    case AspectRatio.SQUARE:
                        width, height = 1328, 1328
                        aspect_ratio_string = "1:1"
                    case AspectRatio.LANDSCAPE_16_9:
                        width, height = 1664, 928
                        aspect_ratio_string = "16:9"
                    case AspectRatio.PORTRAIT_9_16:
                        width, height = 928, 1664
                        aspect_ratio_string = "9:16"
                    case AspectRatio.LANDSCAPE_4_3:
                        width, height = 1472, 1140
                        aspect_ratio_string = "4:3"
                    case AspectRatio.PORTRAIT_3_4:
                        width, height = 1140, 1472
                        aspect_ratio_string = "3:4"
                    case AspectRatio.LANDSCAPE_3_2:
                        width, height = 1584, 1056
                        aspect_ratio_string = "3:2"
                    case AspectRatio.PORTRAIT_2_3:
                        width, height = 1056, 1584
                        aspect_ratio_string = "2:3"
                    case AspectRatio.LANDSCAPE_21_9 | AspectRatio.PORTRAIT_9_21:
                        msg = f"Aspect ratio '{aspect_ratio}' is not supported by HuggingFace image generation model"
                        raise ImgGenParameterError(msg)
                return {"width": width, "height": height, "aspect_ratio": aspect_ratio_string}
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
        """Map inference parameters (steps, quality, guidance) to provider-specific format.

        If num_inference_steps is not provided, it will be derived from the quality setting
        using the configured quality-to-steps mapping for the specific model.
        """
        args_dict: dict[str, Any] = {}
        match inference_taxonomy:
            case InferenceTaxonomy.SDXL_LIGHTNING:
                if num_inference_steps:
                    acceptable_steps = [1, 2, 4, 8]
                    if num_inference_steps not in acceptable_steps:
                        # TODO: prevent this when building presets and params
                        log.warning(f"Number of inference steps {num_inference_steps} for SDXL Lightning must be one of {acceptable_steps}")
                        num_inference_steps = 4
                else:
                    num_inference_steps = get_config().cogt.img_gen_config.get_num_inference_steps(
                        model_name="sdxl_lightning", quality=quality or Quality.MEDIUM
                    )
                args_dict["num_inference_steps"] = num_inference_steps
            case InferenceTaxonomy.FLUX:
                if num_inference_steps is None:
                    num_inference_steps = get_config().cogt.img_gen_config.get_num_inference_steps(
                        model_name="flux", quality=quality or Quality.MEDIUM
                    )
                args_dict["num_inference_steps"] = num_inference_steps
                if guidance_scale:
                    args_dict["guidance_scale"] = guidance_scale
            case InferenceTaxonomy.QWEN_IMAGE:
                if num_inference_steps is None:
                    num_inference_steps = get_config().cogt.img_gen_config.get_num_inference_steps(
                        model_name="qwen_image", quality=quality or Quality.MEDIUM
                    )
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
        """Map safety checker settings to provider-specific parameters.

        Only generates arguments if the model supports safety checker configuration
        (taxonomy is AVAILABLE) and the corresponding parameters are provided.
        """
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
        output_format: ImageFormat,
    ) -> dict[str, Any]:
        """Map output format to provider-specific parameter name and validate support.

        Raises:
            ImgGenParameterError: If the output format is not supported by the target model
        """
        key: str
        value: str
        match output_format_taxonomy:
            case OutputFormatTaxonomy.SDXL:
                key = "format"
                match output_format:
                    case ImageFormat.PNG:
                        value = "png"
                    case ImageFormat.JPEG:
                        value = "jpeg"
                    case ImageFormat.WEBP:
                        msg = "Output format WebP is not supported by SDXL image generation models"
                        raise ImgGenParameterError(msg)
            case OutputFormatTaxonomy.FLUX_1:
                key = "output_format"
                match output_format:
                    case ImageFormat.PNG:
                        value = "png"
                    case ImageFormat.JPEG:
                        value = "jpeg"
                    case ImageFormat.WEBP:
                        msg = "Output format WebP is not supported by Flux 1 image generation models"
                        raise ImgGenParameterError(msg)
            case OutputFormatTaxonomy.FLUX_2:
                key = "output_format"
                value = output_format.value
            case OutputFormatTaxonomy.GPT:
                key = "output_format"
                value = output_format.value
        return {key: value}
