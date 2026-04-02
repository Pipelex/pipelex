from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast

from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec
from typing_extensions import override

from pipelex import log

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

STORAGE_REF_ENCODING = b"binary/storage-ref"
JSON_PLAIN_ENCODING = b"json/plain"


class StoragePayloadCodec(PayloadCodec):
    """Codec that offloads large Temporal payloads to external storage.

    Payloads whose serialized size meets or exceeds ``size_threshold`` are
    stored via the provided :class:`StorageProviderAbstract` and replaced with
    a lightweight reference payload.  Payloads below the threshold pass through
    unchanged.  Content-addressed keys (SHA-256) give natural deduplication.

    Storage keys are structured as ``{user_id}/{pipeline_run_id}/{hash}`` when
    the payload contains ``job_metadata``, enabling per-client cleanup.
    """

    def __init__(
        self,
        storage_provider: StorageProviderAbstract,
        size_threshold: int,
        storage_prefix: str,
    ) -> None:
        self._storage = storage_provider
        self._size_threshold = size_threshold
        self._storage_prefix = storage_prefix if storage_prefix.endswith("/") else f"{storage_prefix}/"

    @staticmethod
    def _extract_job_routing(payload: Payload) -> tuple[str, str] | None:
        """Extract user_id and pipeline_run_id from a JSON payload's job_metadata.

        Returns:
            A (user_id, pipeline_run_id) tuple, or None if the payload is not
            JSON or does not contain job_metadata at the top level.
        """
        if payload.metadata.get("encoding") != JSON_PLAIN_ENCODING:
            return None
        try:
            data = json.loads(payload.data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        typed_data = cast("dict[str, Any]", data)
        job_metadata = typed_data.get("job_metadata")
        if not isinstance(job_metadata, dict):
            return None
        user_id: str | None = job_metadata.get("user_id")  # type: ignore[assignment]
        pipeline_run_id: str | None = job_metadata.get("pipeline_run_id")  # type: ignore[assignment]
        if isinstance(user_id, str) and isinstance(pipeline_run_id, str):
            return user_id, pipeline_run_id
        return None

    def _build_storage_key(self, payload: Payload, hash_hex: str) -> str:
        """Build a storage key, structured by job routing when available."""
        routing = self._extract_job_routing(payload)
        if routing:
            user_id, pipeline_run_id = routing
            return f"{self._storage_prefix}{user_id}/{pipeline_run_id}/{hash_hex}"
        return f"{self._storage_prefix}{hash_hex}"

    @override
    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        encoded: list[Payload] = []
        for payload in payloads:
            serialized = payload.SerializeToString()
            if len(serialized) < self._size_threshold:
                encoded.append(payload)
                continue
            hash_hex = sha256(serialized).hexdigest()
            key = self._build_storage_key(payload, hash_hex)
            uri = await self._storage.store(data=serialized, key=key)
            log.dev(f"Payload offloaded to storage: key='{key}'")
            ref_payload = Payload(
                metadata={"encoding": STORAGE_REF_ENCODING},
                data=uri.encode(),
            )
            encoded.append(ref_payload)
        return encoded

    @override
    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        decoded: list[Payload] = []
        for payload in payloads:
            if payload.metadata.get("encoding") != STORAGE_REF_ENCODING:
                decoded.append(payload)
                continue
            uri = payload.data.decode()
            original_bytes = await self._storage.load(uri)
            original_payload = Payload()
            original_payload.ParseFromString(original_bytes)
            decoded.append(original_payload)
        return decoded
