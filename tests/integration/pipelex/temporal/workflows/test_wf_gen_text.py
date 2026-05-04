# import uuid

# import pytest
# from pipelex import pretty_print
# from pipelex.cogt.content_generation.assignment_models import LLMAssignment
# from pipelex.cogt.llm.llm_prompt import LLMPrompt
# from pipelex.hub import get_llm_deck
# from pipelex.pipeline.job_metadata import JobMetadata
# from temporalio import activity
# from temporalio.client import Client as TemporalClient

# from pipelex.temporal.temporal_hub import get_task_manager
# from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
# from pipelex.temporal.tprl_content_generation.wf_make_llm_text import WfMakeLLMText

# USER_TEXT_FOR_BASE = """
# Write a detailed description of a woman's clothing in the style of a 19th-century novel.
# Keep it short: 3 sentences max
# """


# @activity.defn(name="act_llm_gen_text")
# async def act_llm_gen_text_mocked(llm_assignment: LLMAssignment) -> str:
#     return f"Mocked text from {llm_assignment.desc}"


# # silence a warning that comes from deep down in temporalio's pydantic converter
# pytestmark = pytest.mark.filterwarnings("ignore:The `parse_obj` method is deprecated", "ignore:The `dict` method is deprecated")

# TODO: fix and restore this test

# @pytest.mark.asyncio(loop_scope="class")
# class TestAsyncCogtLLMGenTextAndObject:
#     async def test_wf_make_llm_text(self, temporal_client: TemporalClient):
#         llm_setting = get_llm_deck().get_llm_setting(llm_setting_or_preset_id="llm_for_testing_gen_text")
#         llm_prompt_for_text = LLMPrompt(user_text=USER_TEXT_FOR_BASE)

#         llm_assignment = LLMAssignment(
#             job_metadata=JobMetadata(),
#             llm_setting=llm_setting,
#             llm_prompt=llm_prompt_for_text,
#         )

#         task_queue = str(uuid.uuid4())
#         workflow_id = str(uuid.uuid4())
#         async with get_task_manager().make_worker(
#             temporal_client,
#             task_queue=task_queue,
#             substitute_activities={act_llm_gen_text: act_llm_gen_text_mocked},
#         ):
#             crafted_text = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
#                 WfMakeLLMText.run,
#                 arg=llm_assignment,
#                 id=workflow_id,
#                 task_queue=task_queue,
#             )
#             pretty_print(crafted_text, title="make_llm_text")
#             assert isinstance(crafted_text, str)
#             assert crafted_text
