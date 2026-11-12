"""Decode a response body under a byte cap, so that no decompression step ever returns more than the cap allows.

httpx decodes a compressed body one raw read at a time, and each read may expand without bound: a 64 KiB read of a
gzip bomb decodes to tens of megabytes in one call, and a stacked ``Content-Encoding: gzip, gzip`` multiplies the ratio
again. The fetch therefore reads the raw body and decodes it here, asking zlib for at most the bytes the cap still
allows plus one, so that a body past the cap is refused one byte past it whatever its compression ratio. The raw side is
bounded too, so that input decoding to nothing cannot keep the read open, and a compressed body must end where its
stream ends: a truncated one, or one with anything after a deflate stream, is refused. NULs after a gzip member are
padding some writers add, and are skipped as :func:`gzip.decompress` skips them.

Only the content codings the fetch asks for are read: none, ``gzip`` (or ``x-gzip``) and ``deflate``, one at most. Any
other answer, more than one coding or one the runtime does not decode, is refused before the body is read.
"""

import zlib
from enum import StrEnum
from typing import Protocol

import httpx

from pipelex.tools.misc.exceptions import RemoteFileFetchError, RemoteFileSizeBound, RemoteFileTooLargeError

ACCEPTED_CONTENT_CODINGS = "gzip, deflate"
"""The ``Accept-Encoding`` the fetch sends: the codings :class:`BoundedBodyDecoder` reads."""

_UNREAD_CODING_REASON = "the server answered in a content encoding the runtime does not read"
_UNDECODABLE_BODY_REASON = "the server answered a compressed body that does not decode"

# How far the raw bytes of a compressed body may pass the decoded cap. Deflate's worst case, data it cannot compress,
# costs a few bytes per stored block of up to 64 KiB plus the headers and trailers, so no real body comes near this;
# without a bound on the raw side, input that decodes to nothing, such as empty blocks or an endless gzip header,
# would keep the read open as long as the server kept sending.
_COMPRESSED_INPUT_SLACK_BYTES = 64 * 1024


def raw_bound_of(*, limit: int) -> int:
    """The most compressed bytes a fetch accepts for a cap of ``limit`` decoded bytes."""
    return limit + _COMPRESSED_INPUT_SLACK_BYTES


class _Decompressor(Protocol):
    """What the decoder uses of a zlib decompression object, whose class zlib does not export."""

    @property
    def unconsumed_tail(self) -> bytes: ...

    @property
    def unused_data(self) -> bytes: ...

    @property
    def eof(self) -> bool: ...

    # zlib's own signature, positional-only, which this protocol describes rather than chooses.
    def decompress(  # kw-only: ignore
        self, data: bytes, max_length: int, /
    ) -> bytes: ...

    def flush(self) -> bytes: ...


class ContentCoding(StrEnum):
    """The content coding of a response body the fetch reads."""

    IDENTITY = "identity"
    GZIP = "gzip"
    DEFLATE = "deflate"

    @property
    def is_compressed(self) -> bool:
        """Whether the body is compressed, so that its declared length is not the length it decodes to."""
        match self:
            case ContentCoding.IDENTITY:
                return False
            case ContentCoding.GZIP | ContentCoding.DEFLATE:
                return True


# The `Content-Encoding` tokens the decoder reads, by the coding each names.
_DECODED_CODINGS: dict[str, ContentCoding] = {"gzip": ContentCoding.GZIP, "x-gzip": ContentCoding.GZIP, "deflate": ContentCoding.DEFLATE}


def content_coding_of(*, headers: httpx.Headers) -> ContentCoding:
    """The one content coding a response's ``Content-Encoding`` applies, ``identity`` being no coding.

    Raises:
        RemoteFileFetchError: The response applies more than one coding, or one the runtime does not decode. The
            reason names neither the coding, which is the server's text, nor the URL.
    """
    codings = [coding.strip().lower() for coding in headers.get_list("content-encoding", split_commas=True)]
    applied = [coding for coding in codings if coding and coding != "identity"]
    if not applied:
        return ContentCoding.IDENTITY
    decoded_coding = _DECODED_CODINGS.get(applied[0]) if len(applied) == 1 else None
    if decoded_coding is not None:
        return decoded_coding
    msg = f"Could not fetch a remote file: {_UNREAD_CODING_REASON}"
    raise RemoteFileFetchError(msg, reason=_UNREAD_CODING_REASON)


def _undecodable_body_error() -> RemoteFileFetchError:
    return RemoteFileFetchError(f"Could not fetch a remote file: {_UNDECODABLE_BODY_REASON}", reason=_UNDECODABLE_BODY_REASON)


