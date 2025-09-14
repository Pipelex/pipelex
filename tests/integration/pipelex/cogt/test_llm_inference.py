from typing import Tuple

import pytest

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import LLMCapabilityError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageBytes, PromptImagePath
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.hub import get_inference_manager, get_llm_worker
from pipelex.tools.misc.base_64_utils import load_binary_as_base64
from tests.integration.pipelex.cogt.test_data import LLMTestConstants, LLMVisionTestCases, Person


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMInference:
    async def run_inference(self, llm_worker: LLMWorkerAbstract, llm_job: LLMJob):
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        if llm_worker.is_gen_object_supported:
            generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
            assert generated_object
            pretty_print(generated_object)
        else:
            log.info(f"No object generation supported for this worker: '{llm_worker.desc}'")

    async def test_gen_text_from_text(self, llm_job_params: LLMJobParams, llm_handle: str):
        log.info(f"Testing llm_handle '{llm_handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text=None,
            user_text=LLMTestConstants.USER_TEXT_SHORT,
            llm_job_params=llm_job_params,
        )
        await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)

    @pytest.mark.parametrize("image_path", [LLMVisionTestCases.PATH_IMG_PNG_1])
    async def test_gen_text_from_image(self, llm_job_params: LLMJobParams, llm_handle: str, image_path: str):
        prompt_image = PromptImagePath(file_path=image_path)
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_handle)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
            user_images=[prompt_image],
            llm_job_params=llm_job_params,
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {image_path}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Vision not supported for this LLM: {llm_handle} because {exc}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle} because {exc}")
