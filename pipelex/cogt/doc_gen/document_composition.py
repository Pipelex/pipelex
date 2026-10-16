from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.input_shape import InputShape
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.method_file_urls import RelativeUrlBase
from pipelex.cogt.doc_gen.render_job import RenderJob
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


class ComposedTemplateFile(BaseModel):
    """A template file a step names, as its print stage reads it: a file of the step's method tree, and what to read it with.

    The compose stage runs where the step runs, in a workflow on a hosted plane, which reads no file, so it names the
    template file by its tree's digest and its tree path, and the print stage, an activity, reads it through the method
    file store. An HTML template file carries the context it renders with; an office template file carries the shapes
    of the step's inputs, which the engine's template checker reads at a dry print.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: MethodFileRef = Field(description="The template file, as a file of the step's method tree")
    name: str = Field(description="The template file as the method names it, for messages")
    pipe_ref: str = Field(description="The step naming the template file, as 'domain.pipe_code', for the findings of its check")
    render_context: TemplateRenderContext | None = Field(default=None, description="What an HTML template file is rendered with")
    input_shapes: dict[str, InputShape] = Field(
        default_factory=dict, description="The step's declared inputs by name, as the shape of their plain data, for an office template's check"
    )


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

    @property
    def template_name(self) -> str | None:
        """The template file as the method names it, when the step prints from one."""
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
            file_ref = self.template_file.file
            if self.url_base.tree_digest != file_ref.tree_digest or self.url_base.holder != file_ref.tree_path:
                msg = "A document composed from an HTML template file resolves its relative URLs against that file, in its method tree."
                raise ValueError(msg)

    def referenced_uris(self) -> list[UriReference]:
        """The files the print stage will read for the document, which it authorizes against the run's read scope first.

        The images of the layout tree. A template file is a method file, read through the method file store under the
        run's read scope, and composed HTML may name files too, but only an engine laying it out finds them, and it reads
        each through `RenderResources`, which applies the same check, and reads a relative URL from the method tree.
        """
        if self.layout is None:
            return []
        return [
            UriReference(uri=image_url, position=f"image {index} of the document '{self.filename}'")
            for index, image_url in enumerate(self.layout.image_urls(), start=1)
        ]

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
            data=self.data,
            base_url=self.url_base.base_url if self.url_base is not None else None,
        )
