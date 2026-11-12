"""Decode a response body under a byte cap, so that no decompression step ever returns more than the cap allows.

httpx decodes a compressed body one raw read at a time, and each read may expand without bound: a 64 KiB read of a
gzip bomb decodes to tens of megabytes in one call, and a stacked ``Content-Encoding: gzip, gzip`` multiplies the ratio
again. The fetch therefore reads the raw body and decodes it here, asking zlib for at most the bytes the cap still
allows plus one, so that a body past the cap is refused one byte past it whatever its compression ratio.

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


class _Decompressor(Protocol):
    """What the decoder uses of a zlib decompression object, whose class zlib does not export."""

    @property
    def unconsumed_tail(self) -> bytes: ...

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

    A ``deflate`` body is read as zlib-wrapped and, when its first chunk does not decode that way, as raw deflate, as
    httpx's own decoder does, since servers send both under that name.
    """

    def __init__(self, *, coding: ContentCoding, limit: int):
        self.coding = coding
        self.limit = limit
        self._body = bytearray()
        self._decompressor: _Decompressor | None
        # Whether the deflate body may still turn out to be raw deflate, until a chunk has decoded.
        self._is_first_deflate_attempt = False
        match coding:
            case ContentCoding.IDENTITY:
                self._decompressor = None
            case ContentCoding.GZIP:
                self._decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
            case ContentCoding.DEFLATE:
                self._decompressor = zlib.decompressobj()
                self._is_first_deflate_attempt = True

    def feed(self, *, chunk: bytes) -> None:
        """Decode a raw chunk of the body into the body.

        Raises:
            RemoteFileTooLargeError: The body passes the limit.
            RemoteFileFetchError: The compressed body does not decode.
        """
        if self._decompressor is None:
            self._append(decoded=chunk)
            return
        try:
            self._decompress(decompressor=self._decompressor, data=chunk)
        except zlib.error as exc:
            if not self._is_first_deflate_attempt:
                raise _undecodable_body_error() from exc
            self._is_first_deflate_attempt = False
            self._decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
            try:
                self._decompress(decompressor=self._decompressor, data=chunk)
            except zlib.error as raw_exc:
                raise _undecodable_body_error() from raw_exc
        self._is_first_deflate_attempt = False

    def finish(self) -> bytes:
        """The whole decoded body, once every raw chunk is fed.

        Raises:
            RemoteFileTooLargeError: What the decompressor still held passes the limit.
            RemoteFileFetchError: The compressed body does not decode.
        """
        if self._decompressor is not None:
            try:
                # Every chunk was consumed whole, so only the little the decompressor buffers is left.
                self._append(decoded=self._decompressor.flush())
            except zlib.error as exc:
                raise _undecodable_body_error() from exc
        return bytes(self._body)

    def _decompress(self, *, decompressor: _Decompressor, data: bytes) -> None:
        """Decode ``data``, asking for no more than one byte past what the limit still allows at each step."""
        remaining_input = data
        while remaining_input and not decompressor.eof:
            allowed = self.limit - len(self._body) + 1
            self._append(decoded=decompressor.decompress(remaining_input, allowed))
            remaining_input = decompressor.unconsumed_tail

    def _append(self, *, decoded: bytes) -> None:
        self._body.extend(decoded)
        if len(self._body) > self.limit:
            size = len(self._body)
            msg = f"Could not fetch a remote file: its body passed the {self.limit} bytes a fetch reads, at {size} bytes, so the read stopped"
            raise RemoteFileTooLargeError(msg, limit=self.limit, size=size)
