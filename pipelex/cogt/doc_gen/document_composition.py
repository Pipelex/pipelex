from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.core.bundle_resources.bundle_resource import BundleResource
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_read_scope import UriReference


class DocumentComposition(BaseModel):
    """What a `PipeDocGen` step's compose stage produced, for its print stage to hand an engine.

    The compose stage is pure, so it can run where the pipe runs, inside a workflow; this is what crosses to
    the print stage, which reads the template file and prints. It differs from the engine's `RenderJob` by
    naming the template file rather than carrying its bytes: reading a file is the print stage's IO. A template
    file beside a bundle loaded from disk is named by its path; one submitted with a bundle loaded from content
    strings is its bundle resource, inline in a run that stays in its process and a reference to the run's storage
    in one handed to a remote orchestrator, so the bytes never ride in the composition across a workflow boundary.
    """

    model_config = ConfigDict(extra="forbid")

    format: DocGenFormat = Field(strict=False)
    source: DocGenSource = Field(strict=False)
    filename: str
    title: str
    layout: LayoutDocument | None = None
    html: str | None = None
    template_path: str | None = Field(default=None, description="The template file's resolved path, for the print stage to read")
    template_resource: BundleResource | None = Field(
        default=None, description="The template file submitted with the bundle, for the print stage to read"
    )
    template_name: str | None = Field(default=None, description="The template file as the method names it")
    data: dict[str, Any] = Field(default_factory=dict)

    def _carries_payload_of(self, *, source: DocGenSource) -> bool:
        match source:
            case DocGenSource.LAYOUT:
                return self.layout is not None
            case DocGenSource.HTML:
                return self.html is not None
            case DocGenSource.TEMPLATE_FILE:
                return self.template_path is not None or self.template_resource is not None

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
        if self.template_path is not None and self.template_resource is not None:
            msg = "A template file is read from disk or submitted with its bundle, not both."
            raise ValueError(msg)
        return self

    def referenced_uris(self) -> list[UriReference]:
        """The files the print stage will read for the document, which it authorizes against the run's read scope first.

        The images of the layout tree, and a template file submitted with the bundle and stored with the run.
        Composed HTML may name files too, but only an engine laying it out finds them, and it reads each through
        `RenderResources`, which applies the same check.
        """
        references: list[UriReference] = []
        if self.template_resource is not None and self.template_resource.uri is not None:
            references.append(UriReference(uri=self.template_resource.uri, position=f"the template file '{self.template_name}'"))
        if self.layout is not None:
            references.extend(
                UriReference(uri=image_url, position=f"image {index} of the document '{self.filename}'")
                for index, image_url in enumerate(self.layout.image_urls(), start=1)
            )
        return references

    async def make_render_job(self, *, storage_provider: StorageProviderAbstract) -> RenderJob:
        """The engine's job: this composition with the template file's bytes read in, when there is one.

        A stored template file is read through the run's storage provider; the caller authorizes the read against the
        run's read scope first, with `referenced_uris`.
        """
        template: bytes | None = None
        if self.template_path is not None:
            template = Path(self.template_path).read_bytes()
        elif self.template_resource is not None:
            template = await self.template_resource.read_bytes(storage_provider=storage_provider)
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
