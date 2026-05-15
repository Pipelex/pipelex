"""On-disk fallback cache for the Pipelex Gateway remote config.

The cache is a **last-resort** safety net for offline operation. It is never read for freshness
optimisation. Layout::

    ~/.pipelex/cache/remote_config.json

The on-disk payload is the raw JSON returned by the remote endpoint (not a re-serialised
Pydantic dump), so the cache is stable across minor schema drift. Schema-breaking changes
require bumping both the remote-config URL version (in ``pipelex-back-office``) and
``CACHE_SCHEMA_VERSION`` here; older caches are then rejected on load and re-primed on the
next successful fetch.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex import log
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.remote_config import RemoteConfig

CACHE_SCHEMA_VERSION = 1
CACHE_SUBDIR_NAME = "cache"
CACHE_FILE_NAME = "remote_config.json"


class CachedRemoteConfig(BaseModel):
    """A snapshot of the remote gateway config plus the metadata needed to validate it."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(description="On-disk schema version; mismatches reject the cache")
    cached_at: datetime = Field(description="UTC timestamp when this snapshot was written")
    raw_config: dict[str, Any] = Field(description="The raw remote-config JSON payload, untouched")

    def to_remote_config(self) -> RemoteConfig:
        """Re-validate the raw payload into a ``RemoteConfig`` model on demand."""
        return RemoteConfig.model_validate(self.raw_config)


class RemoteConfigCache:
    """Read/write helpers for the on-disk remote-config fallback."""

    @classmethod
    def cache_path(cls) -> Path:
        """Resolve the cache file path under the global ``~/.pipelex`` directory."""
        return config_manager.global_config_dir / CACHE_SUBDIR_NAME / CACHE_FILE_NAME

    @classmethod
    def load(cls) -> CachedRemoteConfig | None:
        """Return the cached snapshot, or ``None`` when there is no usable cache.

        Any of the following result in ``None``:
        - the cache file does not exist
        - the file cannot be read or parsed
        - the on-disk schema version doesn't match this code's ``CACHE_SCHEMA_VERSION``
        - the JSON doesn't validate as ``CachedRemoteConfig``

        Bare ``Exception`` is never caught — only the specific classes raised by the
        filesystem, JSON, and Pydantic layers.
        """
        path = cls.cache_path()
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            log.warning(f"Could not read remote config cache at {path}: {exc}")
            return None

        try:
            raw = json.loads(content)
        except JSONDecodeError as exc:
            log.warning(f"Remote config cache at {path} is not valid JSON: {exc}")
            return None

        try:
            cached = CachedRemoteConfig.model_validate(raw)
        except ValidationError as exc:
            log.warning(f"Remote config cache at {path} failed validation and will be ignored: {exc}")
            return None

        if cached.schema_version != CACHE_SCHEMA_VERSION:
            log.warning(f"Remote config cache at {path} has schema_version={cached.schema_version}, expected {CACHE_SCHEMA_VERSION}; ignoring.")
            return None

        return cached

    @classmethod
    def store(cls, remote_config_payload: dict[str, Any]) -> None:
        """Atomically write the raw remote-config payload to disk.

        Writes go to a temp file in the cache directory and are then moved into place with
        ``os.replace``, which is atomic on the local filesystem. If the move fails, the temp
        file is removed so we don't leave half-written caches around.

        The argument is the **raw** JSON returned by the remote endpoint, NOT a serialised
        ``RemoteConfig`` instance — this keeps the cache stable across minor schema drift.
        """
        path = cls.cache_path()
        cache_dir = path.parent
        cache_dir.mkdir(parents=True, exist_ok=True)

        cached = CachedRemoteConfig(
            schema_version=CACHE_SCHEMA_VERSION,
            cached_at=datetime.now(tz=timezone.utc),
            raw_config=remote_config_payload,
        )
        serialised = cached.model_dump_json()

        tmp_file = tempfile.NamedTemporaryFile(  # noqa: SIM115 - we manage the handle manually for atomic replace
            mode="w",
            encoding="utf-8",
            dir=str(cache_dir),
            prefix=f".{CACHE_FILE_NAME}.",
            suffix=".tmp",
            delete=False,
        )
        tmp_path = Path(tmp_file.name)
        replaced = False
        try:
            try:
                tmp_file.write(serialised)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            finally:
                tmp_file.close()
            tmp_path.replace(path)
            replaced = True
        finally:
            if not replaced:
                try:
                    tmp_path.unlink()
                except FileNotFoundError:
                    pass
