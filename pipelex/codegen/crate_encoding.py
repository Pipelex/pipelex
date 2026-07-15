"""Canonical JSON and TOML encodings of a normalized library crate.

Both encodings serialize the SAME logical crate (per the standard's [Library Crate Format]) and carry
the same `fingerprint` — the digest is a property of the logical crate, not of a particular encoding's
bytes. Emission is deterministic: the top-level maps (`concepts`, `pipes`, `domains`, `source_map`) are
sorted by qualified key so version-control diffs stay minimal and independent producers agree, while
nested object key order is preserved because structure-field order is semantic (a downstream emitter
declares fields in that order).

Provenance-only inline `source` fields and unset (`None`) members are dropped: they carry no meaning,
TOML has no null, and the fingerprint already excludes them. The top-level `source_map` remains the
single provenance trace.

[Library Crate Format]: mthds/docs/spec/library-crate.md
"""
# tomlkit is not fully typed (`tomlkit.dumps`), so its member access reads as unknown here.
# pyright: reportUnknownMemberType=false

import json
from enum import StrEnum
from typing import Any

import tomlkit
from pydantic import BaseModel

from pipelex.libraries.library_crate import LibraryCrate


class CrateEncoding(StrEnum):
    """The canonical wire encodings a normalized crate can be emitted in."""

    JSON = "json"
    TOML = "toml"


def _dump_object(obj: BaseModel) -> dict[str, Any]:
    """Dump a crate object for emission.

    Prunes `None` members, the provenance-only inline `source`, and the internal `pipe_category`
    discriminator (the union routes on `type`; `pipe_category` is a non-user-facing technical field
    the base marks `exclude=True`, and every subclass defaults it, so dropping it round-trips).
    """
    return obj.model_dump(mode="json", exclude_none=True, exclude={"source", "pipe_category"})


def _encoding_payload(crate: LibraryCrate) -> dict[str, Any]:
    """Build the ordered, key-sorted payload shared by both encodings."""
    concepts: dict[str, Any] = {}
    for concept_ref, value in sorted(crate.concepts.items()):
        concepts[concept_ref] = value if isinstance(value, str) else _dump_object(value)
    pipes = {pipe_ref: _dump_object(blueprint) for pipe_ref, blueprint in sorted(crate.pipes.items())}
    domains = {domain_code: _dump_object(domain) for domain_code, domain in sorted(crate.domains.items())}
    return {
        "mthds_version": crate.mthds_version,
        "concepts": concepts,
        "pipes": pipes,
        "domains": domains,
        "source_map": dict(sorted(crate.source_map.items())),
        "fingerprint": crate.fingerprint,
    }


def encode_crate_json(crate: LibraryCrate) -> str:
    """Encode a normalized crate as canonical JSON (fixed member order, top-level maps key-sorted)."""
    return json.dumps(_encoding_payload(crate), indent=2, ensure_ascii=False) + "\n"


def encode_crate_toml(crate: LibraryCrate) -> str:
    """Encode a normalized crate as canonical TOML — dotted qualified refs are quoted single keys."""
    return tomlkit.dumps(_encoding_payload(crate))


def encode_crate(crate: LibraryCrate, *, encoding: CrateEncoding) -> str:
    """Encode a normalized crate in the selected canonical encoding."""
    match encoding:
        case CrateEncoding.JSON:
            return encode_crate_json(crate)
        case CrateEncoding.TOML:
            return encode_crate_toml(crate)
