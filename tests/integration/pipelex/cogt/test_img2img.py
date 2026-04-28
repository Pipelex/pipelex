"""End-to-end inference tests for image-to-image generation."""

from typing import ClassVar

import pytest

from pipelex import log, pretty_print, pretty_print_url
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.hub import get_img_gen_worker
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.image_utils import ImageFormat
from tests.cases import ImageTestCases
from tests.integration.pipelex.fixtures.img_gen_fixtures import skip_if_img_gen_params_unsupported
from tests.integration.pipelex.fixtures.model_combo import ModelCombo

PRIMARY_ID = "img2img_1"
SECONDARY_ID = "img2img_2"


class Img2ImgTestCases:
    """Test cases for image-to-image generation."""

    # Editing prompts for image-to-image tests
    EDIT_PROMPT_SINGLE = "Add a colorful sunset sky in the background"
    EDIT_PROMPT_STYLE = "Transform this image into a watercolor painting style"
    EDIT_PROMPT_MULTI = "Combine these images into a cohesive collage that blends their concepts and their graphic styles"

    # Single input image test cases: (topic, image_uri)
    SINGLE_INPUT_IMAGES: ClassVar[list[tuple[str, str]]] = [
        ("PNG local file", ImageTestCases.IMAGE_FILE_PATH_PNG_1),
        ("JPG local file", ImageTestCases.IMAGE_FILE_PATH_JPG_3),
    ]

    # Multiple input images test cases: (topic, list of image_uris)
    MULTIPLE_INPUT_IMAGES: ClassVar[list[tuple[str, list[str]]]] = [
        (
            "Two JPG files",
            [ImageTestCases.IMAGE_FILE_PATH_JPG_1, ImageTestCases.IMAGE_FILE_PATH_JPG_3],
        ),
        (
            "Mixed PNG and JPG",
            [ImageTestCases.IMAGE_FILE_PATH_PNG_1, ImageTestCases.IMAGE_FILE_PATH_JPG_1],
        ),
    ]

    # Remote URL input image test cases: (topic, image_url)
    REMOTE_URL_IMAGES: ClassVar[list[tuple[str, str]]] = [
        ("PNG remote URL", ImageTestCases.IMAGE_URL_PNG),
    ]


@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageToImageGeneration:
    """End-to-end tests for image-to-image generation."""

    @pytest.mark.parametrize(
        ("topic", "image_uri"),
        Img2ImgTestCases.SINGLE_INPUT_IMAGES,
    )
    async def test_img2img_single_input_image(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
        topic: str,
        image_uri: str,
    ):
        """Test image editing with a single input image."""
        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        if not img_gen_worker.is_img2img_supported:
            msg = f"Image-to-image is not supported for this worker: '{img_gen_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        pretty_print(f"Testing img2img with handle '{img_gen_combo.handle}', input: {topic}")

        # Create prompt with input image
        input_image = PromptImageUri(uri=image_uri)
        img_gen_prompt = ImgGenPrompt(
            positive_text=Img2ImgTestCases.EDIT_PROMPT_SINGLE,
            input_images=[input_image],
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )
        skip_if_img_gen_params_unsupported(img_gen_worker.inference_model, img_gen_job_params, has_input_images=True)

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

    @pytest.mark.parametrize(
        ("topic", "image_uri"),
        Img2ImgTestCases.SINGLE_INPUT_IMAGES,
    )
    async def test_img2img_style_apply(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
        topic: str,
        image_uri: str,
    ):
        """Test style apply with a single input image."""
        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        if not img_gen_worker.is_img2img_supported:
            msg = f"Image-to-image is not supported for this worker: '{img_gen_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        pretty_print(f"Testing img2img style apply with handle '{img_gen_combo.handle}', input: {topic}")

        # Use parametrized source image for style transfer
        input_image = PromptImageUri(uri=image_uri)
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
        skip_if_img_gen_params_unsupported(img_gen_worker.inference_model, img_gen_job_params, has_input_images=True)

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

    @pytest.mark.parametrize(
        ("topic", "image_uris"),
        Img2ImgTestCases.MULTIPLE_INPUT_IMAGES,
    )
    async def test_img2img_multiple_input_images(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
        topic: str,
        image_uris: list[str],
    ):
        """Test image editing with multiple input images.

        Models supporting multiple inputs:
        - flux-2-pro: up to 8 images
        - gpt-image-1.5: up to 16 images
        """
        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        if not img_gen_worker.is_img2img_supported:
            msg = f"Image-to-image is not supported for this worker: '{img_gen_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        pretty_print(f"Testing img2img with multiple inputs, handle '{img_gen_combo.handle}', input: {topic}")

        # Create prompt with multiple input images
        input_images: list[PromptImage] = [PromptImageUri(uri=uri) for uri in image_uris]
        img_gen_prompt = ImgGenPrompt(
            positive_text=Img2ImgTestCases.EDIT_PROMPT_MULTI,
            negative_text="distorted, artifacts",
            input_images=input_images,
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )
        skip_if_img_gen_params_unsupported(img_gen_worker.inference_model, img_gen_job_params, has_input_images=True)

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

    @pytest.mark.parametrize(
        ("topic", "image_url"),
        Img2ImgTestCases.REMOTE_URL_IMAGES,
    )
    async def test_img2img_with_remote_url(
        self,
        job_metadata: JobMetadata,
        img_gen_combo: ModelCombo,
        generated_content_factory: GeneratedContentFactory,
        topic: str,
        image_url: str,
    ):
        """Test image editing with a remote URL as input image."""
        img_gen_worker = get_img_gen_worker(img_gen_handle=img_gen_combo.handle)
        if not img_gen_worker.is_img2img_supported:
            msg = f"Image-to-image is not supported for this worker: '{img_gen_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        pretty_print(f"Testing img2img with remote URL, handle '{img_gen_combo.handle}', input: {topic}")

        # Use remote URL instead of local file
        input_image = PromptImageUri(uri=image_url)
        img_gen_prompt = ImgGenPrompt(
            positive_text="Render the essential topic of this image. Add dramatic lighting and enhance the colors",
            negative_text="dark, desaturated",
            input_images=[input_image],
        )

        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            output_format=ImageFormat.PNG,
        )
        skip_if_img_gen_params_unsupported(img_gen_worker.inference_model, img_gen_job_params, has_input_images=True)

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
