from typing import Any, Dict, List, Optional

from pipelex import log
from pipelex.cogt.exceptions import ImggGeneratedTypeError, ImggParameterError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job import ImggJob
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, OutputFormat, Quality
from pipelex.config import get_config


class FalFactory:
    @staticmethod
    def make_fal_application(imgg_engine: ImggEngine) -> str:
        return f"{imgg_engine.imgg_platform}/{imgg_engine.imgg_model_name}"

    @classmethod
    def make_nb_steps_from_quality_for_flux_pro(cls, quality: Quality) -> int:
        flux_map_quality_to_steps = get_config().plugins.fal_config.flux_map_quality_to_steps
        return flux_map_quality_to_steps[quality.value]

    @classmethod
    def make_nb_steps_from_quality_for_sdxl_lightning(cls, quality: Quality) -> int:
        sdxl_lightning_map_quality_to_steps = get_config().plugins.fal_config.sdxl_lightning_map_quality_to_steps
        return sdxl_lightning_map_quality_to_steps[quality.value]

    @classmethod
    def make_image_size_for_flux_1(cls, aspect_ratio: AspectRatio) -> str:
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return "square_hd"
            case AspectRatio.LANDSCAPE_4_3:
                return "landscape_4_3"
            case AspectRatio.LANDSCAPE_16_9:
                return "landscape_16_9"
            case AspectRatio.LANDSCAPE_21_9:
                return "landscape_21_9"
            case AspectRatio.PORTRAIT_3_4:
                return "portrait_4_3"
            case AspectRatio.PORTRAIT_9_16:
                return "portrait_16_9"
            case AspectRatio.PORTRAIT_9_21:
                return "portrait_21_9"
            case AspectRatio.LANDSCAPE_3_2 | AspectRatio.PORTRAIT_2_3:
                raise ImggParameterError(f"Aspect ratio '{aspect_ratio}' is not supported by Flux-1 image generation model")

    @classmethod
    def make_aspect_ratio_for_flux_1_1_ultra(cls, aspect_ratio: AspectRatio) -> str:
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return "1:1"
            case AspectRatio.LANDSCAPE_4_3:
                return "4:3"
            case AspectRatio.LANDSCAPE_16_9:
                return "16:9"
            case AspectRatio.LANDSCAPE_21_9:
                return "21:9"
            case AspectRatio.PORTRAIT_3_4:
                return "3:4"
            case AspectRatio.PORTRAIT_9_16:
                return "9:16"
            case AspectRatio.PORTRAIT_9_21:
                return "9:21"
            case AspectRatio.LANDSCAPE_3_2 | AspectRatio.PORTRAIT_2_3:
                raise ImggParameterError(f"Aspect ratio '{aspect_ratio}' is not supported by Flux-1.1 Ultra image generation model")

    @classmethod
    def make_output_format_for_flux(cls, output_format: OutputFormat) -> str:
        match output_format:
            case OutputFormat.PNG:
                return "png"
            case OutputFormat.JPG:
                return "jpeg"
            case OutputFormat.WEBP:
                raise ImggParameterError("Output format WebP is not supported for Flux")

    @classmethod
    def make_fal_arguments(
        cls,
        fal_application: str,
        imgg_job: ImggJob,
        nb_images: int,
    ) -> Dict[str, Any]:
        params = imgg_job.job_params
        args_dict: Dict[str, Any]
        num_inference_steps: Optional[int]
        match fal_application:
            case ImggHandle.FLUX_1_PRO_LEGACY | ImggHandle.FLUX_1_1_PRO:
                num_inference_steps = params.nb_steps
                if not num_inference_steps and (quality := params.quality):
                    num_inference_steps = cls.make_nb_steps_from_quality_for_flux_pro(quality=quality)

                args_dict = {
                    "prompt": imgg_job.imgg_prompt.positive_text,
                    "image_size": cls.make_image_size_for_flux_1(params.aspect_ratio),
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": params.guidance_scale,
                    "num_images": nb_images,
                    "enable_safety_checker": params.is_moderated,
                    "safety_tolerance": params.safety_tolerance,
                    "seed": params.seed,
                    "output_format": cls.make_output_format_for_flux(params.output_format),
                    "sync_mode": imgg_job.job_config.is_sync_mode,
                }
            case ImggHandle.FLUX_1_1_ULTRA:
                args_dict = {
                    "prompt": imgg_job.imgg_prompt.positive_text,
                    "aspect_ratio": cls.make_aspect_ratio_for_flux_1_1_ultra(params.aspect_ratio),
                    "num_images": nb_images,
                    "enable_safety_checker": params.is_moderated,
                    "safety_tolerance": params.safety_tolerance,
                    "raw": params.is_raw,
                    "seed": params.seed,
                    "output_format": cls.make_output_format_for_flux(params.output_format),
                    "sync_mode": imgg_job.job_config.is_sync_mode,
                }
            case ImggHandle.SDXL_LIGHTNING:
                num_inference_steps = params.nb_steps
                if not num_inference_steps and (quality := params.quality):
                    num_inference_steps = cls.make_nb_steps_from_quality_for_sdxl_lightning(quality=quality)
                acceptable_steps = [1, 2, 4, 8]
                if num_inference_steps not in acceptable_steps:
                    log.warning(f"Number of inference steps {num_inference_steps}' for SDXL Lightning must be one of {acceptable_steps}")
                    num_inference_steps = 8
                args_dict = {
                    "prompt": imgg_job.imgg_prompt.positive_text,
                    "image_size": cls.make_image_size_for_flux_1(params.aspect_ratio),
                    "num_inference_steps": num_inference_steps,
                    "num_images": nb_images,
                    "seed": params.seed,
                    "output_format": cls.make_output_format_for_flux(params.output_format),
                    "sync_mode": imgg_job.job_config.is_sync_mode,
                }
            case _:
                raise ImggParameterError(f"Invalid fal application: '{fal_application}'")

        return args_dict

    @staticmethod
    def make_generated_image(fal_result: Dict[str, Any]) -> GeneratedImage:
        images = fal_result["images"]
        fal_image_dict = images[0]
        image_url = fal_image_dict["url"]
        if not isinstance(image_url, str):
            raise ImggGeneratedTypeError("Image url is not a string")
        # TODO: if the url is actual image data, send it to cloud storage?

        width = fal_image_dict["width"]
        if not isinstance(width, int):
            raise ImggGeneratedTypeError("Image width is not an integer")
        height = fal_image_dict["height"]
        if not isinstance(height, int):
            raise ImggGeneratedTypeError("Image height is not an integer")

        generated_image = GeneratedImage(
            url=image_url,
            width=width,
            height=height,
        )
        return generated_image

    @staticmethod
    def make_generated_image_list(fal_result: Dict[str, Any]) -> List[GeneratedImage]:
        fal_image_dicts = fal_result["images"]

        generated_image_list: List[GeneratedImage] = []
        for fal_image_dict in fal_image_dicts:
            image_url = fal_image_dict["url"]
            if not isinstance(image_url, str):
                raise ImggGeneratedTypeError("Image url is not a string")

            width = fal_image_dict["width"]
            if not isinstance(width, int):
                raise ImggGeneratedTypeError("Image width is not an integer")
            height = fal_image_dict["height"]
            if not isinstance(height, int):
                raise ImggGeneratedTypeError("Image height is not an integer")

            generated_image = GeneratedImage(
                url=image_url,
                width=width,
                height=height,
            )
            generated_image_list.append(generated_image)

        return generated_image_list
