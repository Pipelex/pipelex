"""Decode a response body under a byte cap, so that no decompression step ever returns more than the cap allows.

httpx decodes a compressed body one raw read at a time, and each read may expand without bound: a 64 KiB read of a
gzip bomb decodes to tens of megabytes in one call, and a stacked ``Content-Encoding: gzip, gzip`` multiplies the ratio
again. The fetch therefore reads the raw body and decodes it here, asking zlib for at most the bytes the cap still
allows plus one, so that a body past the cap is refused one byte past it whatever its compression ratio. The raw side is
bounded too, so that input decoding to nothing cannot keep the read open, and a compressed body must end where its
stream ends: a truncated one, or one with anything after a deflate stream, is refused.

Only the content codings the fetch asks for are read: none, ``gzip`` (or ``x-gzip``) and ``deflate``, one at most. Any
other answer, more than one coding or one the runtime does not decode, is refused before the body is read.
"""

import zlib
from enum import StrEnum
from typing import Protocol

import httpx

from pipelex.tools.misc.exceptions import RemoteFileFetchError, RemoteFileTooLargeError

ACCEPTED_CONTENT_CODINGS = "gzip, deflate"
"""The ``Accept-Encoding`` the fetch sends: the codings :class:`BoundedBodyDecoder` reads."""

_UNREAD_CODING_REASON = "the server answered in a content encoding the runtime does not read"
_UNDECODABLE_BODY_REASON = "the server answered a compressed body that does not decode"

# How far the raw bytes of a compressed body may pass the decoded cap. Deflate's worst case, data it cannot compress,
# costs a few bytes per stored block of up to 64 KiB plus the headers and trailers, so no real body comes near this;
# without a bound on the raw side, input that decodes to nothing, such as empty blocks or an endless gzip header,
# would keep the read open as long as the server kept sending.
_COMPRESSED_INPUT_SLACK_BYTES = 64 * 1024


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
    asked for no more than one byte past it. The raw bytes may not pass ``limit`` by more than
    :data:`_COMPRESSED_INPUT_SLACK_BYTES`, so that input decoding to nothing, such as empty deflate blocks or an endless
    gzip header, cannot hold the read open: its refusal's ``size`` is then the raw bytes received.

    A ``gzip`` body may hold several members, each read in turn under the same cap, as :func:`gzip.decompress` reads
    them. A ``deflate`` body is read as zlib-wrapped and, when its first chunk does not decode that way, as raw deflate,
    as httpx's own decoder does, since servers send both under that name; nothing may follow its end. A compressed body
    that stops before its stream ends is refused at :meth:`finish`, except an empty one, which decodes to nothing.
    """

    def __init__(self, *, coding: ContentCoding, limit: int):
        self.coding = coding
        self.limit = limit
        self._body = bytearray()
        self._raw_size = 0
        self._decompressor: _Decompressor | None
        # Whether the deflate body may still turn out to be raw deflate, until a chunk has decoded.
        self._is_first_deflate_attempt = False
        match coding:
            case ContentCoding.IDENTITY:
                self._decompressor = None
            case ContentCoding.GZIP:
                self._decompressor = _gzip_member_decompressor()
            case ContentCoding.DEFLATE:
                self._decompressor = zlib.decompressobj()
                self._is_first_deflate_attempt = True

    def feed(self, *, chunk: bytes) -> None:
        """Decode a raw chunk of the body into the body.

        Raises:
            RemoteFileTooLargeError: The body passes the limit, or its raw bytes pass it by more than the slack.
            RemoteFileFetchError: The compressed body does not decode, or something follows the end of a deflate one.
        """
        if self._decompressor is None:
            self._append(decoded=chunk)
            return
        self._count_raw(chunk=chunk)
        try:
            self._decompress(decompressor=self._decompressor, data=chunk)
        except zlib.error as exc:
            if not self._is_first_deflate_attempt or self._body:
                raise _undecodable_body_error() from exc
            self._is_first_deflate_attempt = False
            raw_deflate_decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
            self._decompressor = raw_deflate_decompressor
            try:
                self._decompress(decompressor=raw_deflate_decompressor, data=chunk)
            except zlib.error as raw_exc:
                raise _undecodable_body_error() from raw_exc
        if chunk:
            self._is_first_deflate_attempt = False

    def finish(self) -> bytes:
        """The whole decoded body, once every raw chunk is fed.

        Raises:
            RemoteFileTooLargeError: What the decompressor still held passes the limit.
            RemoteFileFetchError: The compressed body does not decode, or stops before its stream ends.
        """
        if self._decompressor is not None and self._raw_size > 0:
            try:
                # Every chunk was consumed whole, so only the little the decompressor buffers is left.
                self._append(decoded=self._decompressor.flush())
            except zlib.error as exc:
                raise _undecodable_body_error() from exc
            # zlib's flush does not refuse a cut stream: a body that stops before its end is not the file.
            if not self._decompressor.eof:
                raise _undecodable_body_error()
        return bytes(self._body)

    def _decompress(self, *, decompressor: _Decompressor, data: bytes) -> None:
        """Decode ``data``, asking for no more than one byte past what the limit still allows at each step.

        Raises:
            RemoteFileFetchError: Data follows the end of a deflate stream.
        """
        remaining_input = data
        while remaining_input:
            if decompressor.eof:
                decompressor = self._next_member_decompressor()
            allowed = self.limit - len(self._body) + 1
            self._append(decoded=decompressor.decompress(remaining_input, allowed))
            # Past the stream's end, the rest of the input is the next gzip member, or junk after a deflate stream.
            remaining_input = decompressor.unused_data if decompressor.eof else decompressor.unconsumed_tail

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
        if self._raw_size > self.limit + _COMPRESSED_INPUT_SLACK_BYTES:
            msg = (
                f"Could not fetch a remote file: its compressed body passed {self.limit + _COMPRESSED_INPUT_SLACK_BYTES} bytes received "
                f"for a cap of {self.limit} decoded bytes, at {self._raw_size} bytes, so the read stopped"
            )
            raise RemoteFileTooLargeError(msg, limit=self.limit, size=self._raw_size)

    def _append(self, *, decoded: bytes) -> None:
        self._body.extend(decoded)
        if len(self._body) > self.limit:
            size = len(self._body)
            msg = f"Could not fetch a remote file: its body passed the {self.limit} bytes a fetch reads, at {size} bytes, so the read stopped"
            raise RemoteFileTooLargeError(msg, limit=self.limit, size=size)


def _gzip_member_decompressor() -> _Decompressor:
    return zlib.decompressobj(zlib.MAX_WBITS | 16)
