from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.input_shape import InputShape
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.method_file_urls import RelativeUrlBase
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.cogt.doc_gen.sheet_range import SheetRangeFill
from pipelex.cogt.doc_gen.table_fill import CellPolicy, TableFill, sheet_range_refusal, table_match_refusal
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from pipelex.tools.uri.uri_read_scope import UriReference


class TemplateRenderContext(BaseModel):
    """What the print stage renders a step's HTML template file with: the step's data, and the concepts that type it.

    The data is the stuffs the step's inputs name, the only ones its template may read, as they travel between processes.
    The concepts are those of the run's library crate, with its domains and none of its pipes, which travel beside the
    data as plain JSON, so the print stage can type the data again wherever it runs and render the template with the
    whole stack of a `PipeCompose` HTML template, its filters included. The print stage renders in the run's own library
    when its process holds it, which `crate_fingerprint` names, such as in a local run, so the data keeps the classes the
    run built it with; anywhere else it types the data with the concepts alone, in a library it keeps for later prints.
    The composition crosses into the print activity's payload, so it carries neither the run's pipes nor the data the
    step does not read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    crate_fingerprint: str = Field(description="The fingerprint of the run's library crate, by which a process holding it renders in it")
    concepts_crate: dict[str, Any] = Field(
        description="The concepts and domains of the run's library crate, with none of its pipes, as JSON, which type the step's data"
    )
    working_memory_raw: dict[str, Any] = Field(description="The stuffs the step's inputs name, as a working memory dumped for transport")
    runtime_params: dict[str, Any] = Field(default_factory=dict, description="The run's runtime parameters, which a template may read")


class TemplateInputFile(BaseModel):
    """A template file a run supplies as one of the step's inputs: the input's name, and the document it holds.

    The compose stage reads no file, so it names the document by the URL its `DocumentContent` holds, with the media
    type and the file name it carries, and the print stage reads it under the run's read scope as it reads any file the
    run names. The file's name is never quoted in a message: an input is named by its name alone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_name: str = Field(description="The step's input whose document is the template file")
    url: str = Field(description="The document's URL, as its `DocumentContent` holds it")
    mime_type: str | None = Field(default=None, description="The media type the document carries, if any")
    filename: str | None = Field(default=None, description="The document's file name, if any, which the output's name defaults to")


class ComposedTemplateFile(BaseModel):
    """A template file a step prints from, as its print stage reads it: where the file is, and what to read it with.

    The file is one of the step's method tree, named by its tree's digest and its tree path and read through the method
    file store, or one the run supplies as one of the step's inputs (`TemplateInputFile`), read from the URL its document
    holds. The compose stage runs where the step runs, in a workflow on a hosted plane, which reads no file, so it only
    names the file, and the print stage, an activity, reads it. An HTML template file carries the context it renders
    with, and is always the method's; an office template file carries the shapes of the step's inputs, which the
    engine's template checker reads.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: MethodFileRef | TemplateInputFile = Field(description="The template file: a file of the step's method tree, or a run input's document")
    name: str = Field(
        description="The template file as the method names it, such as 'invoice.xlsx', or the input supplying it, as \"the input 'workbook'\""
    )
    pipe_ref: str = Field(description="The step naming the template file, as 'domain.pipe_code', for the findings of its check")
    render_context: TemplateRenderContext | None = Field(default=None, description="What an HTML template file is rendered with")
    input_shapes: dict[str, InputShape] = Field(
        default_factory=dict, description="The step's declared inputs by name, as the shape of their plain data, for an office template's check"
    )

    @model_validator(mode="after")
    def validate_input_template(self) -> Self:
        """A run input supplies an office template only: an HTML template is the method's own text."""
        if isinstance(self.file, TemplateInputFile) and self.render_context is not None:
            msg = "A template file a run input supplies is an office file, never an HTML template rendered before it prints."
            raise ValueError(msg)
        return self

    @property
    def method_file(self) -> MethodFileRef | None:
        """The file of the step's method tree, when the template is the method's."""
        return self.file if isinstance(self.file, MethodFileRef) else None

    @property
    def input_file(self) -> TemplateInputFile | None:
        """The run input's document, when a run input supplies the template."""
        return self.file if isinstance(self.file, TemplateInputFile) else None

    @property
    def desc(self) -> str:
        """How a message names the template: "the template file 'invoice.xlsx'", or "the template the input 'workbook' supplies"."""
        if self.input_file is not None:
            return f"the template the input '{self.input_file.input_name}' supplies"
        return f"the template file '{self.name}'"


def template_input_name(*, input_name: str) -> str:
    """How a template a run input supplies is named in a job and in messages: `the input 'workbook'`, never by its file's name."""
    return f"the input '{input_name}'"


