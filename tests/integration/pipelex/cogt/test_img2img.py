"""End-to-end inference tests for image-to-image generation."""

import pytest

from pipelex import pretty_print, pretty_print_url
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.hub import get_img_gen_worker
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.image_utils import ImageFormat
from tests.cases import ImageTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo

PRIMARY_ID = "img2img_1"
SECONDARY_ID = "img2img_2"


class Img2ImgTestCases:
    """Test cases for image-to-image generation."""

    # Editing prompts for image-to-image tests
    EDIT_PROMPT_SINGLE = "Add a colorful sunset sky in the background"
    EDIT_PROMPT_STYLE = "Transform this image into a watercolor painting style"
    EDIT_PROMPT_MULTI = "Combine these images into a cohesive collage"


@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageToImageGeneration:
    """End-to-end tests for image-to-image generation."""

    async def test_img2img_single_input_image(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
    ):
        """Test image editing with a single input image."""
        pretty_print(f"Testing img2img with handle '{img_gen_combo.handle}'")

        # Create prompt with input image
        input_image = PromptImageUri(uri=ImageTestCases.IMAGE_FILE_PATH_PNG_1)
        img_gen_prompt = ImgGenPrompt(
            positive_text=Img2ImgTestCases.EDIT_PROMPT_SINGLE,
            negative_text="blurry, low quality",
            input_images=[input_image],
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )

        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt(
            img_gen_prompt=img_gen_prompt,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )

        generated_image_raw_details = await img_gen_worker.gen_image(
            img_gen_job=img_gen_job,
        )
        pretty_print(generated_image_raw_details, title="Generated image raw details")

        image_content = await generated_content_factory.make_image_content(
            primary_id=PRIMARY_ID,
            secondary_id=SECONDARY_ID,
            raw_details=generated_image_raw_details,
        )
        pretty_print(image_content, title="Image content")

        assert image_content.public_url is not None
        pretty_print_url(image_content.public_url, title="Generated Image URL")

    async def test_img2img_style_transfer(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
    ):
        """Test style transfer with a single input image."""
        pretty_print(f"Testing img2img style transfer with handle '{img_gen_combo.handle}'")

        # Use a different source image for style transfer
        input_image = PromptImageUri(uri=ImageTestCases.IMAGE_FILE_PATH_JPG_3)
        img_gen_prompt = ImgGenPrompt(
            positive_text=Img2ImgTestCases.EDIT_PROMPT_STYLE,
            negative_text=None,
            input_images=[input_image],
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )

        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt(
            img_gen_prompt=img_gen_prompt,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )

        generated_image_raw_details = await img_gen_worker.gen_image(
            img_gen_job=img_gen_job,
        )
        pretty_print(generated_image_raw_details, title="Generated image raw details (style transfer)")

        image_content = await generated_content_factory.make_image_content(
            primary_id=PRIMARY_ID,
            secondary_id=SECONDARY_ID,
            raw_details=generated_image_raw_details,
        )
        pretty_print(image_content, title="Image content (style transfer)")

        assert image_content.public_url is not None
        pretty_print_url(image_content.public_url, title="Generated Image URL (style transfer)")

    async def test_img2img_multiple_input_images(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
    ):
        """Test image editing with multiple input images.

        Models supporting multiple inputs:
        - flux-2-pro: up to 8 images
        - gpt-image-1.5: up to 16 images
        """
        pretty_print(f"Testing img2img with multiple inputs, handle '{img_gen_combo.handle}'")

        # Create prompt with multiple input images
        input_images: list[PromptImage] = [
            PromptImageUri(uri=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
            PromptImageUri(uri=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
        ]
        img_gen_prompt = ImgGenPrompt(
            positive_text=Img2ImgTestCases.EDIT_PROMPT_MULTI,
            negative_text="distorted, artifacts",
            input_images=input_images,
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )

        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt(
            img_gen_prompt=img_gen_prompt,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )

        generated_image_raw_details = await img_gen_worker.gen_image(
            img_gen_job=img_gen_job,
        )
        pretty_print(generated_image_raw_details, title="Generated image raw details (multi-input)")

        image_content = await generated_content_factory.make_image_content(
            primary_id=PRIMARY_ID,
            secondary_id=SECONDARY_ID,
            raw_details=generated_image_raw_details,
        )
        pretty_print(image_content, title="Image content (multi-input)")

        assert image_content.public_url is not None
        pretty_print_url(image_content.public_url, title="Generated Image URL (multi-input)")

    async def test_img2img_with_remote_url(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
    ):
        """Test image editing with a remote URL as input image."""
        pretty_print(f"Testing img2img with remote URL, handle '{img_gen_combo.handle}'")

        # Use remote URL instead of local file
        input_image = PromptImageUri(uri=ImageTestCases.IMAGE_URL_PNG)
        img_gen_prompt = ImgGenPrompt(
            positive_text="Add dramatic lighting and enhance the colors",
            negative_text="dark, desaturated",
            input_images=[input_image],
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )

        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt(
            img_gen_prompt=img_gen_prompt,
            job_metadata=job_metadata,
            img_gen_job_params=img_gen_job_params,
        )

        generated_image_raw_details = await img_gen_worker.gen_image(
            img_gen_job=img_gen_job,
        )
        pretty_print(generated_image_raw_details, title="Generated image raw details (remote URL)")

        image_content = await generated_content_factory.make_image_content(
            primary_id=PRIMARY_ID,
            secondary_id=SECONDARY_ID,
            raw_details=generated_image_raw_details,
        )
        pretty_print(image_content, title="Image content (remote URL)")

        assert image_content.public_url is not None
        pretty_print_url(image_content.public_url, title="Generated Image URL (remote URL)")
