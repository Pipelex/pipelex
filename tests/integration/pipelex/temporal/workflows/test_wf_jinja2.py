# import uuid

# import pytest
# from pipelex import pretty_print
# from pipelex.cogt.content_generation.assignment_models import Jinja2Assignment
# from temporalio.client import Client as TemporalClient

# from pipelex.temporal.temporal_hub import get_task_manager
# from pipelex.temporal.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text

# TODO: fix and restore this test

# @pytest.mark.asyncio(loop_scope="class")
# class TestWfJinja2:
#     async def test_wf_jinja2_text(self, temporal_client: TemporalClient):
#         task_queue = str(uuid.uuid4())
#         workflow_id = str(uuid.uuid4())
#         input_content = {
#             # "jinja2": "The answer is: {{ the_answer }}",
#             "the_answer": "elementary, my dear Watson",
#         }
#         jinja2_assignment = Jinja2Assignment(
#             context=input_content,
#             jinja2="The answer is: {{ the_answer }}",
#         )
#         async with get_task_manager().make_worker(
#             temporal_client,
#             task_queue=task_queue,
#         ):
#             crafted_text = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
#                 WfMakeJinja2Text.run,
#                 arg=jinja2_assignment,
#                 id=workflow_id,
#                 task_queue=task_queue,
#             )
#             pretty_print(crafted_text, title="make_llm_text")
#             assert crafted_text == "The answer is: elementary, my dear Watson"
