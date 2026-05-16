from pydantic import BaseModel
from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list, llm_gen_text
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


@activity.defn
@convert_pipelex_errors
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    log.dev("act_llm_gen_text")
    return await llm_gen_text(llm_assignment=llm_assignment)


@activity.defn
async def act_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    log.dev("act_llm_gen_object")
    return await llm_gen_object(object_assignment=object_assignment)


@activity.defn
async def act_llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]:
    log.dev("act_llm_gen_object_list")
    return await llm_gen_object_list(object_assignment=object_assignment)
