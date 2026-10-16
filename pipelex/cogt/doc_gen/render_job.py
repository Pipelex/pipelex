"""The contract between Pipelex and a document engine: a render job in, the file's bytes out.

A `PipeDocGen` step runs in two stages. The compose stage renders the templates and builds the layout tree,
and it is pure. The print stage hands its result to an engine, as a `RenderJob`, and stores the bytes the
engine returns. An engine is the worker of a `doc_gen` model (`DocGenWorkerAbstract`), registered through
the plugin registrar's `add_inference_backend`, and the Pipelex document generation plugin registers its own
from outside this repository, so this module and the worker are that plugin's contract with Pipelex:
everything an engine needs arrives as plain data in the job, and the one thing it reads from outside the job,
a file the document names (an image, a stylesheet), it reads through the `RenderResources` it is handed, which
applies the run's read scope and returns the file as a `LoadedResource`, its bytes with the media type its source
gives it. The job never carries a Pipelex object, so an ordinary Pipelex release does not break an
engine; changing this module is a change of the plugin contract, versioned by `PLUGIN_API_VERSION`.

A relative URL in an HTML document names a file of its template's method tree, such as the logo beside the template or
the font a stylesheet beside it names. An engine resolves it as HTML and CSS resolve one, by joining it to the URL of the
file that holds it: the job's `base_url` for the document's own URLs, and a stylesheet's URL for the URLs the stylesheet
holds. That base lies under `METHOD_FILE_URL_PREFIX`, a host no network serves, and an engine reads a URL it joined under
it through `RenderResources.load`, like any other, which finds the file in the method tree and never on a disk
(`pipelex.cogt.doc_gen.method_file_urls`).
"""

from typing import Any, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument

#: The start of every URL that names a file of a document's method tree: the job's `base_url`, and every URL an engine
#: joins to it, such as a stylesheet's and the URLs it holds. Its host is in the `.invalid` domain, which RFC 2606
#: reserves for names that never resolve, so no URL under it is ever fetched: an engine hands one to
#: `RenderResources.load`, which reads the file it names from the method tree.
METHOD_FILE_URL_PREFIX = "https://method-files.pipelex.invalid/"


class RenderJob(BaseModel):
    """Everything an engine needs to print one document, as plain data.

    Exactly one payload is set, the one the source names: `layout` for `DocGenSource.LAYOUT`, `html` for
    `DocGenSource.HTML`, and `template` with `data` for `DocGenSource.TEMPLATE_FILE`.

    `base_url` is set only for HTML, when its template belongs to a method tree: an engine joins every relative URL of
    the document to it, and reads what it joined through `RenderResources.load`. Without it, a relative URL in the
    document names no file.
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
    base_url: str | None = Field(
        default=None,
        description=(
            "The URL a relative URL of the HTML is joined to, under METHOD_FILE_URL_PREFIX: where the template sits in its "
            "method tree. None when the document has no template of a method tree"
        ),
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
        if self.base_url is not None:
            if not self.source.is_html:
                msg = f"A render job {self.source.desc} has no HTML, so it carries no base URL for its relative URLs."
                raise ValueError(msg)
            if not self.base_url.startswith(METHOD_FILE_URL_PREFIX):
                msg = f"A render job's base URL names a file of its method tree, under '{METHOD_FILE_URL_PREFIX}'."
                raise ValueError(msg)
        return self


class RenderedDocument(BaseModel):
    """What an engine returns: the file's bytes.

    The MIME type and the suffix are the format's (`DocGenFormat`), which the step's filename already ends
    in, so an engine does not restate them. A model rather than bare bytes, so the contract can grow an
    optional field without breaking an engine.
    """

    data: bytes


class LoadedResource(BaseModel):
    """What `RenderResources.load` returns: a file's bytes, and the media type its source gives it.

    `mime_type` is lowercased and without its parameters, such as `text/css`, and it is the source's word, never a
    guess, so it is `None` when the source gives none:

    - **`https://`**: the final response's `Content-Type`, after redirects; `None` when the response sends none.
    - **`data:`**: the type the URL declares.
    - **`pipelex-storage://`**: the type the storage provider has for the key. A cloud provider (S3, GCS) returns the
      content type recorded when the file was stored; the local and in-memory providers identify binary formats from
      the bytes and have none for a text format, such as a stylesheet or an SVG.
    - **A local path**, which only an unscoped run reads: `None`, since a file system records no type.
    - **A file of the method tree**, named by a URL under `METHOD_FILE_URL_PREFIX`: `None`, since a tree records none.

    A declared type is returned as declared, even a generic one such as `application/octet-stream`, and is not checked
    against the bytes. An engine that needs a type, such as an HTML engine that keeps a stylesheet only when it is
    `text/css`, falls back to its own guess from the URI or the bytes when the type is `None` or says nothing. A model
    rather than a tuple, so the contract can grow an optional field without breaking an engine.
    """

    data: bytes
    mime_type: str | None = None


class RenderResources(Protocol):
    """How an engine reads a file its document names, such as the image of an image block.

    Pipelex hands one to every render. It resolves `pipelex-storage://` keys through the run's storage
    provider, decodes `data:` URLs and fetches `https://` through the SSRF guard, and it refuses what the
    run's read scope does not allow, a local path included. A URL under `METHOD_FILE_URL_PREFIX`, which an
    engine joined to the job's `base_url` or to the URL of a stylesheet read that way, is a file of the
    document's method tree: it is resolved in the tree by the MTHDS standard's rules for a relative URL and
    read through the method file store, under the run's read scope. So is a relative URL of an HTML document
    an engine hands as written, against the job's `base_url`. Neither ever reaches a disk. It is synchronous,
    since engines are, and it may be called from the thread the engine prints in.
    """

    def load(self, *, uri: str, position: str) -> LoadedResource:
        """Return the bytes a URI points at, with the media type its source gives them (`LoadedResource`).

        Args:
            uri: The URI the document names, or, for a relative URL, the URL an engine joined it to.
            position: Where the URI sits, in words, which a refusal names instead of the URI: "image 2 of the document".

        Raises:
            UriReadRefusedError: the run's read scope does not allow the URI.
            TemplateUrlRefusedError: the URI names no file of the document's method tree: it climbs above the tree's
                root, names a file the tree does not hold, or the document has no method tree to resolve it in.
        """
        ...
