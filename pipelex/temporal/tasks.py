from typing import ClassVar

from pipelex.temporal.temporal_tasks import TaskPack
from pipelex.temporal.tprl_content_generation.act_extract_generate import act_extract_gen_extract_pages
from pipelex.temporal.tprl_content_generation.act_img_gen_generate import act_img_gen_images
from pipelex.temporal.tprl_content_generation.act_jinja2_generate import act_jinja2_gen_text
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_object, act_llm_gen_object_list, act_llm_gen_text
from pipelex.temporal.tprl_content_generation.act_render_page_views import act_render_page_views
from pipelex.temporal.tprl_pipe.act_assemble_graph import act_assemble_graph
from pipelex.temporal.tprl_pipe.act_deliver import act_deliver
from pipelex.temporal.tprl_pipe.act_flush_trace_events import act_flush_trace_events
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from pipelex.types import StrEnum


class PackName(StrEnum):
    CRAFTING = "crafting"
    PIPE = "pipe"


class Tasks:
    TASK_PACKS: ClassVar[dict[str, TaskPack]] = {
        PackName.CRAFTING: TaskPack(
            workflow_list=[],
            activity_list=[
                act_llm_gen_object,
                act_llm_gen_text,
                act_llm_gen_object_list,
                act_img_gen_images,
                act_jinja2_gen_text,
                act_extract_gen_extract_pages,
                act_render_page_views,
            ],
        ),
        PackName.PIPE: TaskPack(
            workflow_list=[
                WfPipeRouter,
                WfPipeRun,
            ],
            activity_list=[
                act_assemble_graph,
                act_deliver,
                act_flush_trace_events,
            ],
        ),
    }
