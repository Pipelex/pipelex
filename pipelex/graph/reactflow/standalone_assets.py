"""CDN-pinned GraphViewer asset references.

Generated HTML loads `@pipelex/mthds-ui` (the GraphViewer IIFE bundle + its
CSS) and `elkjs` from `cdn.jsdelivr.net` with Subresource Integrity (SRI)
hashes. Versions and `sha384` integrities are pinned here so the template
can read them through a single source of truth.

To bump a version, run `pipelex-dev refresh-graph-ui-sri` (Phase 5) which
re-fetches the URLs, recomputes the hashes, and updates the constants below.
"""

from pydantic import BaseModel, ConfigDict


class CDNAsset(BaseModel):
    """A pinned CDN asset with its Subresource Integrity hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    integrity: str
    crossorigin: str = "anonymous"


MTHDS_UI_VERSION = "0.6.3"
ELKJS_VERSION = "0.11.1"

MTHDS_UI_JS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{MTHDS_UI_VERSION}/dist/standalone/graph-viewer.js",
    integrity="sha384-BS9SD/K440VwYZxJCMuOi3g0FVlFz9ugiivYvkVpRDPFRo9FMc6IXQl9EM22VCSP",
)

MTHDS_UI_CSS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{MTHDS_UI_VERSION}/dist/standalone/graph-viewer.css",
    integrity="sha384-Ue1fm1guW8EQGdaqrsi+8Zm5Iq5AGkxa5+UeWw+sy8vVCSYkGez6+80+p9/oxqOn",
)

ELKJS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/elkjs@{ELKJS_VERSION}/lib/elk.bundled.js",
    integrity="sha384-k7OFwtsMfFyYU75zZhPkC8VRASnGrW1pxavUnozOiO2B5M5gv6PYGOkEYZTrVtvo",
)