class DocumentComposition(BaseModel):
    """What a `PipeDocGen` step's compose stage produced, for its print stage to hand an engine.

    The compose stage is pure, so it can run where the pipe runs, inside a workflow; this is what crosses to the print
    stage, which reads the template file, renders it when it is an HTML template, and prints. It differs from the
    engine's `RenderJob` by naming the template file rather than carrying its bytes: reading a method file is the print
    stage's IO, through the method file store, so the bytes never ride in the composition across a workflow boundary.
    An inline HTML template, whose text is the bundle's own, is rendered by the compose stage and travels as `html`.

    An HTML document's relative URLs, such as an image beside the template, name files of the template's method tree:
    `url_base` says where the template sits there, the template file or the bundle of an inline template, and the print
    stage hands the engine its base URL and reads each file the engine asks for from the tree. It is None for a document
    whose template belongs to no method tree, whose relative URLs then name no file, and for a document with no HTML.
    """

    model_config = ConfigDict(extra="forbid")

    format: DocGenFormat = Field(strict=False)
    source: DocGenSource = Field(strict=False)
    filename: str
    title: str
    layout: LayoutDocument | None = None
    html: str | None = None
    template_file: ComposedTemplateFile | None = Field(default=None, description="The template file the print stage reads, renders and prints")
    data: dict[str, Any] = Field(default_factory=dict)
    url_base: RelativeUrlBase | None = Field(
        default=None, description="Where the HTML template sits in its method tree, which every relative URL of the document resolves against"
    )
    table_fill: TableFill = Field(default=TableFill.REPLACE, strict=False, description="How the template file's Tables are filled")
    match_on: list[str] | None = Field(default=None, description="Under `update`, the fields of the records whose columns are the Table's key")
    match_row: str | None = Field(default=None, description="Under `update`, the field of the records holding the row's position")
    cells: CellPolicy | None = Field(default=None, strict=False, description="Under `update`, which cells of a matched row may be written")
    sheet_range: SheetRangeFill | None = Field(default=None, description="Under `append` or `update`, the range on a sheet one list fills")

    @property
    def template_name(self) -> str | None:
        """The template file as the method names it, or the input supplying it, when the step prints from one."""
        return self.template_file.name if self.template_file is not None else None

    @property
    def renders_html_template_file(self) -> bool:
        """Whether the print stage renders an HTML template file before it prints."""
        return self.template_file is not None and self.template_file.render_context is not None

    def _carries_payload_of(self, *, source: DocGenSource) -> bool:
        match source:
            case DocGenSource.LAYOUT:
                return self.layout is not None
            case DocGenSource.HTML:
                return self.html is not None or self.renders_html_template_file
            case DocGenSource.TEMPLATE_FILE:
                return self.template_file is not None and self.template_file.render_context is None

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Exactly the payload its source names, as its `RenderJob` will need, so a wrong composition fails here and not at print."""
        payloads = {source: self._carries_payload_of(source=source) for source in DocGenSource}
        if not payloads[self.source]:
            msg = f"A document composed {self.source.desc} carries its payload."
            raise ValueError(msg)
        extra_payloads = [str(source) for source, is_set in payloads.items() if is_set and source != self.source]
        if extra_payloads:
            msg = f"A document composed {self.source.desc} carries only its own payload, not the {', '.join(extra_payloads)} one."
            raise ValueError(msg)
        if self.html is not None and self.template_file is not None:
            msg = "A document composed from HTML carries its rendered HTML or the template file the print stage renders, not both."
            raise ValueError(msg)
        if not self.table_fill.is_replace and not self.source.fills_template_file:
            msg = f"A document composed {self.source.desc} fills no Table of a template file, so it cannot {self.table_fill.desc}."
            raise ValueError(msg)
        match_refusal = table_match_refusal(table_fill=self.table_fill, match_on=self.match_on, match_row=self.match_row, cells=self.cells)
        if match_refusal is not None:
            msg = f"A document composed this way cannot match its records to rows: {match_refusal}."
            raise ValueError(msg)
        range_refusal = sheet_range_refusal(table_fill=self.table_fill, sheet_range=self.sheet_range)
        if range_refusal is not None:
            msg = f"A document composed this way cannot fill a range on a sheet: {range_refusal}."
            raise ValueError(msg)
        self._validate_url_base()
        return self

    def _validate_url_base(self) -> None:
        """A base for relative URLs only for HTML, and for an HTML template file, the template file's own place in its tree."""
        if self.url_base is None:
            return
        if not self.source.is_html:
            msg = f"A document composed {self.source.desc} has no HTML, so it carries no base for relative URLs."
            raise ValueError(msg)
        if self.template_file is not None:
            file_ref = self.template_file.method_file
            if file_ref is None:
                msg = "A document composed from an HTML template file prints the method's own file, never one a run input supplies."
                raise ValueError(msg)
            if self.url_base.tree_digest != file_ref.tree_digest or self.url_base.holder != file_ref.tree_path:
                msg = "A document composed from an HTML template file resolves its relative URLs against that file, in its method tree."
                raise ValueError(msg)

    def referenced_uris(self) -> list[UriReference]:
        """The files the print stage will read for the document, which it authorizes against the run's read scope first.

        The images of the layout tree, and the document of a run input that supplies the template file. A template file
        of the method is read through the method file store under the run's read scope, and composed HTML may name files
        too, but only an engine laying it out finds them, and it reads each through `RenderResources`, which applies the
        same check, and reads a relative URL from the method tree.
        """
        uri_references: list[UriReference] = []
        if self.template_file is not None and (input_file := self.template_file.input_file) is not None:
            uri_references.append(UriReference(uri=input_file.url, position=f"the template the input '{input_file.input_name}' supplies"))
        if self.layout is not None:
            uri_references.extend(
                UriReference(uri=image_url, position=f"image {index} of the document '{self.filename}'")
                for index, image_url in enumerate(self.layout.image_urls(), start=1)
            )
        return uri_references

    def make_render_job(self, *, html: str | None = None, template: bytes | None = None) -> RenderJob:
        """The engine's job: this composition with what the print stage read and rendered.

        Args:
            html: The HTML template file, rendered with the step's data, when the step prints from one.
            template: The office template file's bytes, when the step prints from one.
        """
        return RenderJob(
            format=self.format,
            source=self.source,
            filename=self.filename,
            title=self.title,
            layout=self.layout,
            html=html if html is not None else self.html,
            template=template,
            template_name=self.template_name,
            table_fill=self.table_fill,
            match_on=self.match_on,
            match_row=self.match_row,
            cells=self.cells,
            sheet_range=self.sheet_range,
            data=self.data,
            base_url=self.url_base.base_url if self.url_base is not None else None,
        )
