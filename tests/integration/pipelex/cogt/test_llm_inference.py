import pytest

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImagePath
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.hub import get_inference_manager, get_report_delegate
from tests.integration.pipelex.cogt.test_data import ImageDescription, LLMTestConstants, LLMVisionTestCases, Person

USER_TEXT_TRICKY_1 = """
When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
How tall do you think he was when he was 12? and at 15?
"""
USER_TEXT_TRICKY_2 = """
Count the Rs in "Strawberry"
"""


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("routing_profile_override")
class TestLLMInference:
    @pytest.mark.parametrize("user_text", [USER_TEXT_TRICKY_1, USER_TEXT_TRICKY_2])
    async def test_simple_gen_text_from_text(self, llm_job_params: LLMJobParams, llm_handle: str, user_text: str):
        log.info(f"test_simple_gen_text_from_text: Testing llm_handle '{llm_handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=user_text,
            ),
            llm_job_params=llm_job_params,
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        get_report_delegate().generate_report()

    async def test_simple_gen_object_from_text(self, llm_job_params: LLMJobParams, llm_handle: str):
        log.info(f"test_simple_gen_object_from_text: Testing llm_handle '{llm_handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_handle)
        if not llm_worker.is_gen_object_supported:
            msg = f"Object generation is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_TO_EXTRACT_PERSON,
            ),
            llm_job_params=llm_job_params,
        )
        generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
        assert generated_object
        pretty_print(generated_object)
        get_report_delegate().generate_report()

    @pytest.mark.parametrize("image_path", [LLMVisionTestCases.PATH_IMG_PNG_1])
    async def test_gen_text_from_image(self, llm_job_params: LLMJobParams, llm_handle: str, image_path: str):
        log.info(f"test_gen_text_from_image: Testing llm_handle '{llm_handle}'")
        prompt_image = PromptImagePath(file_path=image_path)
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_handle)
        if not llm_worker.is_vision_supported:
            msg = f"Vision is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMVisionTestCases.VISION_USER_TEXT_2,
                user_images=[prompt_image],
            ),
            llm_job_params=llm_job_params,
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Vision of {image_path}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle} because {exc}")
        get_report_delegate().generate_report()

    @pytest.mark.parametrize("image_path", [LLMVisionTestCases.PATH_IMG_PNG_1])
    async def test_gen_object_from_image(self, llm_job_params: LLMJobParams, llm_handle: str, image_path: str):
        log.info(f"test_gen_object_from_image: Testing llm_handle '{llm_handle}'")
        prompt_image = PromptImagePath(file_path=image_path)
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_handle)

        if not llm_worker.is_vision_supported:
            msg = f"Vision is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        if not llm_worker.is_gen_object_supported:
            msg = f"Object generation is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text="Analyze this image and provide a title, detailed description, and estimated date or time period.",
                user_images=[prompt_image],
            ),
            llm_job_params=llm_job_params,
        )
        try:
            generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=ImageDescription)
            assert generated_object
            assert generated_object.title
            assert generated_object.description
            assert generated_object.time_period
            pretty_print(generated_object, title=f"Image Description of {image_path}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_handle} because {exc}")
        get_report_delegate().generate_report()
