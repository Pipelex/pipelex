"""The Gotenberg backend: an Office file posted to a Gotenberg container, and its answers read as the platform reads them.

The file goes to `POST <url>/forms/libreoffice/convert` as a multipart form, named `document.<format key>`: LibreOffice
reads the extension for the format, and nothing of a person's file name has a reason to reach the converter's logs.
What Gotenberg's answers mean was measured for the platform's converter (pipelex-server's
`doc-convert/docs/operations.md`), and this backend reads them as the platform's `DocConvertClient` does:

- **A `200`** is the PDF, checked to start like one, and stamped with the version Gotenberg names in the
  `Gotenberg-Version` header of that same answer. Read off the answer that carried the PDF, it is the version of the
  process that converted the file, whatever was deployed since. Gotenberg names it on a conversion's answer from
  8.39.0 on: a PDF whose answer names none comes from an older Gotenberg, or through a proxy that strips the header,
  a fault of the deployment, `runtime.misconfigured`, and is never taken.
- **A first `400`, `422`, `500` or `504`** is tried once more: a LibreOffice engine dying mid-conversion answers
  exactly as a damaged file does, and the same file then converts. A second one is the file's own,
  `input.file_unreadable`.
- **`413`** is the file too large, under a limit of the converter's own it does not say, and **`503`** the conversion
  out of its budget, both `input.too_large` and final.
- **`429`**, a connection refused, or one dropped before the converter's budget, says nothing about the file: tried
  again a few times, spaced, then `runtime.unavailable`. So is any other status, such as a `404` from a converter
  that moved.
- **A connection dropped after the budget**, a read timeout included, is a hostile file outrunning it: too slow,
  `input.too_large`, never retried. The client's read timeout allows for the six minutes such a file was measured to
  hold a connection.
"""

import asyncio
from collections.abc import Sequence
from enum import StrEnum
from http import HTTPStatus
from time import monotonic
from typing import NamedTuple

import httpx
from typing_extensions import override

from pipelex import log
from pipelex.tools.document_conversion.document_converter_protocol import (
    PDF_MAGIC,
    ConvertedPdf,
    DocumentConverterProtocol,
    is_convertible_format_key,
)
from pipelex.tools.document_conversion.exceptions import (
    ConversionLimitKind,
    DocumentConverterAnswerError,
    DocumentConverterMisconfiguredError,
    DocumentConverterUnavailableError,
    DocumentFormatNotConvertibleError,
    DocumentTooLargeToConvertError,
    DocumentUnreadableByConverterError,
)

GOTENBERG_CONVERTER_NAME = "gotenberg"

_CONVERT_PATH = "/forms/libreoffice/convert"
# The header Gotenberg names its own version in, such as `9.2.0`: the `converter-version` of its PDFs. Gotenberg sends it
# on a conversion's answer from this version on; older ones send none, and 8.0.0 has no `GET /version` either.
CONVERTER_VERSION_HEADER = "Gotenberg-Version"
MIN_GOTENBERG_VERSION_NAMING_ITSELF = "8.39.0"

# Short, so a converter between tasks costs an attempt seconds and not minutes: the file is posted only once connected.
_CONNECT_TIMEOUT_SECONDS = 10.0
_WRITE_TIMEOUT_SECONDS = 60.0
_POOL_TIMEOUT_SECONDS = 5.0

# The pauses before each new attempt when the converter says nothing about the file: busy, unreachable, or gone
# mid-conversion before its budget. An answer still saying nothing after the last is `runtime.unavailable`.
UNAVAILABLE_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
# How many times a file the converter could not read is posted in all before it is taken as unreadable.
UNREADABLE_ATTEMPTS = 2

# The statuses a bad file ends in, which a dying LibreOffice engine answers too.
_UNREADABLE_STATUSES = frozenset(
    {HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY, HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.GATEWAY_TIMEOUT}
)


class _RetryableAnswerKind(StrEnum):
    """What an attempt's answer that is worth another attempt says."""

    # Nothing about the file: the converter busy, unreachable, gone mid-conversion, or answering a status that is not
    # about files. Tried again after each pause of the backend's retry delays.
    UNAVAILABLE = "unavailable"
    # The converter could not read the file, which a dying engine answers too. Tried once more, at once.
    UNREADABLE = "unreadable"


class _RetryableAnswer(NamedTuple):
    """An attempt's answer worth another attempt, and what to say if it is the last."""

    kind: _RetryableAnswerKind
    message: str


