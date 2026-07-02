"""Factory for building image generation API arguments from model rules.

This module translates high-level image generation parameters into provider-specific
API arguments using the taxonomy system defined in `img_gen_model_rules`.

The factory uses the model's rules (a mapping of topics to taxonomies) to determine
how each parameter should be formatted for the specific provider's API.
"""

import base64
from typing import Any, TypeAlias

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, InputFidelity, Quality, SizeTier
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
    OutputCompressionTaxonomy,
    OutputFormatTaxonomy,
    PromptTaxonomy,
    SafetyCheckerTaxonomy,
    SpecificTaxonomy,
)
from pipelex.config import get_config
from pipelex.plugins.openai.openai_img_gen_factory import OpenAIImgGenFactory
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl

ImageFileTuple: TypeAlias = tuple[str, bytes, str]
"""httpx-style multipart file part: (filename, content_bytes, mime_type)."""


class ImgGenArgsFactory:
    """Factory that builds provider-specific API arguments from model rules and job parameters.

    This factory iterates over the model's rules (topic -> taxonomy mappings) and uses
    the appropriate taxonomy handler to generate the correct API arguments for each topic.
    """

    @classmethod
    async def make_args_for_model(
        cls,
        model_rules: ImgGenModelRules,
        *,
        img_gen_job: ImgGenJob,
        nb_images: int,
        model_id: str,
        model_name: str,
    ) -> dict[str, Any]:
        """Build provider-specific API arguments from model rules and job parameters.

        Iterates over each topic in the model's rules and applies the corresponding
        taxonomy handler to generate the correct API arguments.

        Args:
            model_rules: Mapping of argument topics to their taxonomy values for the target model
            img_gen_job: The image generation job containing prompt and parameters
            nb_images: Number of images to generate
            model_id: The model identifier
            model_name: The config model name

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
                            size=job_params.size,
                            model_name=model_name,
                        )
                    )
                case ImgGenArgTopic.BACKGROUND:
                    background_taxonomy = BackgroundTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_background(
                            background_taxonomy=background_taxonomy,
                            background=job_params.background,
                            model_name=model_name,
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
                case ImgGenArgTopic.OUTPUT_COMPRESSION:
                    output_compression_taxonomy = OutputCompressionTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_output_compression(
                            output_compression_taxonomy=output_compression_taxonomy,
                        )
                    )
                case ImgGenArgTopic.SPECIFIC:
                    specific_taxonomy = SpecificTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_specific(
                            specific_taxonomy=specific_taxonomy,
                        )
                    )
                case ImgGenArgTopic.MODEL_CHOICE:
                    model_name_taxonomy = ModelChoiceTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_model_name(
                            model_name_taxonomy=model_name_taxonomy,
                            model_id=model_id,
                            model_name=model_name,
                        )
                    )
                case ImgGenArgTopic.INPUT_IMAGES:
                    input_images_taxonomy = InputImagesTaxonomy(taxonomy_value)
                    input_images_args = await cls.make_args_from_input_images(
                        input_images_taxonomy=input_images_taxonomy,
                        input_images=img_gen_job.img_gen_prompt.input_images,
                    )
                    args_dict.update(input_images_args)
                case ImgGenArgTopic.INPUT_FIDELITY:
                    input_fidelity_taxonomy = InputFidelityTaxonomy(taxonomy_value)
                    args_dict.update(
                        cls.make_args_from_input_fidelity(
                            input_fidelity_taxonomy=input_fidelity_taxonomy,
                            input_fidelity=job_params.input_fidelity,
                            model_name=model_name,
                        )
                    )

        # Validate that input_images were processed if provided
        if img_gen_job.img_gen_prompt.input_images:
            if ImgGenArgTopic.INPUT_IMAGES not in model_rules:
                msg = (
                    "Input images were provided but the model does not have 'input_images' rules configured. "
                    "This model may not support image-to-image generation, or the configuration is incomplete."
                )
                raise ImgGenParameterError(msg)

        if job_params.input_fidelity is not None and ImgGenArgTopic.INPUT_FIDELITY not in model_rules:
            msg = f"Model '{model_name}' does not support input_fidelity"
            raise ImgGenParameterError(msg)

        return args_dict

    @classmethod
    def make_args_from_num_images(cls, num_images_taxonomy: NumImagesTaxonomy, *, nb_images: int) -> dict[str, Any]:
        """Map number of images to provider-specific parameter name."""
        match num_images_taxonomy:
            case NumImagesTaxonomy.FAL:
                return {"num_images": nb_images}
            case NumImagesTaxonomy.GPT_IMAGE:
                return {"n": nb_images}

    @classmethod
    def make_args_from_prompt(
        cls,
        prompt_taxonomy: PromptTaxonomy,
        *,
        positive_text: str,
        negative_text: str | None,
    ) -> dict[str, Any]:
        """Map prompt parameters to provider-specific format."""
        match prompt_taxonomy:
            case PromptTaxonomy.POSITIVE_ONLY:
                if negative_text:
                    log.warning(
                        f"A negative prompt was provided but the model's prompt taxonomy is '{PromptTaxonomy.POSITIVE_ONLY}', "
                        "which does not support negative prompts. The negative prompt will be silently ignored."
                    )
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
        model_name_taxonomy: ModelChoiceTaxonomy,
        *,
        model_id: str,
        model_name: str,
    ) -> dict[str, Any]:
        """Map model identifier to provider-specific parameter."""
        match model_name_taxonomy:
            case ModelChoiceTaxonomy.MODEL_ID:
                return {"model": model_id}
            case ModelChoiceTaxonomy.MODEL_NAME:
                return {"model": model_name}

    @classmethod
    def make_args_from_background(cls, background_taxonomy: BackgroundTaxonomy, *, background: Background, model_name: str) -> dict[str, Any]:
        """Map background setting to provider-specific parameter.

        Raises:
            ImgGenParameterError: If the model does not support background configuration
                (taxonomy is UNAVAILABLE) and a transparent background was requested.
        """
        match background_taxonomy:
            case BackgroundTaxonomy.AVAILABLE:
                return {"background": background.value}
            case BackgroundTaxonomy.UNAVAILABLE:
                if background.is_certainly_transparent:
                    msg = f"Model '{model_name}' does not support transparent background"
                    raise ImgGenParameterError(msg)
                return {}

    @classmethod
    def make_args_from_aspect_ratio(
        cls,
        aspect_ratio_taxonomy: AspectRatioTaxonomy,
        *,
        aspect_ratio: AspectRatio,
        size: SizeTier | ImageSize | None,
        model_name: str,
    ) -> dict[str, Any]:
        """Map aspect ratio to provider-specific parameter name and value format.

        Raises:
            ImgGenParameterError: If the aspect ratio or size is not supported by the target model
        """
        if isinstance(size, SizeTier):
            msg = f"Size tier '{size}' is not yet supported for image generation model '{model_name}'"
            raise ImgGenParameterError(msg)
        match aspect_ratio_taxonomy:
            case AspectRatioTaxonomy.FLUX | AspectRatioTaxonomy.FLUX_11_ULTRA | AspectRatioTaxonomy.QWEN_IMAGE:
                if size is not None:
                    msg = f"Model '{model_name}' does not support exact image sizes; use aspect_ratio to control the geometry"
                    raise ImgGenParameterError(msg)
            case AspectRatioTaxonomy.GPT_IMAGE_LEGACY | AspectRatioTaxonomy.GPT_IMAGE_2:
                pass
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
                    case (
                        AspectRatio.LANDSCAPE_3_2
                        | AspectRatio.PORTRAIT_2_3
                        | AspectRatio.LANDSCAPE_4_1
                        | AspectRatio.LANDSCAPE_8_1
                        | AspectRatio.PORTRAIT_1_4
                        | AspectRatio.PORTRAIT_1_8
                    ):
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
                    case (
                        AspectRatio.LANDSCAPE_3_2
                        | AspectRatio.PORTRAIT_2_3
                        | AspectRatio.LANDSCAPE_4_1
                        | AspectRatio.LANDSCAPE_8_1
                        | AspectRatio.PORTRAIT_1_4
                        | AspectRatio.PORTRAIT_1_8
                    ):
                        msg = f"Aspect ratio '{aspect_ratio}' is not supported by Flux-1.1 Ultra image generation model"
                        raise ImgGenParameterError(msg)
            case AspectRatioTaxonomy.GPT_IMAGE_LEGACY:
                key = "size"
                value = OpenAIImgGenFactory.size_for_legacy_openai_image(
                    model_name=model_name,
                    aspect_ratio=aspect_ratio,
                    size=size,
                )[0]
            case AspectRatioTaxonomy.GPT_IMAGE_2:
                key = "size"
                value = OpenAIImgGenFactory.size_for_gpt_image_2(
                    model_name=model_name,
                    aspect_ratio=aspect_ratio,
                    size=size,
                )[0]
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
                    case (
                        AspectRatio.LANDSCAPE_21_9
                        | AspectRatio.PORTRAIT_9_21
                        | AspectRatio.LANDSCAPE_4_1
                        | AspectRatio.LANDSCAPE_8_1
                        | AspectRatio.PORTRAIT_1_4
                        | AspectRatio.PORTRAIT_1_8
                    ):
                        msg = f"Aspect ratio '{aspect_ratio}' is not supported by HuggingFace image generation model"
                        raise ImgGenParameterError(msg)
                return {"width": width, "height": height, "aspect_ratio": aspect_ratio_string}
        return {key: value}

    @classmethod
    def make_args_from_inference(
        cls,
        inference_taxonomy: InferenceTaxonomy,
        *,
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
            case InferenceTaxonomy.GPT_IMAGE:
                args_dict["quality"] = (quality or Quality.MEDIUM).value
        return args_dict

    @classmethod
    def make_args_from_safety_checker(
        cls,
        safety_checker_taxonomy: SafetyCheckerTaxonomy,
        *,
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
            case SafetyCheckerTaxonomy.OPENAI_MODERATION:
                moderation = OpenAIImgGenFactory.moderation_for_openai_image(is_moderated=is_moderated)
                if not isinstance(moderation, str):
                    return args_dict
                args_dict["moderation"] = moderation
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
        *,
        output_format: ImageFormat | None,
    ) -> dict[str, Any]:
        """Map output format to provider-specific parameter name and validate support.

        When output_format is None, returns an empty dict so the provider applies its own default.

        Raises:
            ImgGenParameterError: If the output format is not supported by the target model
        """
        key: str
        value: str
        match output_format_taxonomy:
            case OutputFormatTaxonomy.SDXL:
                if output_format is None:
                    return {}
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
                if output_format is None:
                    return {}
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
                if output_format is None:
                    return {}
                key = "output_format"
                value = output_format.value
            case OutputFormatTaxonomy.GPT_IMAGE_LEGACY:
                if output_format is None:
                    return {}
                key = "output_format"
                value = output_format.value
            case OutputFormatTaxonomy.UNAVAILABLE:
                return {}
        return {key: value}

    @classmethod
    def make_args_from_output_compression(
        cls,
        output_compression_taxonomy: OutputCompressionTaxonomy,
    ) -> dict[str, Any]:
        """Map output compression to provider-specific parameter.

        OpenAI gpt-image-1/-1-mini/-1.5 accept `output_compression` (0-100) for JPEG/WEBP outputs.
        PNG ignores this value (lossless). Models that do not expose this parameter use UNAVAILABLE.
        """
        match output_compression_taxonomy:
            case OutputCompressionTaxonomy.GPT_IMAGE_LEGACY:
                return {"output_compression": 100}
            case OutputCompressionTaxonomy.UNAVAILABLE:
                return {}

    @classmethod
    async def make_args_from_input_images(
        cls,
        input_images_taxonomy: InputImagesTaxonomy,
        *,
        input_images: list[PromptImage] | None,
    ) -> dict[str, Any]:
        """Map input images to provider-specific API parameters for image-to-image generation.

        Args:
            input_images_taxonomy: The taxonomy specifying how to format images for the target API
            input_images: List of input images to include in the request

        Returns:
            Dictionary of API arguments for the input images
        """
        if not input_images:
            return {}

        if input_images_taxonomy == InputImagesTaxonomy.NONE:
            msg = "Model does not support image inputs, but input images were provided"
            raise ImgGenParameterError(msg)

        match input_images_taxonomy:
            case InputImagesTaxonomy.GPT_IMAGE:
                # The GPT Image "image" argument is only valid on the OpenAI/Azure /images/edits
                # route, which (unlike /images/generations) takes a multipart/form-data body, so
                # each image is produced here as an httpx-style (filename, bytes, mime_type) file
                # tuple. Max 16 images, each < 50MB, png/webp/jpg.
                prepped_images = await prep_prompt_images(prompt_images=input_images, is_http_url_enabled=False)
                image_files: list[ImageFileTuple] = []
                for index, prepped in enumerate(prepped_images):
                    if isinstance(prepped, PreparedFileBase64):
                        image_bytes = base64.b64decode(prepped.base64_data)
                        image_files.append((f"image_{index}.{prepped.file_type.extension}", image_bytes, prepped.mime_type))
                    elif isinstance(prepped, PreparedFileHttpUrl):
                        # GPT Image API requires the image bytes as a file part, not an HTTP URL
                        msg = "GPT Image API requires image file data, but got HTTP URL"
                        raise ImgGenParameterError(msg)
                    else:
                        msg = f"Unexpected PreparedFile type for GPT Image API: {type(prepped).__name__}"
                        raise ImgGenParameterError(msg)
                return {"image": image_files}

            case InputImagesTaxonomy.BFL_FLUX_2:
                # BFL Flux 2 Pro format: input_image (1st), input_image_2 through input_image_8
                # Max 8 images total, accepts URLs or base64 data URLs
                prepped_images = await prep_prompt_images(prompt_images=input_images, is_http_url_enabled=True)
                args: dict[str, Any] = {}
                for idx, prepped in enumerate(prepped_images[:8]):
                    # 0->input_image, 1->input_image_2, 2->input_image_3, etc.
                    key = "input_image" if idx == 0 else f"input_image_{idx + 1}"
                    if isinstance(prepped, PreparedFileBase64):
                        args[key] = prepped.as_data_url()
                    elif isinstance(prepped, PreparedFileHttpUrl):
                        args[key] = prepped.url
                    else:
                        msg = f"Unexpected PreparedFile type for Flux 2 API: {type(prepped).__name__}"
                        raise ImgGenParameterError(msg)
                return args

    @classmethod
    def make_args_from_input_fidelity(
        cls,
        input_fidelity_taxonomy: InputFidelityTaxonomy,
        *,
        input_fidelity: InputFidelity | None,
        model_name: str,
    ) -> dict[str, Any]:
        """Map input fidelity settings for image editing."""
        if input_fidelity is None:
            return {}

        match input_fidelity_taxonomy:
            case InputFidelityTaxonomy.GPT_IMAGE_LEGACY:
                return {
                    "input_fidelity": OpenAIImgGenFactory.input_fidelity_for_openai_image(input_fidelity=input_fidelity),
                }
            case InputFidelityTaxonomy.UNAVAILABLE:
                msg = f"Model '{model_name}' does not support input_fidelity"
                raise ImgGenParameterError(msg)
