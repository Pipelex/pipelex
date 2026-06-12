"""Unit tests for the Temporal codec HTTP server (encode/decode endpoints + CORS)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from aiohttp.test_utils import TestClient, TestServer
from google.protobuf import json_format
from temporalio.api.common.v1 import Payload, Payloads

from pipelex.temporal.codec.codec_server import build_codec_server
from pipelex.temporal.codec.storage_payload_codec import STORAGE_REF_ENCODING, StoragePayloadCodec
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

if TYPE_CHECKING:
    from collections.abc import Sequence

ALLOWED_ORIGIN = "http://localhost:8233"
OTHER_ORIGIN = "http://evil.example.com"
SIZE_THRESHOLD = 64
STORAGE_PREFIX = "test-codec/"
JSON_HEADERS = {"Content-Type": "application/json"}


class _RaisingCodec:
    """Stub codec whose encode/decode always raise the configured exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def encode(self, _payloads: Sequence[Payload]) -> list[Payload]:
        raise self._exc

    async def decode(self, _payloads: Sequence[Payload]) -> list[Payload]:
        raise self._exc


def _make_real_codec(storage: InMemoryStorageProvider) -> StoragePayloadCodec:
    return StoragePayloadCodec(
        storage_provider=storage,
        size_threshold=SIZE_THRESHOLD,
        storage_prefix=STORAGE_PREFIX,
    )


def _payloads_json(*payloads: Payload) -> bytes:
    """Serialize payloads to the Payloads-proto JSON the Temporal Web UI sends."""
    return json_format.MessageToJson(Payloads(payloads=list(payloads))).encode()


def _parse_payloads(body: bytes) -> Payloads:
    return json_format.Parse(body, Payloads())


def _make_payload(size: int) -> Payload:
    return Payload(metadata={"encoding": b"binary/plain"}, data=b"x" * size)


@pytest.mark.asyncio(loop_scope="class")
class TestCodecServer:
    @pytest.mark.parametrize("endpoint", ["/encode", "/decode"])
    async def test_cors_preflight_allowed_origin(self, endpoint: str) -> None:
        """OPTIONS preflight from an allowed origin gets the full CORS header set."""
        app = build_codec_server(codec=_make_real_codec(InMemoryStorageProvider()), cors_origins=[ALLOWED_ORIGIN])
        async with TestClient(TestServer(app)) as client:
            response = await client.options(endpoint, headers={"Origin": ALLOWED_ORIGIN})

            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
            assert response.headers["Access-Control-Allow-Methods"] == "POST"
            assert response.headers["Access-Control-Allow-Headers"] == "content-type,x-namespace"

    @pytest.mark.parametrize(
        ("topic", "origin_headers"),
        [
            ("disallowed_origin", {"Origin": OTHER_ORIGIN}),
            ("missing_origin", {}),
        ],
    )
    async def test_cors_preflight_rejected_origin(self, topic: str, origin_headers: dict[str, str]) -> None:
        """OPTIONS preflight from a disallowed or missing origin gets no CORS headers."""
        app = build_codec_server(codec=_make_real_codec(InMemoryStorageProvider()), cors_origins=[ALLOWED_ORIGIN])
        async with TestClient(TestServer(app)) as client:
            response = await client.options("/encode", headers=origin_headers)

            assert response.status == 200
            assert "Access-Control-Allow-Origin" not in response.headers, f"CORS leaked for {topic}"

    async def test_non_json_content_type_rejected_with_cors(self) -> None:
        """A POST without application/json content type returns 415, still carrying CORS headers."""
        app = build_codec_server(codec=_make_real_codec(InMemoryStorageProvider()), cors_origins=[ALLOWED_ORIGIN])
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/encode",
                data=b"whatever",
                headers={"Content-Type": "text/plain", "Origin": ALLOWED_ORIGIN},
            )

            assert response.status == 415
            assert await response.text() == "Expected application/json"
            assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN

    async def test_malformed_payloads_json_rejected(self) -> None:
        """A POST body that is not valid Payloads JSON returns 400."""
        app = build_codec_server(codec=_make_real_codec(InMemoryStorageProvider()), cors_origins=[ALLOWED_ORIGIN])
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/encode", data=b"this is not json", headers=JSON_HEADERS)

            assert response.status == 400
            assert await response.text() == "Malformed Payloads JSON"

    async def test_encode_decode_round_trip_over_http(self) -> None:
        """A large payload is offloaded by /encode and fully restored by /decode."""
        storage = InMemoryStorageProvider()
        app = build_codec_server(codec=_make_real_codec(storage), cors_origins=[ALLOWED_ORIGIN])
        original = _make_payload(SIZE_THRESHOLD + 100)
        original_bytes = original.SerializeToString()

        async with TestClient(TestServer(app)) as client:
            encode_response = await client.post(
                "/encode",
                data=_payloads_json(original),
                headers={**JSON_HEADERS, "Origin": ALLOWED_ORIGIN},
            )

            assert encode_response.status == 200
            assert encode_response.content_type == "application/json"
            assert encode_response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN

            encoded_body = await encode_response.read()
            encoded = _parse_payloads(encoded_body)
            assert len(encoded.payloads) == 1
            assert encoded.payloads[0].metadata["encoding"] == STORAGE_REF_ENCODING
            assert len(storage.root) == 1

            decode_response = await client.post("/decode", data=encoded_body, headers=JSON_HEADERS)

            assert decode_response.status == 200
            decoded = _parse_payloads(await decode_response.read())
            assert len(decoded.payloads) == 1
            assert decoded.payloads[0].SerializeToString() == original_bytes

    async def test_encode_small_payload_passes_through(self) -> None:
        """A payload below the threshold comes back from /encode unchanged."""
        storage = InMemoryStorageProvider()
        app = build_codec_server(codec=_make_real_codec(storage), cors_origins=[ALLOWED_ORIGIN])
        original = _make_payload(10)

        async with TestClient(TestServer(app)) as client:
            response = await client.post("/encode", data=_payloads_json(original), headers=JSON_HEADERS)

            assert response.status == 200
            encoded = _parse_payloads(await response.read())
            assert encoded.payloads[0].SerializeToString() == original.SerializeToString()
            assert len(storage.root) == 0

    @pytest.mark.parametrize(
        ("topic", "codec_exc", "expected_status", "expected_text"),
        [
            ("storage_object_missing", StorageFileNotFoundError("blob gone"), 404, "Storage object not found"),
            ("storage_io_error", OSError("disk on fire"), 502, "Storage I/O error"),
            ("file_not_found_is_io_error", FileNotFoundError("no such file"), 502, "Storage I/O error"),
        ],
    )
    async def test_codec_failures_map_to_http_errors(
        self,
        topic: str,
        codec_exc: Exception,
        expected_status: int,
        expected_text: str,
    ) -> None:
        """Storage lookup and I/O failures inside the codec map to diagnostic HTTP errors with CORS."""
        raising_codec = cast("StoragePayloadCodec", _RaisingCodec(codec_exc))
        app = build_codec_server(codec=raising_codec, cors_origins=[ALLOWED_ORIGIN])

        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/decode",
                data=_payloads_json(_make_payload(10)),
                headers={**JSON_HEADERS, "Origin": ALLOWED_ORIGIN},
            )

            assert response.status == expected_status, f"Wrong status for {topic}"
            assert await response.text() == expected_text
            assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
