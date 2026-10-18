"""The redirect stubs that make a Pipelex code's type URI reach its page on docs.pipelex.com.

A code's type URI is the registry's base URL, a slash, then the whole code:
``https://docs.pipelex.com/errors/pipelex.billing.plan_limit``. The documentation itself is versioned,
and serves the code's page at ``/<version>/errors/pipelex/billing/plan_limit/``, with ``/latest/`` the
released version. The site is served by GitHub Pages from its ``gh-pages`` branch, with no server-side
redirect of our own, so the documentation's deployment writes, at the root of the published site, one
directory per code named after the whole code, holding an ``index.html`` that redirects to the code's
``/latest/`` page. GitHub Pages answers a URL naming a directory without its trailing slash, as the type
URI does, with a 301 to the same URL with the slash, whatever its last segment holds (``/0.87.0`` is
answered so too), and serves the directory's ``index.html`` there. The stubs are written from the pages the
released version holds, so a code resolves once a release that documents it is the latest, and a stub whose
code the latest version no longer documents is removed. The base URL itself gets a root stub, redirecting to
the codes' index under ``/latest/``, only while the latest version documents at least one code; otherwise a
root stub written earlier is removed, and only a file carrying the stubs' marker is ever removed.
"""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError

if TYPE_CHECKING:
    from pathlib import Path

# The version directory of the published site that the type URIs resolve to.
LATEST_DIR_NAME = "latest"
# The comment every stub carries, so that only a stub this module wrote is ever removed.
STUB_MARKER = "<!-- pipelex-dev write-error-type-redirects: the type URI of an error code -->"
# How a report names the root stub, the base URL's own, which serves no code.
ROOT_STUB_NAME = "(index)"

_SEGMENT = r"[a-z][a-z0-9_]*"
_CODE_DIR_REGEX = re.compile(rf"^{_SEGMENT}(\.{_SEGMENT})+$")


class TypeRedirectsReport(BaseModel):
    """What a run of :func:`write_type_redirects` did, by the code each stub serves."""

    model_config = ConfigDict(frozen=True)

    written: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


def render_stub(*, target_path: str, site_origin: str) -> str:
    """A page that sends its reader to ``target_path``, keeping the URL's fragment, as the documentation's other redirects do."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"{STUB_MARKER}\n"
        '<meta charset="utf-8">\n'
        "<title>Redirecting...</title>\n"
        f'<link rel="canonical" href="{site_origin}{target_path}">\n'
        '<meta name="robots" content="noindex">\n'
        f'<script>var anchor=window.location.hash.substr(1);location.href="{target_path}"+(anchor?"#"+anchor:"")</script>\n'
        f'<meta http-equiv="refresh" content="0; url={target_path}">\n'
        "</head>\n"
        "<body>\n"
        f'Redirecting to <a href="{target_path}">{target_path}</a>...\n'
        "</body>\n"
        "</html>\n"
    )


def _documented_codes(*, pages_dir: Path) -> list[str]:
    """Every code whose page the published version holds: ``<prefix>/<family>/<name>/index.html`` is ``<prefix>.<family>.<name>``."""
    codes: list[str] = []
    for index_file in sorted(pages_dir.glob("*/*/*/index.html")):
        segments = index_file.parent.relative_to(pages_dir).parts
        code = ".".join(segments)
        if _CODE_DIR_REGEX.match(code):
            codes.append(code)
    return codes


def write_type_redirects(*, site_root: Path, base_url: str) -> TypeRedirectsReport:
    """Write, under the published site's root, the stub of every code the latest version documents, and remove stale stubs.

    Args:
        site_root: The root of the published site, a checkout of its ``gh-pages`` branch.
        base_url: The registry's base URL, whose path is where the stubs go and whose origin their canonical links name.

    Raises:
        ErrorRegistryError: When the site has no latest version, or the base URL lies elsewhere than the site's root.
    """
    url = urlsplit(base_url)
    stubs_path = url.path.strip("/")
    if not stubs_path:
        msg = f"the base URL {base_url} has no path, so the type URIs would overwrite the site's root"
        raise ErrorRegistryError(msg)
    site_origin = f"{url.scheme}://{url.netloc}"
    pages_dir = site_root / LATEST_DIR_NAME / stubs_path
    if not (site_root / LATEST_DIR_NAME).is_dir():
        msg = f"{site_root} holds no '{LATEST_DIR_NAME}' version, so no type URI can resolve"
        raise ErrorRegistryError(msg)
    stubs_dir = site_root / stubs_path
    codes = _documented_codes(pages_dir=pages_dir) if pages_dir.is_dir() else []

    written: list[str] = []
    unchanged: list[str] = []
    removed: list[str] = []
    targets = {code: f"/{LATEST_DIR_NAME}/{stubs_path}/{code.replace('.', '/')}/" for code in codes}
    # The root stub sends the base URL to the codes' index under /latest/, which only a version that documents
    # the codes holds: before such a release is the latest, /latest/errors/ is not that index, and may be no
    # page at all, so no root stub is written, and the site's 404 page sends the base URL to /latest/ as it
    # sends any path without a version.
    if codes:
        targets[""] = f"/{LATEST_DIR_NAME}/{stubs_path}/"
    for code, target_path in targets.items():
        stub_file = stubs_dir / code / "index.html" if code else stubs_dir / "index.html"
        content = render_stub(target_path=target_path, site_origin=site_origin)
        if stub_file.is_file() and stub_file.read_text(encoding="utf-8") == content:
            unchanged.append(code or ROOT_STUB_NAME)
            continue
        stub_file.parent.mkdir(parents=True, exist_ok=True)
        stub_file.write_text(content, encoding="utf-8", newline="\n")
        written.append(code or ROOT_STUB_NAME)

    if stubs_dir.is_dir():
        for stub_dir in sorted(stubs_dir.iterdir()):
            if not stub_dir.is_dir() or stub_dir.name in targets or not _CODE_DIR_REGEX.match(stub_dir.name):
                continue
            stub_file = stub_dir / "index.html"
            if _is_stub(stub_file=stub_file):
                shutil.rmtree(stub_dir)
                removed.append(stub_dir.name)
        root_stub_file = stubs_dir / "index.html"
        if "" not in targets and _is_stub(stub_file=root_stub_file):
            root_stub_file.unlink()
            removed.append(ROOT_STUB_NAME)
    return TypeRedirectsReport(written=written, unchanged=unchanged, removed=removed)


def _is_stub(*, stub_file: Path) -> bool:
    """Whether a file is a stub this module wrote, which alone it may remove: a file carrying the stub's marker."""
    return stub_file.is_file() and STUB_MARKER in stub_file.read_text(encoding="utf-8")
