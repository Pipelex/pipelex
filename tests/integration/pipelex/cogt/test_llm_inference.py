import pytest
from pydantic import BaseModel

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.hub import get_inference_manager
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import ImageDescription, LLMTestConstants, LLMVisionTestCases, Person
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMInference:
    @pytest.mark.parametrize("user_text", [LLMTestConstants.USER_TEXT_SUPER_SHORT])
    async def test_simple_gen_text_from_text(self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, user_text: str):
        log.info(f"test_simple_gen_text_from_text: Testing llm_handle '{llm_combo.handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_combo.handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=user_text,
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        # get_report_delegate().generate_report()

    async def test_simple_gen_object_from_text(self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo):
        log.info(f"test_simple_gen_object_from_text: Testing llm_handle '{llm_combo.handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_combo.handle)
        if not llm_worker.is_gen_object_supported:
            msg = f"Object generation is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_TO_EXTRACT_PERSON,
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
        assert generated_object
        pretty_print(generated_object)
        # get_report_delegate().generate_report()

    async def test_simple_gen_object_list_from_text(self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo):
        """Generate a list of structured objects from a text prompt."""
        log.info(f"test_simple_gen_object_list_from_text: Testing llm_handle '{llm_combo.handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_combo.handle)
        if not llm_worker.is_gen_object_supported:
            msg = f"Object generation is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

        class PersonList(BaseModel):
            items: list[Person]

        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_TO_GEN_PERSON_LIST,
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        generated_list = await llm_worker.gen_object(llm_job=llm_job, schema=PersonList)
        assert generated_list
        assert generated_list.items
        assert len(generated_list.items) >= 2
        for person in generated_list.items:
            assert person.name
            assert person.age > 0
        pretty_print(generated_list, title="Generated person list")

    @pytest.mark.parametrize("image_path", [LLMVisionTestCases.PATH_IMG_PNG_1])
    async def test_gen_text_from_image(self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, image_path: str):
        log.info(f"test_gen_text_from_image: Testing llm_handle '{llm_combo.handle}'")
        prompt_image = PromptImageUri(uri=image_path)
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_combo.handle)
        if not llm_worker.is_vision_supported:
            msg = f"Vision is not supported for this LLM worker: '{llm_worker.desc}'"
            log.info(msg)
            pytest.skip(msg)

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
            pretty_print(generated_text, title=f"Vision of {image_path}")
        except PromptImageFormatError as exc:
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")
        # get_report_delegate().generate_report()

    @pytest.mark.parametrize("image_path", [LLMVisionTestCases.PATH_IMG_PNG_1])
    async def test_gen_object_from_image(self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo, image_path: str):
        log.info(f"test_gen_object_from_image: Testing llm_handle '{llm_combo.handle}'")
        prompt_image = PromptImageUri(uri=image_path)
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_combo.handle)

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
            job_metadata=job_metadata,
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
            pytest.skip(f"Prompt Image format not supported for this LLM: {llm_combo.handle} because {exc}")
        # get_report_delegate().generate_report()
