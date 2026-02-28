from enum import StrEnum
from typing import ClassVar

from deep_flow.temporal_tasks import TaskPack
from deep_flow.tprl_content_generation.act_imgg_generate import act_imgg_gen_images
from deep_flow.tprl_content_generation.act_jinja2_generate import act_jinja2_gen_text
from deep_flow.tprl_content_generation.act_llm_generate import act_llm_gen_object, act_llm_gen_object_list, act_llm_gen_text
from deep_flow.tprl_content_generation.act_ocr_generate import act_ocr_gen_extract_pages
from deep_flow.tprl_content_generation.wf_make_images import WfMakeImages
from deep_flow.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from deep_flow.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from deep_flow.tprl_content_generation.wf_make_object import WfMakeObject, WfMakeObjectList, WfMakeTextThenObject, WfMakeTextThenObjectList
from deep_flow.tprl_content_generation.wf_make_ocr import WfMakeOcr
from deep_flow.tprl_pipe.wf_pipe_router import WfPipeRouter


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
                WfMakeOcr,
                WfMakeJinja2Text,
            ],
            activity_list=[
                act_llm_gen_object,
                act_llm_gen_text,
                act_llm_gen_object_list,
                act_imgg_gen_images,
                act_jinja2_gen_text,
                act_ocr_gen_extract_pages,
            ],
        ),
        PackName.PIPE: TaskPack(
            workflow_list=[
                WfPipeRouter,
            ],
            activity_list=[],
        ),
    }
