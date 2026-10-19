from typing import cast

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.dry_mock import (
    dry_llm_gen_object,
    dry_llm_gen_object_list,
    dry_llm_gen_text,
)
from pipelex.cogt.content_generation.object_class_resolution import resolve_object_class
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_utils import dump_prompt, dump_response_from_text_gen
from pipelex.runtime_hub import get_llm_worker


async def llm_gen_text(llm_assignment: LLMAssignment) -> str:
    authorize_assignment_reads(job_metadata=llm_assignment.job_metadata, uri_references=llm_assignment.referenced_uris())
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
    return generated_text


async def llm_gen_object(object_assignment: ObjectAssignment, *, object_class: type[BaseModel] | None = None) -> BaseModel:
    """Generate one structured object. ``object_class`` is the caller's live class when there is one.

    Omit it (the boundary case: a worker that received only the serialized assignment) to rebuild the
    class from the assignment's JSON schema instead — see :mod:`.object_class_resolution`.
    """
    llm_assignment = object_assignment.llm_assignment_for_object
    authorize_assignment_reads(job_metadata=llm_assignment.job_metadata, uri_references=object_assignment.referenced_uris())
    if object_assignment.cogt_run_params.run_mode.is_dry:
        return dry_llm_gen_object(object_assignment, object_class=object_class)
    llm_worker = get_llm_worker(llm_handle=llm_assignment.llm_handle)
    llm_job = LLMJobFactory.make_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_prompt=llm_assignment.llm_prompt,
        llm_job_params=llm_assignment.llm_job_params,
    )
    content_class = resolve_object_class(object_assignment=object_assignment, object_class=object_class)
    dump_prompt(llm_prompt=llm_job.llm_prompt)
    generated_object: BaseModel = await llm_worker.gen_object(
        llm_job=llm_job,
        schema=content_class,
    )
    dump_response_from_text_gen(response=generated_object)
    return generated_object


def make_object_list_schema(*, item_class: type[BaseModel], item_class_name: str) -> type[BaseModel]:
    """The model a list of objects is generated as, ``ListOf<item>``, whose ``items`` are the objects.

    Its title is its name from the start, not only its ``__name__``: ``instructor`` validates the model's answer with a
    subclass named after the wrapper, and a refusal of that answer is located by this class's schema only when both
    validators carry the same title (``pipelex.tools.typing.pydantic_utils.located_validation_errors``).
    """
    list_schema_name = f"ListOf{item_class_name}"

    class ListSchema(BaseModel):
        model_config = ConfigDict(title=list_schema_name)

        items: list[item_class]  # type: ignore[valid-type] # pyright: ignore[reportInvalidTypeForm]

    ListSchema.__name__ = list_schema_name
    if item_class.__doc__:
        ListSchema.__doc__ = f"List wrapper for {item_class_name}.\n\nItem description:\n{item_class.__doc__}"
    else:
        ListSchema.__doc__ = f"A list of {item_class_name}."
    return ListSchema


async def llm_gen_object_list(object_assignment: ObjectAssignment, *, object_class: type[BaseModel] | None = None) -> list[BaseModel]:
    """Generate a list of structured objects. ``object_class`` is the caller's live item class when there is one.

    Omit it (the boundary case: a worker that received only the serialized assignment) to rebuild the
    item class from the assignment's JSON schema instead — see :mod:`.object_class_resolution`.
    """
    llm_assignment = object_assignment.llm_assignment_for_object
    authorize_assignment_reads(job_metadata=llm_assignment.job_metadata, uri_references=object_assignment.referenced_uris())
    if object_assignment.cogt_run_params.run_mode.is_dry:
        return dry_llm_gen_object_list(object_assignment, object_class=object_class)
    llm_worker = get_llm_worker(llm_handle=llm_assignment.llm_handle)
    llm_job = LLMJobFactory.make_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_prompt=llm_assignment.llm_prompt,
        llm_job_params=llm_assignment.llm_job_params,
    )
    item_class_name = object_assignment.object_class_name
    item_class = resolve_object_class(object_assignment=object_assignment, object_class=object_class)
    list_schema = make_object_list_schema(item_class=item_class, item_class_name=item_class_name)

    dump_prompt(llm_prompt=llm_job.llm_prompt)
    wrapped_list = await llm_worker.gen_object(
        llm_job=llm_job,
        schema=list_schema,
    )
    dump_response_from_text_gen(response=wrapped_list)
    # The wrapper's one field, which `make_object_list_schema` declares.
    generated_list: list[BaseModel] = cast("list[BaseModel]", wrapped_list.items)  # type: ignore[attr-defined] # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    return generated_list
