import os
import zlib

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.tools.misc.bounded_body_decoder import BoundedBodyDecoder, ContentCoding, content_coding_of
from pipelex.tools.misc.exceptions import RemoteFileFetchError, RemoteFileTooLargeError

# The most bytes the transport hands over in one raw read.
RAW_READ_SIZE = 64 * 1024


def _decode_in_raw_reads(*, decoder: BoundedBodyDecoder, body: bytes) -> bytes:
    for start in range(0, len(body), RAW_READ_SIZE):
        decoder.feed(chunk=body[start : start + RAW_READ_SIZE])
    return decoder.finish()


def _zlib_compress(*, data: bytes, wbits: int) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, wbits)
    return compressor.compress(data) + compressor.flush()


class TestBoundedBodyDecoder:
    @pytest.mark.parametrize(
        ("header_values", "expected"),
        [
            pytest.param([], ContentCoding.IDENTITY, id="none"),
            pytest.param(["identity"], ContentCoding.IDENTITY, id="identity"),
            pytest.param(["gzip"], ContentCoding.GZIP, id="gzip"),
            pytest.param(["X-Gzip"], ContentCoding.GZIP, id="x-gzip-any-case"),
            pytest.param(["deflate"], ContentCoding.DEFLATE, id="deflate"),
            pytest.param(["gzip, identity"], ContentCoding.GZIP, id="identity-ignored"),
        ],
    )
    def test_the_content_codings_the_runtime_reads(self, header_values: list[str], expected: ContentCoding) -> None:
        headers = httpx.Headers([("Content-Encoding", value) for value in header_values])

        assert content_coding_of(headers=headers) == expected

    @pytest.mark.parametrize(
        "header_values",
        [
            pytest.param(["gzip, gzip"], id="stacked-gzip"),
            pytest.param(["gzip", "deflate"], id="two-headers"),
            pytest.param(["br"], id="brotli"),
            pytest.param(["zstd"], id="zstd"),
            pytest.param(["compress"], id="unknown"),
        ],
    )
    def test_any_other_content_coding_is_refused(self, header_values: list[str]) -> None:
        headers = httpx.Headers([("Content-Encoding", value) for value in header_values])

        with pytest.raises(RemoteFileFetchError) as exc_info:
            content_coding_of(headers=headers)

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert exc_info.value.resolve_error_code() == CoreCode.INPUT_FILE_UNREADABLE
        assert exc_info.value.reason == "the server answered in a content encoding the runtime does not read"

    @pytest.mark.parametrize(
        ("coding", "wbits"),
        [
            pytest.param(ContentCoding.GZIP, zlib.MAX_WBITS | 16, id="gzip"),
            pytest.param(ContentCoding.DEFLATE, zlib.MAX_WBITS, id="deflate"),
        ],
    )
    def test_a_compression_bomb_is_refused_one_byte_past_the_cap(self, coding: ContentCoding, wbits: int) -> None:
        """No decompression step returns more than the cap allows, so a bomb never expands in memory."""
        bomb = _zlib_compress(data=b"\0" * 50_000_000, wbits=wbits)
        decoder = BoundedBodyDecoder(coding=coding, limit=1000)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            decoder.feed(chunk=bomb[:RAW_READ_SIZE])

        assert (exc_info.value.limit, exc_info.value.size) == (1000, 1001)

    def test_a_plain_body_past_the_cap_is_refused(self) -> None:
        decoder = BoundedBodyDecoder(coding=ContentCoding.IDENTITY, limit=1000)
        decoder.feed(chunk=b"x" * 600)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            decoder.feed(chunk=b"x" * 600)

        assert (exc_info.value.limit, exc_info.value.size) == (1000, 1200)

    @pytest.mark.parametrize(
        ("coding", "wbits"),
        [
            pytest.param(ContentCoding.IDENTITY, None, id="identity"),
            pytest.param(ContentCoding.GZIP, zlib.MAX_WBITS | 16, id="gzip"),
            pytest.param(ContentCoding.DEFLATE, zlib.MAX_WBITS, id="deflate-zlib-wrapped"),
            pytest.param(ContentCoding.DEFLATE, -zlib.MAX_WBITS, id="deflate-raw"),
        ],
    )
    def test_a_body_decoding_to_exactly_the_cap_is_returned_whole(self, coding: ContentCoding, wbits: int | None) -> None:
        decoded = os.urandom(200_000)
        encoded = decoded if wbits is None else _zlib_compress(data=decoded, wbits=wbits)

        assert _decode_in_raw_reads(decoder=BoundedBodyDecoder(coding=coding, limit=len(decoded)), body=encoded) == decoded

    @pytest.mark.parametrize(
        ("coding", "body"),
        [
            pytest.param(ContentCoding.GZIP, b"\x1f\x8b\x08\x00 not really a gzip stream", id="gzip"),
            pytest.param(ContentCoding.DEFLATE, b"neither zlib-wrapped nor raw deflate \xff\xff\xff", id="deflate"),
        ],
    )
    def test_a_corrupt_compressed_body_is_unreadable(self, coding: ContentCoding, body: bytes) -> None:
        decoder = BoundedBodyDecoder(coding=coding, limit=1000)

        with pytest.raises(RemoteFileFetchError) as exc_info:
            _decode_in_raw_reads(decoder=decoder, body=body)

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert exc_info.value.resolve_error_code() == CoreCode.INPUT_FILE_UNREADABLE
        assert exc_info.value.reason == "the server answered a compressed body that does not decode"
