import gzip
import os
import zlib

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.tools.misc.bounded_body_decoder import BoundedBodyDecoder, ContentCoding, content_coding_of, raw_bound_of
from pipelex.tools.misc.exceptions import RemoteFileFetchError, RemoteFileSizeBound, RemoteFileTooLargeError

# The most bytes the transport hands over in one raw read.
RAW_READ_SIZE = 64 * 1024


def _decode_in_raw_reads(*, decoder: BoundedBodyDecoder, body: bytes) -> bytes:
    for start in range(0, len(body), RAW_READ_SIZE):
        decoder.feed(chunk=body[start : start + RAW_READ_SIZE])
    return decoder.finish()


# A regression that stops refusing must fail the test rather than hang it: no test feeds more raw reads than this.
MAX_RAW_READS = 50
# A deflate stored block that holds nothing and is not the last: five bytes that decode to nothing, forever.
EMPTY_STORED_BLOCK = b"\x00\x00\x00\xff\xff"
UNDECODABLE_REASON = "the server answered a compressed body that does not decode"
FIRST_THEN_SECOND = gzip.compress(b"first-") + gzip.compress(b"second")
PATTERN = bytes(range(256)) * 400
GZIP_OF_PATTERN = gzip.compress(PATTERN)
ZLIB_OF_PATTERN = zlib.compress(PATTERN)
# A raw deflate stream whose first two bytes also read as a valid zlib header: a stored block holding b"Z", then an
# empty last block.
RAW_DEFLATE_WITH_A_ZLIB_LOOKING_HEAD = bytes([0x78, 0x01, 0x00, 0xFE, 0xFF]) + b"Z" + bytes([0x01, 0x00, 0x00, 0xFF, 0xFF])
NUL_PADDING = b"\x00" * 512


