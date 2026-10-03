"""The contract between Pipelex and a document engine: a render job in, the file's bytes out.

A `PipeDocGen` step runs in two stages. The compose stage renders the templates and builds the layout tree,
and it is pure. The print stage hands its result to an engine, as a `RenderJob`, and stores the bytes the
engine returns. An engine is the worker of a `doc_gen` model (`DocGenWorkerAbstract`), registered through
the plugin registrar's `add_inference_backend`, and the Pipelex document generation plugin registers its own
from outside this repository, so this module and the worker are that plugin's contract with Pipelex:
everything an engine needs arrives as plain data in the job, and the one thing it reads from outside the job,
a file the document names (an image), it reads through the `RenderResources` it is handed, which applies the
run's read scope. The job never carries a Pipelex object, so an ordinary Pipelex release does not break an
engine; changing this module is a change of the plugin contract, versioned by `PLUGIN_API_VERSION`.
"""

from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument


class RenderJob(BaseModel):
    """Everything an engine needs to print one document, as plain data.

    Exactly one payload is set, the one the source names: `layout` for `DocGenSource.LAYOUT`, `html` for
    `DocGenSource.HTML`, and `template` with `data` for `DocGenSource.TEMPLATE_FILE`.
    """

    model_config = ConfigDict(extra="forbid", ser_json_bytes="base64", val_json_bytes="base64")

    format: DocGenFormat = Field(strict=False)
    source: DocGenSource = Field(strict=False)
    filename: str = Field(description="The file's name, suffix included, such as 'invoice-INV-2026-0142.pdf'")
    title: str = Field(description="The document's title, for a running header and the file's metadata")
    layout: LayoutDocument | None = Field(default=None, description="The auto-layout of the step's inputs")
    html: str | None = Field(default=None, description="The step's HTML template, rendered against its inputs")
    template: bytes | None = Field(default=None, description="The template file's bytes")
    template_name: str | None = Field(default=None, description="The template file as the method names it, for messages")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="The step's inputs as plain data, by input name: what a template file is filled with",
    )

    def _carries_payload_of(self, *, source: DocGenSource) -> bool:
        match source:
            case DocGenSource.LAYOUT:
                return self.layout is not None
            case DocGenSource.HTML:
                return self.html is not None
            case DocGenSource.TEMPLATE_FILE:
                return self.template is not None

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        payloads = {source: self._carries_payload_of(source=source) for source in DocGenSource}
        if not payloads[self.source]:
            msg = f"A render job {self.source.desc} carries its payload: the '{self.source}' one is missing."
            raise ValueError(msg)
        extra_payloads = [str(source) for source, is_set in payloads.items() if is_set and source != self.source]
        if extra_payloads:
            msg = f"A render job {self.source.desc} carries only its own payload, not the {', '.join(extra_payloads)} one."
            raise ValueError(msg)
        return self


class RenderedDocument(BaseModel):
    """What an engine returns: the file's bytes.

    The MIME type and the suffix are the format's (`DocGenFormat`), which the step's filename already ends
    in, so an engine does not restate them. A model rather than bare bytes, so the contract can grow an
    optional field without breaking an engine.
    """

    data: bytes


class RenderResources(Protocol):
    """How an engine reads a file its document names, such as the image of an image block.

    Pipelex hands one to every render. It resolves `pipelex-storage://` keys through the run's storage
    provider, decodes `data:` URLs and fetches `https://` through the SSRF guard, and it refuses what the
    run's read scope does not allow, a local path included. It is synchronous, since engines are, and it
    may be called from the thread the engine prints in.
    """

    def load(self, *, uri: str, position: str) -> bytes:
        """Return the bytes a URI points at.

        Args:
            uri: The URI the document names.
            position: Where the URI sits, in words, which a refusal names instead of the URI: "image 2 of the document".

        Raises:
            UriReadRefusedError: the run's read scope does not allow the URI.
        """
        ...
