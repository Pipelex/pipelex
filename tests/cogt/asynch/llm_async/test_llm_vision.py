# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Tuple

import pytest

from pipelex import pretty_print
from pipelex.cogt.exceptions import LLMCapabilityError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageBytes, PromptImagePath, PromptImageUrl
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_job import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.hub import get_llm_worker
from pipelex.tools.misc.base_64 import load_binary_as_base64
from tests.cogt.test_data import LLMVisionTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestAsyncCogtLLMVision:
    @pytest.mark.parametrize("topic, image_uri", LLMVisionTestCases.IMAGES_MIXED_SOURCES)
    async def test_gen_text_from_vision_by_url_async(self, llm_handle_for_vision: str, topic: str, image_uri: str):
        prompt_image = PromptImageFactory.make_prompt_image_from_uri(uri=image_uri)
        llm_worker_async = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=200, seed=None),
        )
        try:
            generated_text = await llm_worker_async.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")

    async def test_gen_text_from_vision_by_bytes_async(self, vision_image_param: str, llm_handle_for_vision: str):
        image_bytes = load_binary_as_base64(path=vision_image_param)
        prompt_image = PromptImageBytes(b64_image_bytes=image_bytes)
        llm_worker_async = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=200, seed=None),
        )
        try:
            generated_text = await llm_worker_async.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text)
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")

    @pytest.mark.parametrize("topic, image_path", LLMVisionTestCases.IMAGE_PATHS)
    async def test_gen_text_from_vision_by_path_async(self, topic: str, image_path: str, llm_handle_for_vision: str):
        prompt_image = PromptImagePath(file_path=image_path)
        llm_worker_async = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=200, seed=None),
        )
        try:
            generated_text = await llm_worker_async.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")

    @pytest.mark.parametrize("topic, image_pair", LLMVisionTestCases.IMAGE_PATH_PAIRS)
    async def test_gen_text_from_vision_2_images_async(self, llm_handle_for_vision: str, topic: str, image_pair: Tuple[str, str]):
        prompt_image1 = PromptImagePath(file_path=image_pair[0])
        prompt_image2 = PromptImagePath(file_path=image_pair[1])
        llm_worker_async = get_llm_worker(llm_handle=llm_handle_for_vision)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_IMAGES_COMPARE_PROMPT,
            user_images=[prompt_image1, prompt_image2],
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=500, seed=None),
        )
        try:
            generated_text = await llm_worker_async.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Comparative vision of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision capability not supported for this LLM: {llm_handle_for_vision} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle_for_vision} because {exc}")
