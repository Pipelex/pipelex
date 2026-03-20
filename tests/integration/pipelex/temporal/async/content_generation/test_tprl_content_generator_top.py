import logging

import pytest
from temporalio.client import WorkflowFailureError

from pipelex import pretty_print
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.hub import get_model_deck
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.test_extras.temporal_registry_test_models import Person
from pipelex.temporal.tprl_content_generation.content_generator_top import ContentGeneratorTop
from tests.integration.pipelex.temporal.test_data import PipeTestCases

USER_TEXT_FOR_BASE = """
Write a detailed description of a woman's clothing in the style of a 19th-century novel.
Keep it short: 3 sentences max
"""

USER_TEXT_FOR_SINGLE_PERSON = "name: John, age: 30, job: bank teller"
USER_TEXT_FOR_SINGLE_PERSON_TEXT_THEN_OBJECT = """
Imagine a female character that decides to become a cop once reaching middle age.
Present this character in a couple of very short sentences.
Be sure to include the character's full name, age and job.
"""
MULTIPLE_USER_TEXTS_FOR_PEOPLE = [
    "name: Bob, age: 25, job: banker",
    "name: Maria, age: 35, job: consultant",
    "name: SLartiblfastikur, age: 30, job: fizzy buzzer",
    "name: Alice, age: 40, job: developer",
    "name: Tom, age: 45, job: TV presenter",
    "name: Jerry, age: 50, job: nurse",
]
USER_TEXTS_FOR_PEOPLE_STR = "\n".join(MULTIPLE_USER_TEXTS_FOR_PEOPLE)
USER_TEXT_FOR_MULTIPLE_PEOPLE_TEXT_THEN_OBJECT = """
Imagine the 4 main characters for a sitcom in Paris.
Present each character in one very short sentence.
Be sure to include each character's full name, age and job.
"""

USER_TEXT_FOR_HAIKU = """
Write a haiku about the meaning of life
"""

