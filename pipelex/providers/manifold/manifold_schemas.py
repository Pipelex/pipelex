"""The wire shapes the manifold plugin sends and reads.

Two groups, and they are owned by different sides.

**The native-route requests** (`ManifoldExtractRequest`, `ManifoldSearchRequest`) are this plugin's
half of a contract the *gateway* owns and freezes, in `src/pig/pipelex/schemas.ts`. They are written
out field by field rather than derived from the runtime's job-params models, and that is the point:
several fields of `ExtractJobParams` are deliberately absent from the contract and the gateway
**refuses** them at any value, including their own defaults. A worker that reached for
`model_dump()` would send `should_caption_images=false` and be refused; one that sent them and had
them ignored would be told a parameter was honoured when it was dropped. Building the body
explicitly is what makes the absence visible in this file rather than surprising at request time.

**The image response** is Azure's, as the gateway forwards it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ManifoldExtractInput(BaseModel):
    """Exactly one of the two is set; the gateway refuses neither-or-both."""

    document_uri: str | None = None
    image_uri: str | None = None


class ManifoldExtractParams(BaseModel):
    """The extract parameters the contract *does* carry.

    `max_nb_images` keeps the runtime's own semantics — `None` unlimited, `0` none, `N` a per-page
    cap. `render_js` and `include_raw_html` are honoured by the web-fetch provider alone, and the
    gateway refuses a non-null value on a provider that cannot honour them.
    """

    max_nb_images: int | None = None
    render_js: bool | None = None
    include_raw_html: bool | None = None


class ManifoldExtractRequest(BaseModel):
    model: str
    input: ManifoldExtractInput
    params: ManifoldExtractParams | None = None


class ManifoldSearchRequest(BaseModel):
    """Flat, and with no `depth`: the model id carries it — `linkup/standard` versus `linkup/deep`."""

    model: str
    query: str
    include_images: bool | None = None
    include_inline_citations: bool | None = None
    max_results: int | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    from_date: str | None = None
    to_date: str | None = None
    output_schema: dict[str, Any] | None = None


class ManifoldImgGenAzureGptImageDatum(BaseModel):
    """One generated image.

    `b64_json` is optional here although Azure always sends it on a successful generation, so that a
    datum arriving without one gets the error it deserves — the image was filtered, which is the
    caller's prompt to change — rather than a parse failure blamed on the model.
    """

    model_config = ConfigDict(extra="ignore")

    b64_json: str | None = None


class ManifoldImgGenAzureGptImage(BaseModel):
    """The Azure GPT Image response, as the gateway forwards it unchanged.

    `size` and `output_format` arrive as Azure wrote them and are what the runtime needs to build a
    `GeneratedImageRawDetails`; `data` carries the images themselves.
    """

    model_config = ConfigDict(extra="ignore")

    size: str = Field(description="Size of the image, as WIDTHxHEIGHT")
    output_format: str = Field(description="Output format of the image")
    data: list[ManifoldImgGenAzureGptImageDatum] = []
