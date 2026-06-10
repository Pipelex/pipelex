from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from pipelex import pretty_print
    from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
    from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
    from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol  # noqa: TC001
    from pipelex.cogt.extract.extract_input import ExtractInput
    from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
    from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
    from pipelex.cogt.llm.llm_prompt import LLMPrompt
    from pipelex.hub import get_model_deck
    from pipelex.pipe_run.pipe_run_mode import PipeRunMode
    from pipelex.pipeline.job_metadata import JobMetadata
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.test_extras.temporal_registry_test_models import Person
    from pipelex.temporal.tprl_content_generation.content_generator_in_workflow_factory import ContentGeneratorInWorkflowFactory
    from tests.integration.pipelex.temporal.test_data import PipeTestCases


USER_TEXT_FOR_BASE = """
Write a detailed description of a woman's clothing in the style of a 19th-century novel.
Keep it short: 3 sentences max
"""

USER_TEXT_FOR_SINGLE_PERSON = "name: John, age: 30, job: bank teller"
MULTIPLE_USER_TEXTS_FOR_PEOPLE = [
    "name: Bob, age: 25, job: banker",
    "name: Maria, age: 35, job: consultant",
    "name: SLartiblfastikur, age: 30, job: fizzy buzzer",
    "name: Alice, age: 40, job: developer",
    "name: Tom, age: 45, job: TV presenter",
    "name: Jerry, age: 50, job: nurse",
]
USER_TEXTS_FOR_PEOPLE_STR = "\n".join(MULTIPLE_USER_TEXTS_FOR_PEOPLE)

USER_TEXT_FOR_HAIKU = """
Write a haiku about the meaning of life
"""

POSITIVE_TEXT_FOR_IMAGE = "A group of dogs with sunglasses playing beer pong with drinks and snacks"


@workflow.defn(name="wf_test_content_generator_child")
class WfTestContentGeneratorChild:
    @workflow.run
    async def run(self, is_dry_run: bool = False):
        workflow_log.debug("Workflow start")
        content_generator: ContentGeneratorProtocol
        if is_dry_run:
            content_generator = ContentGeneratorDry()
        else:
            content_generator = ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow()

        job_metadata = JobMetadata(
            user_id="temporal-test",
            pipeline_run_id=workflow.info().workflow_id,
        )
        run_mode = PipeRunMode.DRY if is_dry_run else PipeRunMode.LIVE
        cogt_run_params = CogtRunParams(run_mode=run_mode)

        llm_setting_for_text = get_model_deck().get_llm_setting(llm_choice="$testing-text")
        crafted_text = await content_generator.make_llm_text(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            llm_setting_main=llm_setting_for_text,
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_BASE),
        )
        pretty_print(crafted_text, title="make_llm_text")

        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="$testing-structured")
        crafted_object_direct = await content_generator.make_object(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            object_class=Person,
            llm_setting_for_object=llm_setting_for_object,
            llm_prompt_for_object=LLMPrompt(user_text=USER_TEXT_FOR_SINGLE_PERSON),
        )
        pretty_print(crafted_object_direct, title="make_object")

        crafted_object_list_direct = await content_generator.make_object_list(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            object_class=Person,
            llm_setting_for_object_list=llm_setting_for_object,
            llm_prompt_for_object_list=LLMPrompt(user_text=USER_TEXTS_FOR_PEOPLE_STR),
        )
        pretty_print(crafted_object_list_direct, title="make_object_list")

        crafted_image = await content_generator.make_single_image(
            img_gen_handle="gpt-image-1-mini",
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            img_gen_prompt=ImgGenPrompt(positive_text=POSITIVE_TEXT_FOR_IMAGE),
        )
        pretty_print(crafted_image, title="make_single_image")

        context = {
            "the_answer": "elementary, my dear Watson",
        }
        jinja2_text = await content_generator.make_templated_text(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            context=context,
            template="♦️♦️ {{ the_answer }} ♦️♦️",
        )
        pretty_print(jinja2_text, title="templated_text")

        page_contents = await content_generator.make_extract_pages(
            extract_input=ExtractInput(
                image_uri=PipeTestCases.IMG_EXPENSE_REPORT_1,
            ),
            cogt_run_params=cogt_run_params,
            extract_handle="azure-document-intelligence",
            job_metadata=job_metadata,
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )
        pretty_print(page_contents, title="make_extract_pages")

        workflow_log.debug("Workflow complete")
