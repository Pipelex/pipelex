from typing import cast

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.dry_mock import (
    dry_llm_gen_object,
    dry_llm_gen_object_list,
    dry_llm_gen_text,
)
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_utils import dump_prompt, dump_response_from_text_gen
from pipelex.hub import get_llm_worker


async def llm_gen_text(llm_assignment: LLMAssignment) -> str:
    if llm_assignment.cogt_run_params.run_mode.is_dry:
        return dry_llm_gen_text(llm_assignment)
    llm_worker = get_llm_worker(llm_handle=llm_assignment.llm_handle)
    llm_job = LLMJobFactory.make_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_prompt=llm_assignment.llm_prompt,
        llm_job_params=llm_assignment.llm_job_params,
    )
    dump_prompt(llm_prompt=llm_job.llm_prompt)
    generated_text = await llm_worker.gen_text(llm_job=llm_job)
    dump_response_from_text_gen(response=generated_text)
    log.verbose(generated_text, title="llm_gen_text")
    return generated_text


async def llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    llm_assignment = object_assignment.llm_assignment_for_object
    if object_assignment.cogt_run_params.run_mode.is_dry:
        return dry_llm_gen_object(object_assignment)
    llm_worker = get_llm_worker(llm_handle=llm_assignment.llm_handle)
    llm_job = LLMJobFactory.make_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_prompt=llm_assignment.llm_prompt,
        llm_job_params=llm_assignment.llm_job_params,
    )
    content_class = SchemaToModelFactory.make_from_json_schema(
        schema=object_assignment.object_class_schema,
        class_name=object_assignment.object_class_name,
    )
    dump_prompt(llm_prompt=llm_job.llm_prompt)
    generated_object: BaseModel = await llm_worker.gen_object(
        llm_job=llm_job,
        schema=content_class,
    )
    dump_response_from_text_gen(response=generated_object)
    return generated_object


async def llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]:
    llm_assignment = object_assignment.llm_assignment_for_object
    if object_assignment.cogt_run_params.run_mode.is_dry:
        return dry_llm_gen_object_list(object_assignment)
    log.verbose(f"llm_gen_object_list to generate a list of '{object_assignment.object_class_name}'")
    llm_worker = get_llm_worker(llm_handle=llm_assignment.llm_handle)
    llm_job = LLMJobFactory.make_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_prompt=llm_assignment.llm_prompt,
        llm_job_params=llm_assignment.llm_job_params,
    )
    item_class_name = object_assignment.object_class_name
    item_class = SchemaToModelFactory.make_from_json_schema(
        schema=object_assignment.object_class_schema,
        class_name=item_class_name,
    )

    class ListSchema(BaseModel):
        items: list[item_class]  # type: ignore[valid-type] # pyright: ignore[reportInvalidTypeForm]

    ListSchema.__name__ = f"ListOf{item_class_name}"

    if item_class.__doc__:
        ListSchema.__doc__ = f"List wrapper for {item_class_name}.\n\nItem description:\n{item_class.__doc__}"
    else:
        ListSchema.__doc__ = f"A list of {item_class_name}."

    dump_prompt(llm_prompt=llm_job.llm_prompt)
    wrapped_list: ListSchema = await llm_worker.gen_object(
        llm_job=llm_job,
        schema=ListSchema,
    )
    dump_response_from_text_gen(response=wrapped_list)
    generated_list: list[BaseModel] = cast("list[BaseModel]", wrapped_list.items)  # pyright: ignore[reportUnknownMemberType]
    return generated_list
