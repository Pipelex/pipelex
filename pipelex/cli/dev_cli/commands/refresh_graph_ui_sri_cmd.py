"""Command to refresh CDN-pinned graph viewer SRI hashes.

Fetches `@pipelex/mthds-ui` (the standalone IIFE bundle + its CSS) and `elkjs`
from `cdn.jsdelivr.net`, computes `sha384` Subresource Integrity hashes, and
rewrites `pipelex/graph/reactflow/standalone_assets.py` to pin the new
versions.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.graph.reactflow import standalone_assets as current_pins
from pipelex.hub import get_console

_DEFAULT_OUTPUT_PATH = Path(current_pins.__file__)

# Accepts SemVer-ish version strings: 1.2.3, 1.2.3-rc.1, 1.2.3+build.5, 1.2.3-beta+exp.sha.5114f85.
# Anchored, no slashes, no whitespace — eliminates URL traversal and Python-literal-injection vectors.
_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

_MTHDS_UI_JS_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{version}/dist/standalone/graph-viewer.js"
_MTHDS_UI_CSS_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{version}/dist/standalone/graph-viewer.css"
_ELKJS_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/elkjs@{version}/lib/elk.bundled.js"

# URL templates we are willing to fetch from. Split into (prefix, suffix) around the `{version}`
# placeholder so the runtime check can match a candidate URL against the same shape we built it from.
_ALLOWED_URL_SHAPES: tuple[tuple[str, str], ...] = tuple(
    tuple(template.split("{version}", maxsplit=1))  # type: ignore[misc]
    for template in (_MTHDS_UI_JS_URL_TEMPLATE, _MTHDS_UI_CSS_URL_TEMPLATE, _ELKJS_URL_TEMPLATE)
)

_MODULE_TEMPLATE = '''\
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


MTHDS_UI_VERSION = {mthds_ui_version_literal}
ELKJS_VERSION = {elkjs_version_literal}

MTHDS_UI_JS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{{MTHDS_UI_VERSION}}/dist/standalone/graph-viewer.js",
    integrity={mthds_ui_js_integrity_literal},
)

MTHDS_UI_CSS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@{{MTHDS_UI_VERSION}}/dist/standalone/graph-viewer.css",
    integrity={mthds_ui_css_integrity_literal},
)

ELKJS = CDNAsset(
    url=f"https://cdn.jsdelivr.net/npm/elkjs@{{ELKJS_VERSION}}/lib/elk.bundled.js",
    integrity={elkjs_integrity_literal},
)
'''


def _validate_version(name: str, value: str) -> str:
    if not _VERSION_PATTERN.fullmatch(value):
        msg = f"Invalid {name} version {value!r}: expected a SemVer string like 1.2.3 or 1.2.3-rc.1"
        raise PipelexCLIError(msg)
    return value


def _validate_sri(value: str) -> str:
    """Re-validate the computed SRI string before it goes into the regenerated module.

    sha384 always produces a 48-byte digest, which base64-encodes to exactly 64 chars
    with no `=` padding — so the literal must match that exact shape, not a looser
    alphabet+padding pattern.
    """
    if not re.fullmatch(r"sha384-[A-Za-z0-9+/]{64}", value):
        msg = f"Refusing to write malformed SRI literal {value!r}"
        raise PipelexCLIError(msg)
    return value


def _fetch(url: str, timeout: float = 30.0) -> bytes:
    """Fetch the full body at `url`. Raises if the URL is not on the allowlist or the request fails."""
    if not any(url.startswith(prefix) and url.endswith(suffix) for prefix, suffix in _ALLOWED_URL_SHAPES):
        msg = f"Refusing to fetch {url}: only the jsDelivr graph viewer URLs are allowed"
        raise PipelexCLIError(msg)
    with urlopen(url, timeout=timeout) as response:  # noqa: S310  # URL is a known-good https jsDelivr origin (checked above)
        body: bytes = response.read()
    return body


def _sha384_sri(payload: bytes) -> str:
    """Return the SRI integrity string `sha384-<base64>` for the given bytes."""
    digest = hashlib.sha384(payload).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def _python_string_literal(value: str) -> str:
    """Encode `value` as a double-quoted Python string literal (matches the codebase's ruff format).

    `json.dumps` is suitable because every value we encode (SemVer versions, sha384 base64) only
    contains ASCII characters that have identical Python and JSON string-literal forms.
    """
    return json.dumps(value, ensure_ascii=True)


def _render_module_source(
    *,
    mthds_ui_version: str,
    elkjs_version: str,
    mthds_ui_js_integrity: str,
    mthds_ui_css_integrity: str,
    elkjs_integrity: str,
) -> str:
    return _MODULE_TEMPLATE.format(
        mthds_ui_version_literal=_python_string_literal(mthds_ui_version),
        elkjs_version_literal=_python_string_literal(elkjs_version),
        mthds_ui_js_integrity_literal=_python_string_literal(mthds_ui_js_integrity),
        mthds_ui_css_integrity_literal=_python_string_literal(mthds_ui_css_integrity),
        elkjs_integrity_literal=_python_string_literal(elkjs_integrity),
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
    # `is None` (not falsy) so an explicit empty-string argument fails validation rather than silently falling back to the default.
    target_mthds_ui_version = _validate_version(
        "mthds-ui",
        current_pins.MTHDS_UI_VERSION if mthds_ui_version is None else mthds_ui_version,
    )
    target_elkjs_version = _validate_version(
        "elkjs",
        current_pins.ELKJS_VERSION if elkjs_version is None else elkjs_version,
    )
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
        mthds_ui_js_integrity=_validate_sri(_sha384_sri(js_bytes)),
        mthds_ui_css_integrity=_validate_sri(_sha384_sri(css_bytes)),
        elkjs_integrity=_validate_sri(_sha384_sri(elk_bytes)),
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