def _split_points(*, body: bytes) -> list[int]:
    return [*range(21), len(body) // 2, len(body) - 1]


def _feed_until_refused(*, decoder: BoundedBodyDecoder, head: bytes, chunk: bytes) -> tuple[int, RemoteFileFetchError]:
    """Feed ``head``, then ``chunk`` again and again, until the decoder refuses: how many reads of ``chunk`` it took, and the refusal."""
    raw_reads = 0
    try:
        decoder.feed(chunk=head)
        for _ in range(MAX_RAW_READS):
            raw_reads += 1
            decoder.feed(chunk=chunk)
        decoder.finish()
    except RemoteFileFetchError as exc:
        return raw_reads, exc
    pytest.fail(f"The decoder took {MAX_RAW_READS} raw reads without refusing")


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

    @pytest.mark.parametrize(
        ("coding", "head", "chunk"),
        [
            pytest.param(ContentCoding.DEFLATE, b"", EMPTY_STORED_BLOCK * (RAW_READ_SIZE // 5), id="raw-deflate-empty-blocks"),
            pytest.param(ContentCoding.DEFLATE, b"\x78\x9c", EMPTY_STORED_BLOCK * (RAW_READ_SIZE // 5), id="zlib-wrapped-empty-blocks"),
            pytest.param(ContentCoding.GZIP, b"\x1f\x8b\x08\x08\x00\x00\x00\x00\x00\x03", b"A" * RAW_READ_SIZE, id="gzip-endless-file-name"),
        ],
    )
    def test_input_that_decodes_to_nothing_is_refused_once_it_passes_the_slack(self, coding: ContentCoding, head: bytes, chunk: bytes) -> None:
        """Raw bytes count too, so a body that keeps coming without decoding to anything cannot hold the read open."""
        raw_reads, refusal = _feed_until_refused(decoder=BoundedBodyDecoder(coding=coding, limit=1000), head=head, chunk=chunk)

        assert isinstance(refusal, RemoteFileTooLargeError)
        assert raw_reads == 2
        # Limit and size are both compressed bytes: the raw bound, and the raw bytes received when the read stopped.
        assert refusal.bound == RemoteFileSizeBound.COMPRESSED
        assert refusal.limit == raw_bound_of(limit=1000)
        assert refusal.size == len(head) + raw_reads * len(chunk)
        assert "compressed" in refusal.message

    @pytest.mark.parametrize(
        ("coding", "stream", "after"),
        [
            pytest.param(ContentCoding.GZIP, gzip.compress(b"hello"), b"\xff" * RAW_READ_SIZE, id="junk-after-gzip"),
            pytest.param(
                ContentCoding.DEFLATE,
                _zlib_compress(data=b"hello", wbits=zlib.MAX_WBITS),
                _zlib_compress(data=b"again", wbits=zlib.MAX_WBITS),
                id="a-second-stream-after-zlib-wrapped-deflate",
            ),
            pytest.param(
                ContentCoding.DEFLATE,
                _zlib_compress(data=b"hello", wbits=-zlib.MAX_WBITS),
                _zlib_compress(data=b"again", wbits=-zlib.MAX_WBITS),
                id="a-second-stream-after-raw-deflate",
            ),
        ],
    )
    def test_what_follows_a_complete_stream_is_refused_at_once(self, coding: ContentCoding, stream: bytes, after: bytes) -> None:
        """A gzip body's next member must be gzip; a deflate body has no next member, so anything after its end is refused."""
        raw_reads, refusal = _feed_until_refused(decoder=BoundedBodyDecoder(coding=coding, limit=1000), head=stream, chunk=after)

        assert not isinstance(refusal, RemoteFileTooLargeError)
        assert refusal.reason == UNDECODABLE_REASON
        assert raw_reads == 1

    @pytest.mark.parametrize(
        "chunks",
        [
            pytest.param([FIRST_THEN_SECOND], id="one-read"),
            pytest.param([gzip.compress(b"first-"), gzip.compress(b"second")], id="one-read-per-member"),
            pytest.param([FIRST_THEN_SECOND[:25], FIRST_THEN_SECOND[25:40], FIRST_THEN_SECOND[40:]], id="reads-cutting-the-members"),
        ],
    )
    def test_every_member_of_a_multi_member_gzip_body_is_read(self, chunks: list[bytes]) -> None:
        decoder = BoundedBodyDecoder(coding=ContentCoding.GZIP, limit=1000)
        for chunk in chunks:
            decoder.feed(chunk=chunk)

        assert decoder.finish() == b"first-second"

    def test_the_cap_spans_every_member_of_a_gzip_body(self) -> None:
        decoder = BoundedBodyDecoder(coding=ContentCoding.GZIP, limit=1000)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            decoder.feed(chunk=gzip.compress(b"x" * 600) + gzip.compress(b"y" * 600))

        assert (exc_info.value.limit, exc_info.value.size) == (1000, 1001)

    @pytest.mark.parametrize(
        ("coding", "truncated"),
        [
            pytest.param(ContentCoding.GZIP, GZIP_OF_PATTERN[:-8], id="gzip-without-its-trailer"),
            pytest.param(ContentCoding.GZIP, GZIP_OF_PATTERN[: len(GZIP_OF_PATTERN) // 2], id="half-a-gzip-stream"),
            pytest.param(ContentCoding.GZIP, GZIP_OF_PATTERN[:10], id="a-gzip-header-alone"),
            pytest.param(ContentCoding.DEFLATE, ZLIB_OF_PATTERN[: len(ZLIB_OF_PATTERN) // 2], id="half-a-zlib-stream"),
        ],
    )
    def test_a_truncated_compressed_body_is_refused(self, coding: ContentCoding, truncated: bytes) -> None:
        decoder = BoundedBodyDecoder(coding=coding, limit=10_000_000)

        with pytest.raises(RemoteFileFetchError) as exc_info:
            _decode_in_raw_reads(decoder=decoder, body=truncated)

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert exc_info.value.reason == UNDECODABLE_REASON

    @pytest.mark.parametrize("coding", [ContentCoding.GZIP, ContentCoding.DEFLATE])
    def test_an_empty_compressed_body_decodes_to_nothing(self, coding: ContentCoding) -> None:
        """A server may label an empty body as compressed: it decodes to nothing, as httpx reads it."""
        decoder = BoundedBodyDecoder(coding=coding, limit=1000)
        decoder.feed(chunk=b"")

        assert decoder.finish() == b""

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            pytest.param(_zlib_compress(data=PATTERN[:5000], wbits=-zlib.MAX_WBITS), PATTERN[:5000], id="raw-deflate"),
            pytest.param(_zlib_compress(data=PATTERN[:5000], wbits=zlib.MAX_WBITS), PATTERN[:5000], id="zlib-wrapped-deflate"),
            pytest.param(RAW_DEFLATE_WITH_A_ZLIB_LOOKING_HEAD, b"Z", id="raw-deflate-with-a-zlib-looking-head"),
        ],
    )
    def test_a_deflate_body_decodes_the_same_wherever_its_reads_split(self, body: bytes, expected: bytes) -> None:
        """Which kind of deflate a body is cannot depend on where the network cut its first read."""
        for split_point in _split_points(body=body):
            decoder = BoundedBodyDecoder(coding=ContentCoding.DEFLATE, limit=1_000_000)
            decoder.feed(chunk=body[:split_point])
            decoder.feed(chunk=body[split_point:])

            assert decoder.finish() == expected, f"split at {split_point}"

    @pytest.mark.parametrize(
        "chunks",
        [
            pytest.param([gzip.compress(b"hello") + NUL_PADDING], id="same-read"),
            pytest.param([gzip.compress(b"hello"), NUL_PADDING], id="separate-read"),
            pytest.param([gzip.compress(b"hello"), NUL_PADDING[:100], NUL_PADDING[100:]], id="several-reads"),
        ],
    )
    def test_nul_padding_after_a_gzip_member_is_ignored(self, chunks: list[bytes]) -> None:
        """Some writers pad a gzip body with NULs, which gzip.decompress skips and httpx never refused."""
        decoder = BoundedBodyDecoder(coding=ContentCoding.GZIP, limit=1000)
        for chunk in chunks:
            decoder.feed(chunk=chunk)

        assert decoder.finish() == b"hello"

    @pytest.mark.parametrize(
        "chunks",
        [
            pytest.param([gzip.compress(b"first-") + NUL_PADDING + gzip.compress(b"second")], id="same-read"),
            pytest.param([gzip.compress(b"first-"), NUL_PADDING, gzip.compress(b"second")], id="separate-reads"),
        ],
    )
    def test_nul_padding_between_gzip_members_is_ignored(self, chunks: list[bytes]) -> None:
        decoder = BoundedBodyDecoder(coding=ContentCoding.GZIP, limit=1000)
        for chunk in chunks:
            decoder.feed(chunk=chunk)

        assert decoder.finish() == b"first-second"
