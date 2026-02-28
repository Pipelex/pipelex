from enum import StrEnum
from typing import ClassVar

from pipelex.deep_flow.temporal_tasks import TaskPack
from pipelex.deep_flow.tprl_content_generation.act_extract_generate import act_extract_gen_extract_pages
from pipelex.deep_flow.tprl_content_generation.act_img_gen_generate import act_img_gen_images
from pipelex.deep_flow.tprl_content_generation.act_jinja2_generate import act_jinja2_gen_text
from pipelex.deep_flow.tprl_content_generation.act_llm_generate import act_llm_gen_object, act_llm_gen_object_list, act_llm_gen_text
from pipelex.deep_flow.tprl_content_generation.wf_make_extract import WfMakeExtract
from pipelex.deep_flow.tprl_content_generation.wf_make_images import WfMakeImages
from pipelex.deep_flow.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from pipelex.deep_flow.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from pipelex.deep_flow.tprl_content_generation.wf_make_object import WfMakeObject, WfMakeObjectList, WfMakeTextThenObject, WfMakeTextThenObjectList
from pipelex.deep_flow.tprl_pipe.wf_pipe_router import WfPipeRouter


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
            ],
            activity_list=[
                act_llm_gen_object,
                act_llm_gen_text,
                act_llm_gen_object_list,
                act_img_gen_images,
                act_jinja2_gen_text,
                act_extract_gen_extract_pages,
            ],
        ),
        PackName.PIPE: TaskPack(
            workflow_list=[
                WfPipeRouter,
            ],
            activity_list=[],
        ),
    }
