"""Run setup's check of the templates a run supplies to its `PipeDocGen` steps, before any step starts.

A `PipeDocGen` step with `template_input` fills a file one of its inputs holds, so its template is unknown when the
method loads, and `pipelex validate` can only say it will be checked later. It is known once the run's inputs arrive,
which is before any model is called: this check runs then, beside the check of the file inputs against their consumers
(`pipelex.pipeline.file_input_consumers`), whose walk of the entry pipe finds the steps. For each step certain to run,
reached through no condition and no liftable step, whose template input is a run input, it reads the file under the
run's read scope, refuses one that is not of the step's format, and hands it to the step's engine's template checker
with the shapes of the step's other inputs. An error finding refuses the run as the caller's
(`PipeDocGenTemplateInputUnfitError`), and a warning is logged with the run. A template an earlier step produces is
checked at that step's print instead, since nothing exists to check before then.
"""

from typing import Any, cast

from pipelex.cogt.content_generation.doc_gen_generate import check_office_template
from pipelex.cogt.content_generation.doc_gen_template_input import read_template_input
from pipelex.cogt.doc_gen.doc_gen_engine import get_doc_gen_inference_model
from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, TemplateInputFile, template_input_name
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipeline.file_input_consumers import FileInputConsumer, collect_file_input_consumers
from pipelex.pipeline.input_normalizer import FileInputPath, collect_file_inputs
from pipelex.runtime_hub import get_report_delegate, get_storage_provider


async def check_doc_gen_template_inputs(*, entry_pipe: PipeAbstract, working_memory: WorkingMemory, read_scope: str | None) -> None:
    """Check every template a run input supplies to a `PipeDocGen` step certain to run, against its engine's template checker.

    Args:
        entry_pipe: The pipe the run starts from. Its library must be loaded.
        working_memory: The run's inputs, prepared by run setup.
        read_scope: The run's read scope, under which each template is read.

    Raises:
        DocGenTemplateInputFormatError: a template input's file is not of its step's format.
        PipeDocGenTemplateInputUnfitError: the engine's checker found errors in a template input's file.
        UriReadRefusedError: the run's read scope does not allow a template input's URL.
    """
    file_inputs = collect_file_inputs(working_memory)
    if not file_inputs:
        return
    template_consumers = [
        consumer
        for consumers in collect_file_input_consumers(entry_pipe).values()
        for consumer in consumers
        if consumer.kind.is_doc_gen_template and not consumer.is_conditional
    ]
    for consumer in template_consumers:
        # The step the walk reached, never one looked up again by its reference.
        pipe_doc_gen = consumer.doc_gen_step
        if pipe_doc_gen is None:
            continue
        for file_input in file_inputs:
            if not consumer.covers(file_input_path=file_input.path):
                continue
            document = _document_at(working_memory=working_memory, path=file_input.path)
            if document is None:
                continue
            await _check_template_input(
                pipe_doc_gen=pipe_doc_gen, consumer=consumer, input_name=str(file_input.path[0]), document=document, read_scope=read_scope
            )


async def _check_template_input(
    *, pipe_doc_gen: PipeDocGen, consumer: FileInputConsumer, input_name: str, document: DocumentContent, read_scope: str | None
) -> None:
    """Read one template input's file and hand it to its step's engine's checker, whose findings the template file stage reports."""
    doc_gen_setting = pipe_doc_gen.resolve_engine()
    inference_model = get_doc_gen_inference_model(
        model_handle=doc_gen_setting.model,
        doc_gen_format=pipe_doc_gen.doc_gen_format,
        source=pipe_doc_gen.source,
        pipe_code=consumer.pipe_code,
    )
    # The run's input, named as its caller named it, which a refusal of the file names.
    input_file = TemplateInputFile(input_name=input_name, url=document.url, mime_type=document.mime_type, filename=document.filename)
    template = await read_template_input(
        input_file=input_file,
        doc_gen_format=pipe_doc_gen.doc_gen_format,
        pipe_code=consumer.pipe_code,
        engine=inference_model.name,
        read_scope=read_scope,
        storage_provider=get_storage_provider(),
    )
    await check_office_template(
        worker=DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model, reporting_delegate=get_report_delegate()),
        template_file=ComposedTemplateFile(
            file=input_file,
            name=template_input_name(input_name=input_name),
            pipe_ref=pipe_doc_gen.pipe_ref,
            input_shapes=pipe_doc_gen.input_shapes(),
        ),
        template=template,
        doc_gen_format=pipe_doc_gen.doc_gen_format,
        data=None,
    )


def _document_at(*, working_memory: WorkingMemory, path: FileInputPath) -> DocumentContent | None:
    """The document at a file input's path in the run's inputs, None when the path holds no document."""
    root_name, *segments = path
    stuff = working_memory.get_optional_stuff(str(root_name))
    value: Any = stuff.content if stuff is not None else None
    for segment in segments:
        if isinstance(segment, int):
            items: list[Any]
            if isinstance(value, ListContent):
                items = cast("list[Any]", value.items)  # pyright: ignore[reportUnknownMemberType]
            elif isinstance(value, list):
                items = cast("list[Any]", value)
            else:
                return None
            value = items[segment] if segment < len(items) else None
        elif isinstance(value, StructuredContent):
            value = getattr(value, segment, None)
        else:
            return None
    return value if isinstance(value, DocumentContent) else None
