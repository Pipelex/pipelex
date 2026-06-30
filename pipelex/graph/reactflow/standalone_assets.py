"""CDN-pinned GraphViewer asset references.

Generated HTML loads `@pipelex/mthds-ui` (the GraphViewer IIFE bundle + its
CSS) and `elkjs` from `cdn.jsdelivr.net` with Subresource Integrity (SRI)
hashes. Versions and `sha384` integrities are pinned here so the template
can read them through a single source of truth.

To bump a version, run `pipelex-dev refresh-graph-ui-sri`, which re-fetches
the URLs, recomputes the hashes, and rewrites this file.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CDNAsset(BaseModel):
    """A pinned CDN asset with its Subresource Integrity hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    integrity: str
    crossorigin: Literal["anonymous", "use-credentials"] = "anonymous"


MTHDS_UI_VERSION = "0.10.0"
ELKJS_VERSION = "0.11.1"

MTHDS_UI_JS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{MTHDS_UI_VERSION}/dist/standalone/graph-viewer.js",
    integrity="sha384-Q5k844+2V9geUUIi5igbfplhoa8MA20c/MtWmHJ43h83U+gTAkQTMNRDO+NvP5cP",
)

MTHDS_UI_CSS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{MTHDS_UI_VERSION}/dist/standalone/graph-viewer.css",
    integrity="sha384-+RAnunPv8/gJkU2A4kO1jjx56ZMIdtJP2FC8yoYAfXJGOZWgWHnqz9EWVAho6/HZ",
)

ELKJS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/elkjs@{ELKJS_VERSION}/lib/elk.bundled.js",
    integrity="sha384-k7OFwtsMfFyYU75zZhPkC8VRASnGrW1pxavUnozOiO2B5M5gv6PYGOkEYZTrVtvo",
)
