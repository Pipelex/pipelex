from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

STORAGE_REF_ENCODING = b"binary/storage-ref"


class StoragePayloadCodec(PayloadCodec):
    """Codec that offloads large Temporal payloads to external storage.

    Payloads whose serialized size meets or exceeds ``size_threshold`` are
    stored via the provided :class:`StorageProviderAbstract` and replaced with
    a lightweight reference payload.  Payloads below the threshold pass through
    unchanged.  Content-addressed keys (SHA-256) give natural deduplication.
    """

    def __init__(
        self,
        storage_provider: StorageProviderAbstract,
        size_threshold: int,
        storage_prefix: str,
    ) -> None:
        self._storage = storage_provider
        self._size_threshold = size_threshold
        self._storage_prefix = storage_prefix

    @override
    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        encoded: list[Payload] = []
        for payload in payloads:
            serialized = payload.SerializeToString()
            if len(serialized) < self._size_threshold:
                encoded.append(payload)
                continue
            key = self._storage_prefix + sha256(serialized).hexdigest()
            uri = await self._storage.store(data=serialized, key=key)
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
