from __future__ import annotations

import pytest
from temporalio.api.common.v1 import Payload

from pipelex.temporal.codec.storage_payload_codec import STORAGE_REF_ENCODING, StoragePayloadCodec
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

TEST_THRESHOLD = 1024
TEST_PREFIX = "test-payloads/"


def _make_payload(size: int) -> Payload:
    """Build a Payload with the given data size."""
    return Payload(
        metadata={"encoding": b"binary/plain"},
        data=b"x" * size,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestStoragePayloadCodec:
    """Unit tests for StoragePayloadCodec encode/decode behavior."""

    @pytest.fixture
    def storage(self) -> InMemoryStorageProvider:
        return InMemoryStorageProvider()

    @pytest.fixture
    def codec(self, storage: InMemoryStorageProvider) -> StoragePayloadCodec:
        return StoragePayloadCodec(
            storage_provider=storage,
            size_threshold=TEST_THRESHOLD,
            storage_prefix=TEST_PREFIX,
        )

    async def test_below_threshold_passes_through(
        self,
        codec: StoragePayloadCodec,
    ) -> None:
        """Payloads smaller than the threshold pass through encode/decode unchanged."""
        small_payload = _make_payload(TEST_THRESHOLD - 100)
        original_bytes = small_payload.SerializeToString()

        encoded = await codec.encode([small_payload])

        assert len(encoded) == 1
        assert encoded[0].SerializeToString() == original_bytes

        decoded = await codec.decode(encoded)

        assert len(decoded) == 1
        assert decoded[0].SerializeToString() == original_bytes

    async def test_above_threshold_offloads_to_storage(
        self,
        codec: StoragePayloadCodec,
        storage: InMemoryStorageProvider,
    ) -> None:
        """Payloads larger than the threshold are offloaded to storage and reconstructed on decode."""
        large_payload = _make_payload(TEST_THRESHOLD + 100)
        original_bytes = large_payload.SerializeToString()

        encoded = await codec.encode([large_payload])

        assert len(encoded) == 1
        ref_payload = encoded[0]

        # The reference payload must carry the storage-ref encoding marker
        assert ref_payload.metadata.get("encoding") == STORAGE_REF_ENCODING

        # The reference payload data is a URI pointing to the stored blob
        uri = ref_payload.data.decode()
        assert uri.startswith("pipelex-storage://")

        # The storage provider must contain the original serialized payload
        assert len(storage.root) == 1

        # Decode must reconstruct the original payload exactly
        decoded = await codec.decode(encoded)

        assert len(decoded) == 1
        assert decoded[0].SerializeToString() == original_bytes

    async def test_content_addressed_deduplication(
        self,
        codec: StoragePayloadCodec,
        storage: InMemoryStorageProvider,
    ) -> None:
        """Encoding the same large payload twice produces a single storage entry."""
        large_payload = _make_payload(TEST_THRESHOLD + 50)

        await codec.encode([large_payload])
        await codec.encode([large_payload])

        assert len(storage.root) == 1

    async def test_mixed_payloads(
        self,
        codec: StoragePayloadCodec,
        storage: InMemoryStorageProvider,
    ) -> None:
        """In a batch, small payloads pass through and large payloads are offloaded."""
        small = _make_payload(10)
        large = _make_payload(TEST_THRESHOLD + 200)
        small_bytes = small.SerializeToString()
        large_bytes = large.SerializeToString()

        encoded = await codec.encode([small, large])

        assert len(encoded) == 2

        # First payload (small) passed through unchanged
        assert encoded[0].SerializeToString() == small_bytes

        # Second payload (large) is a storage reference
        assert encoded[1].metadata.get("encoding") == STORAGE_REF_ENCODING

        # Only the large payload was stored
        assert len(storage.root) == 1

        # Full round-trip preserves both payloads
        decoded = await codec.decode(encoded)

        assert len(decoded) == 2
        assert decoded[0].SerializeToString() == small_bytes
        assert decoded[1].SerializeToString() == large_bytes

    async def test_exactly_at_threshold_is_offloaded(
        self,
        storage: InMemoryStorageProvider,
    ) -> None:
        """A payload whose serialized size equals the threshold is offloaded, not passed through."""
        payload = _make_payload(500)
        serialized_size = len(payload.SerializeToString())

        codec = StoragePayloadCodec(
            storage_provider=storage,
            size_threshold=serialized_size,
            storage_prefix=TEST_PREFIX,
        )

        encoded = await codec.encode([payload])

        assert len(encoded) == 1
        assert encoded[0].metadata.get("encoding") == STORAGE_REF_ENCODING
        assert len(storage.root) == 1

    @pytest.mark.parametrize(
        ("topic", "size"),
        [
            ("small", 10),
            ("at_threshold", TEST_THRESHOLD),
            ("above_threshold", TEST_THRESHOLD + 500),
        ],
    )
    async def test_round_trip_fidelity(
        self,
        codec: StoragePayloadCodec,
        topic: str,
        size: int,
    ) -> None:
        """decode(encode(payloads)) returns identical payloads for various sizes."""
        payload = _make_payload(size)
        original_bytes = payload.SerializeToString()

        encoded = await codec.encode([payload])
        decoded = await codec.decode(encoded)

        assert len(decoded) == 1
        assert decoded[0].SerializeToString() == original_bytes, f"Round-trip failed for {topic} (size={size})"

    # -------------------------------------------------------------------
    # _extract_job_routing tests
    # -------------------------------------------------------------------

    async def test_storage_key_includes_routing_when_available(
        self,
        codec: StoragePayloadCodec,
    ) -> None:
        """When job_metadata is present, storage key includes user_id and pipeline_run_id."""
        routed_payload = Payload(
            metadata={"encoding": b"json/plain"},
            data=b'{"job_metadata": {"user_id": "user42", "pipeline_run_id": "run99"}, "big": "' + b"x" * (TEST_THRESHOLD + 500) + b'"}',
        )

        encoded = await codec.encode([routed_payload])
        assert len(encoded) == 1
        uri = encoded[0].data.decode()
        assert "user42" in uri
        assert "run99" in uri

    @pytest.mark.parametrize(
        ("topic", "payload_data"),
        [
            (
                "non_json_encoding_no_routing",
                b"x" * (TEST_THRESHOLD + 500),
            ),
            (
                "json_missing_job_metadata_no_routing",
                b'{"other_key": "value", "pad": "' + b"x" * (TEST_THRESHOLD + 500) + b'"}',
            ),
            (
                "json_non_dict_job_metadata_no_routing",
                b'{"job_metadata": "not a dict", "pad": "' + b"x" * (TEST_THRESHOLD + 500) + b'"}',
            ),
        ],
    )
    async def test_storage_key_falls_back_to_flat_when_no_routing(
        self,
        storage: InMemoryStorageProvider,
        topic: str,
        payload_data: bytes,
    ) -> None:
        """Payloads without valid job_metadata use a flat storage key (prefix + hash only)."""
        codec = StoragePayloadCodec(
            storage_provider=storage,
            size_threshold=TEST_THRESHOLD,
            storage_prefix=TEST_PREFIX,
        )
        payload = Payload(
            metadata={"encoding": b"json/plain" if topic.startswith("json_") else b"binary/plain"},
            data=payload_data,
        )

        encoded = await codec.encode([payload])
        assert len(encoded) == 1
        uri = encoded[0].data.decode()
        # Flat keys have no slashes after the prefix (just prefix + hash)
        key_after_scheme = uri.split("://", 1)[-1]
        segments = key_after_scheme.split("/")
        # prefix is "test-payloads/" so we expect: test-payloads/{hash} = 2 segments
        assert len(segments) == 2, f"Expected flat key for {topic}, got: {key_after_scheme}"
