"""Command to refresh CDN-pinned graph viewer SRI hashes.

Fetches `@pipelex/mthds-ui` (the standalone IIFE bundle + its CSS) and `elkjs`
from `cdn.jsdelivr.net`, computes `sha384` Subresource Integrity hashes, and
rewrites `pipelex/graph/reactflow/standalone_assets.py` to pin the new
versions.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from urllib.request import urlopen

from pipelex.graph.reactflow import standalone_assets as current_pins
from pipelex.hub import get_console

_DEFAULT_OUTPUT_PATH = Path(current_pins.__file__)

_MTHDS_UI_JS_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{version}/dist/standalone/graph-viewer.js"
_MTHDS_UI_CSS_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{version}/dist/standalone/graph-viewer.css"
_ELKJS_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/elkjs@{version}/lib/elk.bundled.js"

_MODULE_TEMPLATE = '''\
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


MTHDS_UI_VERSION = "{mthds_ui_version}"
ELKJS_VERSION = "{elkjs_version}"

MTHDS_UI_JS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{{MTHDS_UI_VERSION}}/dist/standalone/graph-viewer.js",
    integrity="{mthds_ui_js_integrity}",
)

MTHDS_UI_CSS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{{MTHDS_UI_VERSION}}/dist/standalone/graph-viewer.css",
    integrity="{mthds_ui_css_integrity}",
)

ELKJS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/elkjs@{{ELKJS_VERSION}}/lib/elk.bundled.js",
    integrity="{elkjs_integrity}",
)
'''


_ALLOWED_URL_PREFIX = "https://cdn.jsdelivr.net/npm/"


def _fetch(url: str, timeout: float = 30.0) -> bytes:
    """Fetch the full body at `url`. Raises if the request fails."""
    if not url.startswith(_ALLOWED_URL_PREFIX):
        msg = f"Refusing to fetch {url}: only {_ALLOWED_URL_PREFIX}... is allowed"
        raise ValueError(msg)
    with urlopen(url, timeout=timeout) as response:  # noqa: S310  # URL is a known-good https jsDelivr origin (checked above)
        body: bytes = response.read()
    return body


def _sha384_sri(payload: bytes) -> str:
    """Return the SRI integrity string `sha384-<base64>` for the given bytes."""
    digest = hashlib.sha384(payload).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def _render_module_source(
    *,
    mthds_ui_version: str,
    elkjs_version: str,
    mthds_ui_js_integrity: str,
    mthds_ui_css_integrity: str,
    elkjs_integrity: str,
) -> str:
    return _MODULE_TEMPLATE.format(
        mthds_ui_version=mthds_ui_version,
        elkjs_version=elkjs_version,
        mthds_ui_js_integrity=mthds_ui_js_integrity,
        mthds_ui_css_integrity=mthds_ui_css_integrity,
        elkjs_integrity=elkjs_integrity,
    )


def refresh_graph_ui_sri_cmd(
    mthds_ui_version: str | None = None,
    elkjs_version: str | None = None,
    output_path: Path | None = None,
    quiet: bool = False,
) -> None:
    """Refetch the pinned graph viewer assets and rewrite `standalone_assets.py`.

    Args:
        mthds_ui_version: Target `@pipelex/mthds-ui` version. Defaults to the currently pinned version.
        elkjs_version: Target `elkjs` version. Defaults to the currently pinned version.
        output_path: Override the module path to rewrite (used by tests).
        quiet: Suppress all output except a single status line.
    """
    target_mthds_ui_version = mthds_ui_version or current_pins.MTHDS_UI_VERSION
    target_elkjs_version = elkjs_version or current_pins.ELKJS_VERSION
    target_path = output_path or _DEFAULT_OUTPUT_PATH

    console = get_console()

    urls = {
        "mthds-ui js": _MTHDS_UI_JS_URL_TEMPLATE.format(version=target_mthds_ui_version),
        "mthds-ui css": _MTHDS_UI_CSS_URL_TEMPLATE.format(version=target_mthds_ui_version),
        "elkjs": _ELKJS_URL_TEMPLATE.format(version=target_elkjs_version),
    }

    if not quiet:
        console.print()
        console.print("[bold]Refreshing graph viewer CDN pins...[/bold]")
        for label, url in urls.items():
            console.print(f"  {label}: {url}")
        console.print()

    js_bytes = _fetch(urls["mthds-ui js"])
    css_bytes = _fetch(urls["mthds-ui css"])
    elk_bytes = _fetch(urls["elkjs"])

    source = _render_module_source(
        mthds_ui_version=target_mthds_ui_version,
        elkjs_version=target_elkjs_version,
        mthds_ui_js_integrity=_sha384_sri(js_bytes),
        mthds_ui_css_integrity=_sha384_sri(css_bytes),
        elkjs_integrity=_sha384_sri(elk_bytes),
    )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(source, encoding="utf-8")

    if quiet:
        console.print(f"[green]✓ graph viewer SRI refreshed:[/green] mthds-ui={target_mthds_ui_version}, elkjs={target_elkjs_version}")
    else:
        console.print(f"[green]✓ wrote {target_path}[/green]")
        console.print(f"  MTHDS_UI_VERSION = {target_mthds_ui_version}")
        console.print(f"  ELKJS_VERSION    = {target_elkjs_version}")
        console.print()