class BoundedBodyDecoder:
    """The decoded body of a response, fed its raw chunks, refused as soon as it passes ``limit`` bytes.

    Both sides of a compressed body are bounded. The decoded bytes may not pass ``limit``, and each decompression step is
    asked for no more than one byte past it. The raw bytes may not pass :func:`raw_bound_of` ``limit``, so that input
    decoding to nothing, such as empty deflate blocks or an endless gzip header, cannot hold the read open: that refusal's
    ``bound`` is :attr:`RemoteFileSizeBound.COMPRESSED`, its ``limit`` the raw bound and its ``size`` the raw bytes.

    A ``gzip`` body may hold several members, each read in turn under the same cap, and NULs after a member are skipped,
    as :func:`gzip.decompress` does. A ``deflate`` body is read as zlib-wrapped and, when that does not decode before any
    output, as raw deflate, since servers send both under that name; the raw bytes received until the kind is known are
    kept and replayed, so the choice does not depend on where the network cut the reads. Nothing may follow the end of a
    deflate stream. A compressed body that stops before its stream ends is refused at :meth:`finish`, except an empty
    one, which decodes to nothing.
    """

    def __init__(self, *, coding: ContentCoding, limit: int):
        self.coding = coding
        self.limit = limit
        self._body = bytearray()
        self._raw_size = 0
        self._decompressor: _Decompressor | None
        # The raw bytes of a deflate body until it is known to be zlib-wrapped, replayed as raw deflate if it is not.
        self._undecided_deflate_input: bytearray | None = None
        match coding:
            case ContentCoding.IDENTITY:
                self._decompressor = None
            case ContentCoding.GZIP:
                self._decompressor = _gzip_member_decompressor()
            case ContentCoding.DEFLATE:
                self._decompressor = zlib.decompressobj()
                self._undecided_deflate_input = bytearray()

    def refuse_declared_length_past_bound(self, *, declared_length: int) -> None:
        """Refuse a response whose declared ``Content-Length`` already passes its bound, before its body is read.

        The declared length of a compressed body is its compressed length, which says nothing sure of what it decodes
        to, so it is held to the compressed bound; an uncompressed one is held to ``limit``.

        Raises:
            RemoteFileTooLargeError: The declared length passes the bound.
        """
        if self.coding.is_compressed:
            raw_bound = raw_bound_of(limit=self.limit)
            if declared_length > raw_bound:
                msg = (
                    f"Could not fetch a remote file: it declares {declared_length} compressed bytes, past the {raw_bound} "
                    f"a fetch accepts for a cap of {self.limit} decoded bytes, so it was not read"
                )
                raise RemoteFileTooLargeError(msg, limit=raw_bound, size=declared_length, bound=RemoteFileSizeBound.COMPRESSED)
        elif declared_length > self.limit:
            msg = f"Could not fetch a remote file: it declares {declared_length} bytes, past the {self.limit} bytes a fetch reads, so it was not read"
            raise RemoteFileTooLargeError(msg, limit=self.limit, size=declared_length, bound=RemoteFileSizeBound.DECODED)

    def feed(self, *, chunk: bytes) -> None:
        """Decode a raw chunk of the body into the body.

        Raises:
            RemoteFileTooLargeError: The body passes the limit, or its raw bytes pass the compressed bound.
            RemoteFileFetchError: The compressed body does not decode, or something follows the end of a deflate one.
        """
        if self._decompressor is None:
            self._append(decoded=chunk)
            return
        self._count_raw(chunk=chunk)
        if self._undecided_deflate_input is not None:
            self._feed_undecided_deflate(undecided_input=self._undecided_deflate_input, decompressor=self._decompressor, chunk=chunk)
            return
        try:
            self._decompress(decompressor=self._decompressor, data=chunk)
        except zlib.error as exc:
            raise _undecodable_body_error() from exc

    def finish(self) -> bytes:
        """The whole decoded body, once every raw chunk is fed.

        Raises:
            RemoteFileTooLargeError: What the decompressor still held passes the limit.
            RemoteFileFetchError: The compressed body does not decode, or stops before its stream ends.
        """
        if self._decompressor is None or self._raw_size == 0:
            return bytes(self._body)
        if self._undecided_deflate_input is not None:
            # A body that is no complete zlib stream and decoded to nothing may still be raw deflate.
            try:
                self._flush_to_end(decompressor=self._decompressor)
            except RemoteFileTooLargeError:
                raise
            except RemoteFileFetchError:
                if self._body:
                    raise
                self._replay_as_raw_deflate(undecided_input=self._undecided_deflate_input)
            else:
                return bytes(self._body)
        self._flush_to_end(decompressor=self._decompressor)
        return bytes(self._body)

    def _feed_undecided_deflate(self, *, undecided_input: bytearray, decompressor: _Decompressor, chunk: bytes) -> None:
        """Decode a chunk of a deflate body not yet known to be zlib-wrapped, falling back to raw deflate if it is not.

        Raises:
            RemoteFileFetchError: The body decodes neither way, or fails as zlib-wrapped after decoding some output.
        """
        undecided_input.extend(chunk)
        try:
            self._decompress(decompressor=decompressor, data=chunk)
        except zlib.error as exc:
            if self._body:
                raise _undecodable_body_error() from exc
            self._replay_as_raw_deflate(undecided_input=undecided_input)
            return
        # Output, or the end of the stream, settles that the body is zlib-wrapped.
        if self._body or decompressor.eof:
            self._undecided_deflate_input = None

    def _replay_as_raw_deflate(self, *, undecided_input: bytearray) -> None:
        """Decode every raw byte received so far again, as raw deflate.

        Raises:
            RemoteFileFetchError: The body does not decode as raw deflate either.
        """
        self._undecided_deflate_input = None
        raw_deflate_decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
        self._decompressor = raw_deflate_decompressor
        try:
            self._decompress(decompressor=raw_deflate_decompressor, data=bytes(undecided_input))
        except zlib.error as exc:
            raise _undecodable_body_error() from exc

    def _flush_to_end(self, *, decompressor: _Decompressor) -> None:
        """Append what the decompressor still buffers, and refuse a stream that has not reached its end.

        Raises:
            RemoteFileTooLargeError: What the decompressor still held passes the limit.
            RemoteFileFetchError: The stream does not decode, or stops before its end.
        """
        try:
            # Every chunk was consumed whole, so only the little the decompressor buffers is left.
            self._append(decoded=decompressor.flush())
        except zlib.error as exc:
            raise _undecodable_body_error() from exc
        # zlib's flush does not refuse a cut stream: a body that stops before its end is not the file.
        if not decompressor.eof:
            raise _undecodable_body_error()

    def _decompress(self, *, decompressor: _Decompressor, data: bytes) -> None:
        """Decode ``data``, asking for no more than one byte past what the limit still allows at each step.

        Raises:
            RemoteFileFetchError: Data follows the end of a deflate stream.
        """
        remaining_input = data
        while remaining_input:
            if decompressor.eof:
                remaining_input = self._padding_skipped(data=remaining_input)
                if not remaining_input:
                    return
                decompressor = self._next_member_decompressor()
            allowed = self.limit - len(self._body) + 1
            self._append(decoded=decompressor.decompress(remaining_input, allowed))
            # Past the stream's end, the rest of the input is the next gzip member, or junk after a deflate stream.
            remaining_input = decompressor.unused_data if decompressor.eof else decompressor.unconsumed_tail

    def _padding_skipped(self, *, data: bytes) -> bytes:
        """What follows the end of a stream, past the NULs some writers pad a gzip member with.

        Raises:
            RemoteFileFetchError: Data follows the end of a deflate stream, which takes no padding.
        """
        match self.coding:
            case ContentCoding.GZIP:
                return data.lstrip(b"\x00")
            case ContentCoding.DEFLATE | ContentCoding.IDENTITY:
                raise _undecodable_body_error()

    def _next_member_decompressor(self) -> _Decompressor:
        """A fresh decompressor for what follows the end of a stream: the next member of a gzip body.

        Raises:
            RemoteFileFetchError: Data follows the end of a deflate stream, which has no members.
        """
        match self.coding:
            case ContentCoding.GZIP:
                member_decompressor = _gzip_member_decompressor()
                self._decompressor = member_decompressor
                return member_decompressor
            case ContentCoding.DEFLATE | ContentCoding.IDENTITY:
                raise _undecodable_body_error()

    def _count_raw(self, *, chunk: bytes) -> None:
        self._raw_size += len(chunk)
        raw_bound = raw_bound_of(limit=self.limit)
        if self._raw_size > raw_bound:
            msg = (
                f"Could not fetch a remote file: its compressed body passed the {raw_bound} compressed bytes a fetch accepts "
                f"for a cap of {self.limit} decoded bytes, at {self._raw_size} bytes, so the read stopped"
            )
            raise RemoteFileTooLargeError(msg, limit=raw_bound, size=self._raw_size, bound=RemoteFileSizeBound.COMPRESSED)

    def _append(self, *, decoded: bytes) -> None:
        self._body.extend(decoded)
        if len(self._body) > self.limit:
            size = len(self._body)
            msg = f"Could not fetch a remote file: its body passed the {self.limit} bytes a fetch reads, at {size} bytes, so the read stopped"
            raise RemoteFileTooLargeError(msg, limit=self.limit, size=size, bound=RemoteFileSizeBound.DECODED)


def _gzip_member_decompressor() -> _Decompressor:
    return zlib.decompressobj(zlib.MAX_WBITS | 16)
