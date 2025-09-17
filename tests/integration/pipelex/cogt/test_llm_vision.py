from typing import Tuple

import pytest

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import LLMCapabilityError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageBytes, PromptImagePath
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_job import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.hub import get_llm_worker
from pipelex.tools.misc.base_64_utils import load_binary_as_base64
from tests.integration.pipelex.cogt.test_data import LLMVisionTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMVision:
    @pytest.mark.parametrize("topic, image_uri", LLMVisionTestCases.IMAGES_MIXED_SOURCES)
    async def test_gen_text_from_vision_by_url(self, llm_handle_for_vision: str, topic: str, image_uri: str):
        prompt_image = PromptImageFactory.make_prompt_image_from_uri(uri=image_uri)
        llm_worker = get_llm_worker(llm_handle=llm_handle_for_vision)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=1000, seed=None),
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")

    @pytest.mark.parametrize("topic, image_path", LLMVisionTestCases.IMAGE_PATHS)
    async def test_gen_text_from_vision_by_bytes(self, llm_handle_for_vision: str, topic: str, image_path: str):
        image_bytes = load_binary_as_base64(path=image_path)
        prompt_image = PromptImageBytes(base_64=image_bytes)
        llm_worker = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=1000, seed=None),
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")

    @pytest.mark.parametrize("topic, image_path", LLMVisionTestCases.IMAGE_PATHS)
    async def test_gen_text_from_vision_by_path(self, llm_handle_for_vision: str, topic: str, image_path: str):
        prompt_image = PromptImagePath(file_path=image_path)
        llm_worker = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=1000, seed=None),
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")

    @pytest.mark.parametrize("topic, image_pair", LLMVisionTestCases.IMAGE_PATH_PAIRS)
    async def test_gen_text_from_vision_2_images(self, llm_handle_for_vision: str, topic: str, image_pair: Tuple[str, str]):
        prompt_image1 = PromptImagePath(file_path=image_pair[0])
        prompt_image2 = PromptImagePath(file_path=image_pair[1])
        llm_worker = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_IMAGES_COMPARE_PROMPT,
            user_images=[prompt_image1, prompt_image2],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=2000, seed=None),
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Comparative vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")
