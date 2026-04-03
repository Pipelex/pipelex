from typing import ClassVar

from pipelex.temporal.temporal_tasks import TaskPack
from pipelex.temporal.tprl_content_generation.act_extract_generate import act_extract_gen_extract_pages
from pipelex.temporal.tprl_content_generation.act_img_gen_generate import act_img_gen_images
from pipelex.temporal.tprl_content_generation.act_jinja2_generate import act_jinja2_gen_text
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_object, act_llm_gen_object_list, act_llm_gen_text
from pipelex.temporal.tprl_content_generation.act_render_page_views import act_render_page_views
from pipelex.temporal.tprl_content_generation.wf_make_extract import WfMakeExtract
from pipelex.temporal.tprl_content_generation.wf_make_images import WfMakeImages
from pipelex.temporal.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from pipelex.temporal.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from pipelex.temporal.tprl_content_generation.wf_make_object import WfMakeObject, WfMakeObjectList, WfMakeTextThenObject, WfMakeTextThenObjectList
from pipelex.temporal.tprl_content_generation.wf_render_page_views import WfRenderPageViews
from pipelex.temporal.tprl_pipe.act_deliver import act_deliver
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from pipelex.types import StrEnum


class PackName(StrEnum):
    CRAFTING = "crafting"
    PIPE = "pipe"


class Tasks:
    TASK_PACKS: ClassVar[dict[str, TaskPack]] = {
        PackName.CRAFTING: TaskPack(
            workflow_list=[
                WfMakeObject,
                WfMakeLLMText,
                WfMakeTextThenObject,
                WfMakeObjectList,
                WfMakeTextThenObjectList,
                WfMakeImages,
                WfMakeExtract,
                WfMakeJinja2Text,
                WfRenderPageViews,
            ],
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
                act_deliver,
            ],
        ),
    }
