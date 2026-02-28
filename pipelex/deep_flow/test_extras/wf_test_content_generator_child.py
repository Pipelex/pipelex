from temporalio import workflow

from pipelex import pretty_print
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.pipeline.job_metadata import JobMetadata

with workflow.unsafe.imports_passed_through():
    from tests.test_data import PipeTestCases

    from pipelex import pretty_print
    from pipelex.cogt.extract.extract_input import ExtractInput
    from pipelex.cogt.llm.llm_prompt import LLMPrompt
    from pipelex.deep_flow.log_temporal import workflow_log
    from pipelex.deep_flow.test_extras.deep_flow_registry_test_models import Person
    from pipelex.deep_flow.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory
    from pipelex.pipeline.job_metadata import JobMetadata


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

POSITIVE_TEXT_FOR_IMAGE = "A group of dogs with sunglasses playing beer pong with drinks and snacks"


@workflow.defn(name="wf_test_content_generator_child")
class WfTestContentGeneratorChild:
    @workflow.run
    async def run(self):
        workflow_log.debug("Workflow start")
        child_crafter = ContentGeneratorChildFactory.make_content_generator_child()

        llm_setting_for_text = get_llm_deck().get_llm_setting(llm_setting_or_preset_id="llm_for_testing_gen_text")
        crafted_text = await child_crafter.make_llm_text(
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
            llm_setting_main=llm_setting_for_text,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_BASE),
        )
        pretty_print(crafted_text, title="make_llm_text")

        llm_setting_for_object = get_llm_deck().get_llm_setting(llm_setting_or_preset_id="llm_for_testing_gen_object")
        crafted_object_direct = await child_crafter.make_object_direct(
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
            object_class=Person,
            llm_setting_for_object=llm_setting_for_object,
            llm_prompt_for_object=LLMPrompt(user_text=USER_TEXT_FOR_SINGLE_PERSON),
        )
        pretty_print(crafted_object_direct, title="make_object_direct")

        crafted_object = await child_crafter.make_text_then_object(
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
            object_class=Person,
            llm_setting_main=llm_setting_for_text,
            llm_setting_for_object=llm_setting_for_object,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_SINGLE_PERSON_TEXT_THEN_OBJECT),
        )
        pretty_print(crafted_object, title="make_text_then_object")

        crafted_object_list_direct = await child_crafter.make_object_list_direct(
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
            object_class=Person,
            llm_setting_for_object_list=llm_setting_for_object,
            llm_prompt_for_object_list=LLMPrompt(user_text=USER_TEXTS_FOR_PEOPLE_STR),
        )
        pretty_print(crafted_object_list_direct, title="make_object_list_direct")

        crafted_object_list = await child_crafter.make_text_then_object_list(
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
            object_class=Person,
            llm_setting_main=llm_setting_for_text,
            llm_setting_for_object_list=llm_setting_for_object,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_MULTIPLE_PEOPLE_TEXT_THEN_OBJECT),
        )
        pretty_print(crafted_object_list, title="make_text_then_object_list")

        # TODO: fix this
        # crafted_image = await child_crafter.craft_image(
        #     job_metadata=JobMetadata(
        #         job_name=workflow.info().workflow_type,
        #     ),
        #     img_gen_prompt=ImgGenPrompt(positive_text=POSITIVE_TEXT_FOR_IMAGE),
        # )
        # pretty_print(crafted_image, title="craft_image")
        context = {
            "the_answer": "elementary, my dear Watson",
        }
        jinja2_text = await child_crafter.make_jinja2_text(
            context=context,
            jinja2="♦️♦️ {{ the_answer }} ♦️♦️",
        )
        pretty_print(jinja2_text, title="jinja2_text")

        workflow_log.debug("Workflow complete")

        extract_output = await child_crafter.make_extract_extract_pages(
            extract_input=ExtractInput(
                image_uri=PipeTestCases.IMG_EXPENSE_REPORT_1,
            ),
            extract_handle="mistral_ocr",
            job_metadata=JobMetadata(
                job_name=workflow.info().workflow_type,
            ),
        )
        pretty_print(extract_output, title="make_extract_extract_pages")
