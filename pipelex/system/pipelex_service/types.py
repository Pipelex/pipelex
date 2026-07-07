"""Leaf-level enums shared by the ``pipelex_service`` public surface.

Lives here — separate from the heavy ``remote_config_fetcher`` module — so that
``cogt/``-side modules (which already need source provenance to branch error messages and
disable telemetry on stale specs) can import the enum without pulling the fetcher and its
``httpx`` + ``tenacity`` dependencies. Keeps the cogt → pipelex_service edge clean and
avoids a layering inversion as more cogt callers acquire a need for provenance metadata.
"""

from __future__ import annotations

from enum import StrEnum


class RemoteConfigSource(StrEnum):
    """Where a ``RemoteConfigResult`` was sourced from."""

    FRESH = "fresh"
    CACHED = "cached"

    @property
    def is_cached(self) -> bool:
        """True when the config came from the on-disk fallback rather than the network.

        Use this everywhere instead of ``source == RemoteConfigSource.CACHED`` so the
        match/case rule from the project standards stays out of caller code.
        """
        match self:
            case RemoteConfigSource.FRESH:
                return False
            case RemoteConfigSource.CACHED:
                return True