class GotenbergConverter(DocumentConverterProtocol):
    """Converts an Office file through the Gotenberg container at `base_url`."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        budget_seconds: float,
        max_source_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
        unavailable_retry_delays_seconds: Sequence[float] = UNAVAILABLE_RETRY_DELAYS_SECONDS,
    ) -> None:
        """Set up the backend; nothing is sent until the first conversion.

        Args:
            base_url: The container's base URL, such as `http://localhost:3000`.
            timeout_seconds: How long to wait for Gotenberg's answer to one post.
            budget_seconds: Gotenberg's own budget for a conversion, its `--api-timeout`.
            max_source_bytes: The largest file posted; a larger one is refused before anything is sent.
            transport: The HTTP transport, for tests; None for the network.
            unavailable_retry_delays_seconds: The pauses before each new attempt when an answer says nothing about the file.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS, read=timeout_seconds, write=_WRITE_TIMEOUT_SECONDS, pool=_POOL_TIMEOUT_SECONDS
        )
        self._budget_seconds = budget_seconds
        self._max_source_bytes = max_source_bytes
        self._transport = transport
        self._unavailable_retry_delays_seconds = tuple(unavailable_retry_delays_seconds)

    @property
    @override
    def converter_name(self) -> str:
        return GOTENBERG_CONVERTER_NAME

    def _make_client(self) -> httpx.AsyncClient:
        # One client per operation: a backend lives for the process, and an activity may run each step on another loop.
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout)

    async def _pause_or_give_up(self, *, answer: _RetryableAnswer, nb_pauses: int) -> None:
        """Pause before the next attempt after an answer that said nothing about the file, or give up after the last.

        Raises:
            DocumentConverterUnavailableError: Every attempt's answer said nothing about the file.
        """
        if nb_pauses >= len(self._unavailable_retry_delays_seconds):
            msg = f"The document converter was unavailable on each of {nb_pauses + 1} attempts; the last: {answer.message}"
            raise DocumentConverterUnavailableError(msg)
        log.debug(f"Gotenberg said nothing about the file on attempt {nb_pauses + 1}: {answer.message}")
        await asyncio.sleep(self._unavailable_retry_delays_seconds[nb_pauses])

    @override
    async def convert_to_pdf(self, *, data: bytes, format_key: str) -> ConvertedPdf:
        if not is_convertible_format_key(format_key=format_key):
            msg = f"The format '{format_key}' is not one the runtime converts to a PDF."
            raise DocumentFormatNotConvertibleError(msg)
        normalized_format_key = format_key.lower()
        if len(data) > self._max_source_bytes:
            msg = f"The file of {len(data)} bytes is past the converter's limit of {self._max_source_bytes} bytes: it was not sent."
            raise DocumentTooLargeToConvertError(
                msg, format_key=normalized_format_key, limit_kind=ConversionLimitKind.BYTES, limit=self._max_source_bytes, size=len(data)
            )
        nb_unreadable_answers = 0
        nb_pauses = 0
        while True:
            outcome = await self._post_once(data=data, format_key=normalized_format_key)
            if isinstance(outcome, ConvertedPdf):
                return outcome
            match outcome.kind:
                case _RetryableAnswerKind.UNREADABLE:
                    nb_unreadable_answers += 1
                    if nb_unreadable_answers >= UNREADABLE_ATTEMPTS:
                        raise DocumentUnreadableByConverterError(outcome.message, format_key=normalized_format_key)
                    log.debug(f"Gotenberg could not read the file, trying once more: {outcome.message}")
                case _RetryableAnswerKind.UNAVAILABLE:
                    await self._pause_or_give_up(answer=outcome, nb_pauses=nb_pauses)
                    nb_pauses += 1

    async def _post_once(self, *, data: bytes, format_key: str) -> ConvertedPdf | _RetryableAnswer:
        """Post the file once: the PDF and the version its answer names, or an answer worth another attempt.

        Raises:
            DocumentTooLargeToConvertError: The file is too large, or its conversion outran its budget.
            DocumentConverterAnswerError: The converter answered `200` with something that is not a PDF.
            DocumentConverterMisconfiguredError: The converter answered a PDF without naming its version.
        """
        files = {"files": (f"document.{format_key}", data, "application/octet-stream")}
        started = monotonic()
        async with self._make_client() as client:
            try:
                response = await client.post(f"{self._base_url}{_CONVERT_PATH}", files=files)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                msg = f"The converter could not be reached: {type(exc).__name__}."
                return _RetryableAnswer(kind=_RetryableAnswerKind.UNAVAILABLE, message=msg)
            except httpx.TransportError as exc:
                return self._closed_connection(exc=exc, elapsed=monotonic() - started, format_key=format_key)
        return self._read_answer(response=response, elapsed=monotonic() - started, data_size=len(data), format_key=format_key)

    def _closed_connection(self, *, exc: httpx.TransportError, elapsed: float, format_key: str) -> _RetryableAnswer:
        """What a connection that ended with no answer means, by when it ended.

        Raises:
            DocumentTooLargeToConvertError: It ended after the converter's budget: the file outran it.
        """
        if elapsed >= self._budget_seconds:
            msg = (
                f"The conversion ran past its time limit of {self._budget_seconds:.0f} seconds: the connection ended with no answer "
                f"{elapsed:.0f} seconds in ({type(exc).__name__})."
            )
            raise DocumentTooLargeToConvertError(
                msg, format_key=format_key, limit_kind=ConversionLimitKind.SECONDS, limit=round(self._budget_seconds), size=round(elapsed)
            ) from exc
        msg = f"The connection ended with no answer {elapsed:.0f} seconds in, before the converter's budget: {type(exc).__name__}."
        return _RetryableAnswer(kind=_RetryableAnswerKind.UNAVAILABLE, message=msg)

    def _read_answer(self, *, response: httpx.Response, elapsed: float, data_size: int, format_key: str) -> ConvertedPdf | _RetryableAnswer:
        """The PDF of a `200` and the version its answer names, or an answer worth another attempt.

        Raises:
            DocumentTooLargeToConvertError: The file is too large, or its conversion ran out of time.
            DocumentConverterAnswerError: A `200` that is not a PDF.
            DocumentConverterMisconfiguredError: A `200` whose answer names no version: a Gotenberg older than 8.39.0,
                or a proxy stripping the header.
        """
        status = response.status_code
        log.debug(f"Gotenberg answered status {status} after {elapsed:.1f} seconds with {len(response.content)} bytes")
        match status:
            case HTTPStatus.OK:
                if not response.content.startswith(PDF_MAGIC):
                    msg = f"The converter answered 200 with {len(response.content)} bytes that are not a PDF."
                    raise DocumentConverterAnswerError(msg)
                converter_version = response.headers.get(CONVERTER_VERSION_HEADER, "").strip()
                if not converter_version:
                    msg = (
                        f"The converter answered a PDF without naming its version in the {CONVERTER_VERSION_HEADER} header, "
                        f"which Gotenberg {MIN_GOTENBERG_VERSION_NAMING_ITSELF} or later sends: upgrade the converter, "
                        "or stop the proxy in front of it from stripping the header."
                    )
                    raise DocumentConverterMisconfiguredError(msg)
                return ConvertedPdf(pdf_bytes=response.content, converter_name=GOTENBERG_CONVERTER_NAME, converter_version=converter_version)
            case HTTPStatus.TOO_MANY_REQUESTS:
                msg = "The converter's queue is full (429)."
                return _RetryableAnswer(kind=_RetryableAnswerKind.UNAVAILABLE, message=msg)
            case HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
                # Under a limit of the converter's own, which it does not say: the runtime's cap was checked before sending.
                msg = f"The converter refused the file of {data_size} bytes as too large (413), under a limit of its own."
                raise DocumentTooLargeToConvertError(msg, format_key=format_key, limit_kind=ConversionLimitKind.BYTES, limit=None, size=data_size)
            case HTTPStatus.SERVICE_UNAVAILABLE:
                msg = (
                    f"The conversion ran past its time limit of {self._budget_seconds:.0f} seconds: "
                    f"the converter gave up after {elapsed:.0f} seconds (503)."
                )
                raise DocumentTooLargeToConvertError(
                    msg, format_key=format_key, limit_kind=ConversionLimitKind.SECONDS, limit=round(self._budget_seconds), size=round(elapsed)
                )
            case _ if status in _UNREADABLE_STATUSES:
                msg = f"The converter could not read the file: status {status}."
                return _RetryableAnswer(kind=_RetryableAnswerKind.UNREADABLE, message=msg)
            case _:
                msg = f"The converter answered status {status}, which says nothing about the file."
                return _RetryableAnswer(kind=_RetryableAnswerKind.UNAVAILABLE, message=msg)
