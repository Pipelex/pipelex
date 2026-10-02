"""The read scope's check: may this run read the URL a value carries?

A run reads whatever URL its values carry, and a value can carry any URL its method chose — a
construct that assembles one from plain text, a model's structured output, a function's result.
Policing where values are born is hopeless, so the rule is enforced where they are read: in the
content-generation leaves, before the dry-run branch and before any worker is built, and at the
input seam, before an input is uploaded or linked. See `pipelex.system.storage_scope` for where
the read scope comes from.

On a run that carries a read scope:

- a ``pipelex-storage://`` key is read only when it lies under the read scope, compared segment by
  segment, and none of its segments is empty, ``.`` or ``..``;
- a bare path or a ``file://`` URI is never read, and neither is anything ``resolve_uri`` takes
  for a local path, such as a URL in a scheme it does not know;
- ``https://``, ``http://`` and ``data:`` are untouched: a data URL carries its own bytes, and an
  outbound fetch is the SSRF guard's concern.

A run without a read scope reads exactly as it always did.

The check performs no IO, so a refusal says nothing about whether the file exists.
"""

from typing import NamedTuple

from pipelex.system.storage_scope import is_key_within_read_scope
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl, ResolvedHttpUrl, ResolvedLocalPath, ResolvedPipelexStorage
from pipelex.tools.uri.uri_resolver import resolve_uri


class UriReference(NamedTuple):
    """A URL a payload will read, and where it sits, for a refusal to name."""

    uri: str
    # Where the URL sits, in the caller's words: "image 2 of the prompt", "the document to extract".
    position: str


def authorize_uri_read(*, uri: str, read_scope: str | None, position: str) -> None:
    """Refuse the read of `uri` if the run's read scope does not allow it.

    Args:
        uri: The URL about to be read.
        read_scope: The run's read scope, ``None`` for an unscoped run, which reads everything.
        position: Where the URL sits, named in the refusal instead of the URL itself.

    Raises:
        UriReadRefusedError: the URL is a storage key outside the read scope, or a local path.
    """
    if read_scope is None:
        return
    resolved_uri = resolve_uri(uri)
    match resolved_uri:
        case ResolvedHttpUrl() | ResolvedBase64DataUrl():
            return
        case ResolvedPipelexStorage():
            key = resolved_uri.storage_uri.removeprefix(PIPELEX_STORAGE_SCHEME)
            if is_key_within_read_scope(key=key, read_scope=read_scope):
                return
            reason = UriReadRefusalReason.FOREIGN_STORAGE_KEY
        case ResolvedLocalPath():
            reason = UriReadRefusalReason.LOCAL_PATH
    msg = f"Refused to read {position}: {reason.desc}. Pass the file as an input of the run, or upload it first."
    raise UriReadRefusedError(msg, reason=reason)


def authorize_uri_reads(*, uri_references: list[UriReference], read_scope: str | None) -> None:
    """Refuse the first of `uri_references` the run's read scope does not allow.

    Raises:
        UriReadRefusedError: one of the URLs is a storage key outside the read scope, or a local path.
    """
    for uri_reference in uri_references:
        authorize_uri_read(uri=uri_reference.uri, read_scope=read_scope, position=uri_reference.position)
