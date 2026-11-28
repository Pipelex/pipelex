"""Name the files an operator produces from its `output_filename` (spec: mthds-format.md, "Naming Produced Files").

Once an operator whose blueprint states `output_filename` has produced its output, the template is rendered once with the
pipe's inputs, and each `Image` or `Document` of the output takes the name built from it as its `filename`, the name a
download reads: a plural output's second and later items take ` (2)`, ` (3)` and so on. The name never decides where a
file is stored, so the stored file and its URL are left as they were.

The inputs are the ones the step was given: the operator takes the naming context before it runs
(`prepare_naming_context`), so an output it writes under an input's name never stands in for that input, and the stored
values the template reads are loaded first, through the content generator's leaf, as every step rendering where it runs
loads them. Naming a file never fails a run: a template that fails to render, or reaches a value it cannot read, or
renders nothing usable, leaves each file the name the runtime gave it, with a warning.
"""

from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.exceptions import StoredValueNotLoadedError, StoredValueUnreadableError
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.kernel.compose_ops import build_compose_context
from pipelex.kernel.stored_value_ops import load_stored_values_read_from_memory
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import (
    Jinja2ContextError,
    Jinja2DetectVariablesError,
    Jinja2StuffError,
    Jinja2TemplateBudgetError,
    Jinja2TemplateRenderError,
    Jinja2TemplateSecurityError,
    Jinja2TemplateSyntaxError,
)
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.jinja2_required_variables import parse_jinja2_read_paths
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.filetype_utils import UNKNOWN_FILE_TYPE, mime_type_to_extension
from pipelex.tools.misc.produced_file_name import build_produced_file_name
from pipelex.tools.uri.exceptions import UriReadRefusedError

FileContent = ImageContent | DocumentContent


def runtime_file_name(*, content: FileContent, pipe_code: str) -> str:
    """The name the runtime gives a produced file without a template: its own `filename`, else its URL's last segment
    when that has an extension, else the pipe's code with the extension of its media type.
    """
    if content.filename:
        return PurePosixPath(content.filename).name
    parsed = urlparse(content.url)
    if parsed.scheme != "data":
        last_segment = PurePosixPath(parsed.path).name
        if PurePosixPath(last_segment).suffix:
            return last_segment
    if content.mime_type:
        extension = mime_type_to_extension(content.mime_type)
        if extension != UNKNOWN_FILE_TYPE:
            return f"{pipe_code}.{extension}"
    return pipe_code


def input_naming_context(*, memory: WorkingMemory) -> dict[str, Any]:
    """The context `output_filename` renders with: the step's inputs as they are in `memory` now.

    Each value is held by its stuff, so an output the step writes into `memory` afterwards, under an input's name
    included, leaves the context as it was.
    """
    return build_compose_context(memory=memory)


async def prepare_naming_context(
    *, output_filename: str, working_memory: WorkingMemory, job_metadata: JobMetadata, pipe_run_params: PipeRunParams, pipe_code: str
) -> dict[str, Any]:
    """Load the stored values `output_filename` reads, then take the naming context, before the step writes its output.

    A stored value that cannot be loaded is left unloaded, with a warning: the template reaching it then fails to render,
    and the file keeps the runtime's name.
    """
    read_paths: frozenset[str]
    try:
        read_paths = parse_jinja2_read_paths(template_category=TemplateCategory.BASIC, template_source=output_filename)
    except Jinja2DetectVariablesError:
        # The render refuses the template, and the file keeps the runtime's name.
        read_paths = frozenset[str]()
    if read_paths:
        try:
            await load_stored_values_read_from_memory(
                memory=working_memory, read_paths=read_paths, job_metadata=job_metadata, cogt_run_params=pipe_run_params.cogt_run_params
            )
        except (UriReadRefusedError, StoredValueUnreadableError) as exc:
            log.warning(
                "A stored input a file name reads could not be loaded",
                fields={"pipe_code": pipe_code, **error_fields(exc=exc)},
            )
    return input_naming_context(memory=working_memory)


async def render_output_filename(*, output_filename: str, naming_context: dict[str, Any], pipe_code: str) -> str | None:
    """The template rendered with the pipe's inputs, or `None`, with a warning, when it fails to render.

    Plain Jinja2, as the standard writes it: the `$` and `@` shorthands are not expanded, so a name may hold either. Every
    way the render can fail is caught, since naming a file never fails a run: the template's own faults, a filter or a
    method refusing this run's value, a refusal of the sandbox, a render past its budget and a stored value never loaded.
    """
    try:
        return await render_jinja2_async(
            output_filename,
            template_category=TemplateCategory.BASIC,
            templating_context=naming_context,
            is_undefined_strict=True,
            template_owner=TemplateOwner.METHOD,
        )
    except (
        Jinja2TemplateSyntaxError,
        Jinja2TemplateRenderError,
        Jinja2StuffError,
        Jinja2ContextError,
        Jinja2TemplateBudgetError,
        Jinja2TemplateSecurityError,
        StoredValueNotLoadedError,
    ) as exc:
        log.warning("A file name template failed to render, so the file keeps its own name", fields={"pipe_code": pipe_code, **error_fields(exc=exc)})
        return None


def _named(*, content: StuffContent, rendered: str | None, pipe_code: str, item_number: int) -> StuffContent:
    if not isinstance(content, (ImageContent, DocumentContent)):
        return content
    name = build_produced_file_name(rendered=rendered, default_name=runtime_file_name(content=content, pipe_code=pipe_code), item_number=item_number)
    # A copy: an operator may hand an input's own file on as its output, and renaming it in place would rename the input.
    return content.model_copy(update={"filename": name})


async def name_produced_files(*, output_filename: str, main_stuff: Stuff, naming_context: dict[str, Any], pipe_code: str) -> None:
    """Give each file of `main_stuff` the name `output_filename` builds, rendered with the inputs in `naming_context`."""
    content = main_stuff.content
    if isinstance(content, ListContent):
        items: list[StuffContent] = list(content.items)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        if not any(isinstance(item, (ImageContent, DocumentContent)) for item in items):
            return
        rendered = await render_output_filename(output_filename=output_filename, naming_context=naming_context, pipe_code=pipe_code)
        file_number = 0
        named_items: list[StuffContent] = []
        for item in items:
            if isinstance(item, (ImageContent, DocumentContent)):
                file_number += 1
            named_items.append(_named(content=item, rendered=rendered, pipe_code=pipe_code, item_number=file_number))
        main_stuff.content = content.model_copy(update={"items": named_items})
        return
    if not isinstance(content, (ImageContent, DocumentContent)):
        return
    rendered = await render_output_filename(output_filename=output_filename, naming_context=naming_context, pipe_code=pipe_code)
    main_stuff.content = _named(content=content, rendered=rendered, pipe_code=pipe_code, item_number=1)
