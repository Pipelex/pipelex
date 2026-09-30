from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.tools.uri.uri_read_scope import UriReference


class DocumentComposition(BaseModel):
    """What a `PipeDocGen` step's compose stage produced, for its print stage to hand an engine.

    The compose stage is pure, so it can run where the pipe runs, inside a workflow; this is what crosses to
    the print stage, which reads the template file and prints. It differs from the engine's `RenderJob` by
    naming the template file by its path rather than carrying its bytes: reading a file is the print stage's IO.
    """

    model_config = ConfigDict(extra="forbid")

    format: DocGenFormat = Field(strict=False)
    source: DocGenSource = Field(strict=False)
    filename: str
    title: str
    layout: LayoutDocument | None = None
    html: str | None = None
    template_path: str | None = Field(default=None, description="The template file's resolved path, for the print stage to read")
    template_name: str | None = Field(default=None, description="The template file as the method names it")
    data: dict[str, Any] = Field(default_factory=dict)

    def _carries_payload_of(self, *, source: DocGenSource) -> bool:
        match source:
            case DocGenSource.LAYOUT:
                return self.layout is not None
            case DocGenSource.HTML:
                return self.html is not None
            case DocGenSource.TEMPLATE_FILE:
                return self.template_path is not None

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
        return self

    def referenced_uris(self) -> list[UriReference]:
        """The files the print stage will read for the document, which it authorizes against the run's read scope first.

        The images of the layout tree. Composed HTML may name files too, but only an engine laying it out finds
        them, and it reads each through `RenderResources`, which applies the same check.
        """
        if self.layout is None:
            return []
        return [
            UriReference(uri=image_url, position=f"image {index} of the document '{self.filename}'")
            for index, image_url in enumerate(self.layout.image_urls(), start=1)
        ]

    def make_render_job(self) -> RenderJob:
        """The engine's job: this composition with the template file's bytes read in, when there is one."""
        template: bytes | None = None
        if self.template_path is not None:
            template = Path(self.template_path).read_bytes()
        return RenderJob(
            format=self.format,
            source=self.source,
            filename=self.filename,
            title=self.title,
            layout=self.layout,
            html=self.html,
            template=template,
            template_name=self.template_name,
            data=self.data,
        )