# silence a warning that comes from deep down in temporalio's pydantic converter
pytestmark = pytest.mark.filterwarnings("ignore:The `parse_obj` method is deprecated")


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTprlCrafterTop:
    @pytest.mark.llm
    @pytest.mark.inference
    async def test_tprl_make_llm_text_only(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        llm_setting_main = get_model_deck().get_llm_setting(llm_choice="$testing-text")

        text: str = await top_crafter.make_llm_text(
            job_metadata=tprl_job_metadata,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_BASE),
            llm_setting_main=llm_setting_main,
        )
        pretty_print(text, title="make_llm_text")

        assert isinstance(text, str)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_tprl_make_object_direct(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="$testing-structured")

        person_direct: Person = await top_crafter.make_object_direct(
            job_metadata=tprl_job_metadata,
            object_class=Person,
            llm_prompt_for_object=LLMPrompt(user_text=USER_TEXT_FOR_SINGLE_PERSON),
            llm_setting_for_object=llm_setting_for_object,
        )
        pretty_print(person_direct, title="make_object_direct")

        assert isinstance(person_direct, Person)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_tprl_make_text_then_object(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        llm_setting_main = get_model_deck().get_llm_setting(llm_choice="$testing-text")
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="$testing-structured")

        person_tto: Person = await top_crafter.make_text_then_object(
            job_metadata=tprl_job_metadata,
            object_class=Person,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_SINGLE_PERSON_TEXT_THEN_OBJECT),
            llm_setting_main=llm_setting_main,
            llm_setting_for_object=llm_setting_for_object,
        )
        pretty_print(person_tto, title="make_text_then_object")

        assert isinstance(person_tto, Person)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_tprl_make_object_list_direct(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="$testing-structured")

        person_list_direct: list[Person] = await top_crafter.make_object_list_direct(
            job_metadata=tprl_job_metadata,
            object_class=Person,
            llm_prompt_for_object_list=LLMPrompt(user_text=USER_TEXTS_FOR_PEOPLE_STR),
            llm_setting_for_object_list=llm_setting_for_object,
        )
        pretty_print(person_list_direct, title="make_object_list_direct")

        assert isinstance(person_list_direct, list)
        assert all(isinstance(person, Person) for person in person_list_direct)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_tprl_make_text_then_object_list(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        llm_setting_main = get_model_deck().get_llm_setting(llm_choice="$testing-text")
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="$testing-structured")

        person_list_tto: list[Person] = await top_crafter.make_text_then_object_list(
            job_metadata=tprl_job_metadata,
            object_class=Person,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_MULTIPLE_PEOPLE_TEXT_THEN_OBJECT),
            llm_setting_main=llm_setting_main,
            llm_setting_for_object_list=llm_setting_for_object,
        )
        pretty_print(person_list_tto, title="make_text_then_object_list")

        assert isinstance(person_list_tto, list)
        assert all(isinstance(person, Person) for person in person_list_tto)

    @pytest.mark.img_gen
    @pytest.mark.inference
    async def test_tprl_craft_image(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        image: ImageContent = await top_crafter.make_single_image(
            job_metadata=tprl_job_metadata,
            img_gen_handle="@default-small ",
            img_gen_prompt=ImgGenPrompt(
                positive_text="A dog with sunglasses coding on a laptop",
            ),
        )
        pretty_print(image, title="craft_image")
        assert isinstance(image, ImageContent)

    async def test_tprl_jinja2_text(self, top_crafter: ContentGeneratorTop):
        context = {
            "the_answer": "elementary, my dear Watson",
        }

        jinja2_text: str = await top_crafter.make_templated_text(
            context=context,
            template="The answer is: {{ the_answer }}",
        )
        pretty_print(jinja2_text, title="jinja2_text")
        assert isinstance(jinja2_text, str)
        assert jinja2_text == "The answer is: elementary, my dear Watson"

    @pytest.mark.extract
    @pytest.mark.inference
    async def test_tprl_extract(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        extract_output: list[PageContent] = await top_crafter.make_extract_pages(
            job_metadata=tprl_job_metadata,
            extract_handle="azure-document-intelligence",
            extract_input=ExtractInput(image_uri=PipeTestCases.IMG_EXPENSE_REPORT_1),
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )
        pretty_print(extract_output, title="extract_pages")
        assert isinstance(extract_output, list)
        assert all(isinstance(page, PageContent) for page in extract_output)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_tprl_make_llm_text_with_error(self, tprl_job_metadata: JobMetadata, top_crafter: ContentGeneratorTop):
        bad_handle_to_test_failure = "bad_handle_to_test_failure"
        llm_setting_main = LLMSetting(model=bad_handle_to_test_failure, temperature=0.5, max_tokens=100)
        # Filter out Temporal's "Completing activity as failed" traceback for this expected failure

        class _ActivityFailedFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:  # pyright: ignore[reportImplicitOverride]
                return "Completing activity as failed" not in record.getMessage()

        activity_failed_filter = _ActivityFailedFilter()
        activity_logger = logging.getLogger("temporalio.activity")
        activity_logger.addFilter(activity_failed_filter)
        try:
            with pytest.raises(WorkflowFailureError) as excinfo:
                await top_crafter.make_llm_text(
                    job_metadata=tprl_job_metadata,
                    llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_BASE),
                    llm_setting_main=llm_setting_main,
                )
        finally:
            activity_logger.removeFilter(activity_failed_filter)
        workflow_failure_error = excinfo.value
        assert str(workflow_failure_error) == "Workflow execution failed"
        pretty_print(f"Caught expected error: {workflow_failure_error}, caused by {workflow_failure_error.cause}")
        cause_str = str(workflow_failure_error.cause)
        assert any(
            expected in cause_str
            for expected in [
                f"CogtManagerWorkerSetupError: No worker has been setup for '{bad_handle_to_test_failure}'",
                f"ConfigNotFoundError: LLM Engine blueprint for llm_handle '{bad_handle_to_test_failure}' not found in deck's engine blueprints",
                f"ModelNotFoundError: Model handle '{bad_handle_to_test_failure}' was not found in the model deck",
            ]
        )
