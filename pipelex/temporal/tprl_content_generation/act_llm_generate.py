from pydantic import BaseModel
from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list, llm_gen_text
from pipelex.temporal.tprl.workflow_library_setup import setup_workflow_library, teardown_workflow_library


@activity.defn
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    log.dev("act_llm_gen_text")
    return await llm_gen_text(llm_assignment=llm_assignment)


@activity.defn
async def act_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    log.dev("act_llm_gen_object")
    wf_library_id: str | None = None
    if object_assignment.library_crate is not None:
        act_info = activity.info()
        wf_library_id = setup_workflow_library(
            library_crate=object_assignment.library_crate,
            workflow_id=f"{act_info.workflow_id}_act_{act_info.activity_id}",
        )
    try:
        return await llm_gen_object(object_assignment=object_assignment)
    finally:
        if wf_library_id is not None:
            teardown_workflow_library(wf_library_id=wf_library_id)


@activity.defn
async def act_llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]:
    log.dev("act_llm_gen_object_list")
    wf_library_id: str | None = None
    if object_assignment.library_crate is not None:
        act_info = activity.info()
        wf_library_id = setup_workflow_library(
            library_crate=object_assignment.library_crate,
            workflow_id=f"{act_info.workflow_id}_act_{act_info.activity_id}",
        )
    try:
        return await llm_gen_object_list(object_assignment=object_assignment)
    finally:
        if wf_library_id is not None:
            teardown_workflow_library(wf_library_id=wf_library_id)
