from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import LLMCapabilityError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageBase64, PromptImageUri
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.hub import get_llm_worker
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.base64_utils import load_binary_as_base64
from tests.integration.pipelex.cogt.test_data import LLMVisionTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMVision:
    @pytest.mark.parametrize(("topic", "image_uri"), LLMVisionTestCases.IMAGE_URLS)
    async def test_gen_text_from_vision_by_url(
        self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, topic: str, image_uri: str
    ):
        prompt_image = PromptImageFactory.make_prompt_image(uri=image_uri)
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMVisionTestCases.VISION_USER_TEXT,
                user_images=[prompt_image],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )

        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_combo.handle} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")

    @pytest.mark.parametrize(("topic", "image_path"), LLMVisionTestCases.IMAGE_PATHS)
    async def test_gen_text_from_vision_by_bytes(
        self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, topic: str, image_path: str
    ):
        base64_data = await load_binary_as_base64(path=Path(image_path))
        prompt_image = PromptImageBase64(base64_data=base64_data)
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMVisionTestCases.VISION_USER_TEXT,
                user_images=[prompt_image],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_combo.handle} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")

    @pytest.mark.parametrize(("topic", "image_path"), LLMVisionTestCases.IMAGE_PATHS)
    async def test_gen_text_from_vision_by_path(
        self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, topic: str, image_path: str
    ):
        prompt_image = PromptImageUri(uri=image_path)
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMVisionTestCases.VISION_USER_TEXT,
                user_images=[prompt_image],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_combo.handle} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")

    @pytest.mark.parametrize(("topic", "image_pair"), LLMVisionTestCases.IMAGE_PATH_PAIRS)
    async def test_gen_text_from_vision_2_images(
        self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, topic: str, image_pair: tuple[str, str]
    ):
        prompt_image1 = PromptImageUri(uri=image_pair[0])
        prompt_image2 = PromptImageUri(uri=image_pair[1])
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMVisionTestCases.VISION_IMAGES_COMPARE_PROMPT,
                user_images=[prompt_image1, prompt_image2],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Comparative vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_combo.handle} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")

    @pytest.mark.parametrize(("topic", "data_url"), LLMVisionTestCases.IMAGE_DATA_URLS)
    async def test_gen_text_from_vision_by_data_url(
        self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, topic: str, data_url: str
    ):
        """Test LLM vision using a data URL (embedded base64 image).

        This verifies that data URLs like 'data:image/png;base64,...' are correctly
        handled by the LLM vision pipeline.
        """
        prompt_image = PromptImageFactory.make_prompt_image(uri=data_url)
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMVisionTestCases.VISION_USER_TEXT,
                user_images=[prompt_image],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )

        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic} (data URL)")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_combo.handle} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")
