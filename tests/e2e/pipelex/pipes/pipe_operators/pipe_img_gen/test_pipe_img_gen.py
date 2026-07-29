"""E2E tests for PipeImgGen operator including text-to-image and img2img."""

import io
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest
from PIL import Image

from pipelex import pretty_print
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from tests.cases import ImageTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators/pipe_img_gen"]


@pytest.mark.img_gen
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeImgGen:
    """E2E tests for PipeImgGen operator."""

    async def test_generate_image_basic(self, pipe_run_mode: PipeRunMode):
        """Test basic text-to-image generation with a simple prompt."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="generate_image_basic_e2e",
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.url is not None
            pretty_print(image_content.public_url, title="Generated Image URL (basic)")

    @pytest.mark.xfail(reason="Negative prompt is not supported by most models and when it is, it doesn't work well", strict=False)
    async def test_generate_image_with_negative_prompt(self, pipe_run_mode: PipeRunMode):
        """Test text-to-image generation with negative prompt."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="generate_image_with_negative_e2e",
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.url is not None
            pretty_print(image_content.public_url, title="Generated Image URL (with negative prompt)")

    async def test_generate_image_from_text(self, pipe_run_mode: PipeRunMode):
        """Test image generation with dynamic prompt from input."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="generate_image_from_input_e2e",
            inputs={"image_prompt": "A serene Japanese garden with cherry blossoms"},
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.url is not None
            pretty_print(image_content.public_url, title="Generated Image URL (from input)")

    @pytest.mark.parametrize(
        ("topic", "pipe_code", "expected_width", "expected_height"),
        [
            ("nano-banana-2 2K 16:9", "generate_image_2k_nano_banana_2_e2e", 2752, 1536),
            ("gpt-image-2 2K 16:9", "generate_image_2k_gpt_image_2_e2e", 3072, 1728),
        ],
    )
    async def test_generate_image_2k_size_tier(
        self,
        pipe_run_mode: PipeRunMode,
        topic: str,
        pipe_code: str,
        expected_width: int,
        expected_height: int,
    ):
        """Smoke the portable `size = "2k"` tier on the wire: the provider must return 2K-class pixels, not its 1K default."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code=pipe_code,
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.public_url is not None
            pretty_print(image_content.public_url, title=f"Generated Image URL (2K tier - {topic})")
            # The storage provider decides the URL shape: fetch http(s) URLs, read file:// URIs / local paths
            parsed_url = urlparse(image_content.public_url)
            if parsed_url.scheme in {"http", "https"}:
                image_bytes = await fetch_file_from_url_httpx(url=image_content.public_url)
            elif parsed_url.scheme == "file":
                # file:// paths are URI-formatted (percent-encoded) — decode before touching the filesystem
                image_bytes = Path(url2pathname(parsed_url.path)).read_bytes()
            else:
                image_bytes = Path(image_content.public_url).read_bytes()
            with Image.open(io.BytesIO(image_bytes)) as generated_image:
                assert generated_image.size == (expected_width, expected_height), (
                    f"{topic}: expected {expected_width}x{expected_height}, got {generated_image.size[0]}x{generated_image.size[1]}"
                )

    @pytest.mark.parametrize(
        ("topic", "image_uri"),
        [
            ("PNG local file", ImageTestCases.IMAGE_FILE_PATH_PNG_1),
            ("JPG local file", ImageTestCases.IMAGE_FILE_PATH_JPG_3),
        ],
    )
    async def test_img2img_from_single_image(
        self,
        pipe_run_mode: PipeRunMode,
        topic: str,
        image_uri: str,
    ):
        """Test img2img with a single input image."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="img2img_single_input_e2e",
            inputs={"source_image": ImageContent(url=image_uri)},
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.url is not None
            pretty_print(image_content.public_url, title=f"Generated Image URL (img2img single - {topic})")

    @pytest.mark.parametrize(
        ("topic", "image_uri"),
        [
            ("PNG local file", ImageTestCases.IMAGE_FILE_PATH_PNG_1),
            ("JPG local file", ImageTestCases.IMAGE_FILE_PATH_JPG_3),
        ],
    )
    async def test_img2img_style_transfer(
        self,
        pipe_run_mode: PipeRunMode,
        topic: str,
        image_uri: str,
    ):
        """Test img2img style transfer transformation."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="img2img_style_transfer_e2e",
            inputs={"source_image": ImageContent(url=image_uri)},
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.url is not None
            pretty_print(image_content.public_url, title=f"Generated Image URL (style transfer - {topic})")

    @pytest.mark.parametrize(
        ("topic", "style_image_uri", "subject_image_uri"),
        [
            ("Eiffel Tower style + Animalympics subject", ImageTestCases.IMAGE_FILE_PATH_JPG_3, ImageTestCases.IMAGE_FILE_PATH_JPG_1),
            ("Animalympics style + Eiffel Tower subject", ImageTestCases.IMAGE_FILE_PATH_JPG_1, ImageTestCases.IMAGE_FILE_PATH_JPG_3),
            ("AI Lympics style + Solar System subject", ImageTestCases.IMAGE_FILE_PATH_PNG_1, ImageTestCases.IMAGE_FILE_PATH_JPG_2),
        ],
    )
    async def test_img2img_blend_two_images(
        self,
        pipe_run_mode: PipeRunMode,
        topic: str,
        style_image_uri: str,
        subject_image_uri: str,
    ):
        """Test blending two images: style from one and subject from the other."""
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="img2img_blend_two_images_e2e",
            inputs={
                "style_image": ImageContent(url=style_image_uri),
                "subject_image": ImageContent(url=subject_image_uri),
            },
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            image_content = pipe_output.main_stuff_as(content_type=ImageContent)
            assert image_content.url is not None
            pretty_print(image_content.public_url, title=f"Generated Image URL (blend - {topic})")
