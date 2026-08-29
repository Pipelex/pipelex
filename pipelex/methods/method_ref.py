"""The method reference grammar: `<address>[@<tag>]`.

A method reference names a package hosted on a public git forge. The address is
`github.com/<owner>/<repo>[/<selector>]` (MVP scope: `github.com` only). A bare address
means the repository's default branch at HEAD; `@<tag>` pins the repository at that git
tag (recommended form `vX.Y.Z`). Full browser URLs (`https://github.com/...`) are accepted
and normalized into the address form, including `/tree/<branch>/...` deep links whose
branch segment is discarded.

This module is the single place the CLI, the API, and the tests parse that grammar.
"""

import re

from mthds.package.vcs_resolver import address_to_clone_url
from pydantic import BaseModel, ConfigDict

from pipelex.methods.exceptions import MethodRefParseError

GITHUB_HOST = "github.com"

_URL_PREFIXES = (f"https://{GITHUB_HOST}/", f"http://{GITHUB_HOST}/")
_ADDRESS_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class MethodRef(BaseModel):
    """A parsed method reference.

    `address` is the normalized address (no scheme, no `.git` suffix, no tag):
    `github.com/<owner>/<repo>[/<selector>]`. `tag` is the optional git tag from `@<tag>`.
    """

    model_config = ConfigDict(frozen=True)

    address: str
    tag: str | None = None

    @property
    def owner(self) -> str:
        return self.address.split("/")[1]

    @property
    def repo(self) -> str:
        return self.address.split("/")[2]

    @property
    def selector(self) -> str | None:
        """The package selector within the repository (everything after owner/repo), if any."""
        parts = self.address.split("/")
        return "/".join(parts[3:]) or None

    @property
    def repo_address(self) -> str:
        """The repository address alone: `github.com/<owner>/<repo>`."""
        return "/".join(self.address.split("/")[:3])

    @property
    def clone_url(self) -> str:
        """The HTTPS clone URL derived from the repository address."""
        return address_to_clone_url(self.repo_address)

    @property
    def ref_str(self) -> str:
        """The canonical string form of this reference: `<address>[@<tag>]`."""
        if self.tag:
            return f"{self.address}@{self.tag}"
        return self.address


def looks_like_method_ref(target: str) -> bool:
    """Return True if *target* looks like a method reference (bare address or GitHub URL).

    This is the dispatch test only — a True result still needs :func:`parse_method_ref`
    to validate the structure. Bare `github.com/...` addresses count, so they no longer
    fall through to local-path resolution.
    """
    return target.startswith((f"{GITHUB_HOST}/", *_URL_PREFIXES))


def parse_method_ref(ref: str) -> MethodRef:
    """Parse a method reference string into a :class:`MethodRef`.

    Accepts the bare address form (`github.com/owner/repo[/selector][@tag]`) and full
    GitHub URLs (`https://github.com/owner/repo[...]`, with an optional trailing `.git`
    or a `/tree/<branch>/...` deep link whose branch segment is discarded).

    Args:
        ref: The reference string to parse.

    Returns:
        The parsed, normalized method reference.

    Raises:
        MethodRefParseError: If the reference does not match the grammar.
    """
    raw = ref.strip()
    if not raw:
        msg = "Empty method reference. Expected '<address>[@<tag>]', e.g. 'github.com/Pipelex/methods/documents@v0.1.0'."
        raise MethodRefParseError(msg)

    body = raw
    tag: str | None = None
    if "@" in raw:
        body, tag_part = raw.rsplit("@", 1)
        if not tag_part or not _TAG_PATTERN.match(tag_part):
            msg = f"Invalid tag '{tag_part}' in method reference '{raw}'. A tag must be a git tag name, e.g. 'v0.1.0'."
            raise MethodRefParseError(msg)
        tag = tag_part

    for prefix in _URL_PREFIXES:
        if body.startswith(prefix):
            body = f"{GITHUB_HOST}/{body[len(prefix) :]}"
            break

    body = body.rstrip("/").removesuffix(".git")

    if not body.startswith(f"{GITHUB_HOST}/"):
        msg = f"Unsupported method address '{raw}': only '{GITHUB_HOST}/...' addresses are supported."
        raise MethodRefParseError(msg)

    parts = body.split("/")

    # Browser deep links: github.com/<owner>/<repo>/tree/<branch>/<path> — drop the
    # `tree/<branch>` (or `blob/<branch>`) segments and keep the path as the selector.
    if len(parts) >= 5 and parts[3] in {"tree", "blob"}:
        parts = parts[:3] + parts[5:]

    if len(parts) < 3:
        msg = f"Invalid method address '{raw}': expected '{GITHUB_HOST}/<owner>/<repo>[/<selector>]'."
        raise MethodRefParseError(msg)

    for segment in parts[1:]:
        if not _ADDRESS_SEGMENT_PATTERN.match(segment):
            msg = f"Invalid segment '{segment}' in method address '{raw}': allowed characters are letters, digits, '.', '_' and '-'."
            raise MethodRefParseError(msg)

    return MethodRef(address="/".join(parts), tag=tag)
