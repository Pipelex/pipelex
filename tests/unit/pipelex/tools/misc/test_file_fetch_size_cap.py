import gzip
import json
import logging
import os
from collections.abc import AsyncIterator

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.config import get_config
from pipelex.errors.problem import ProblemView
from pipelex.tools.misc.bounded_body_decoder import raw_bound_of
from pipelex.tools.misc.exceptions import RemoteFileFetchError, RemoteFileSizeBound, RemoteFileTooLargeError
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx, fetch_file_from_url_httpx, fetching_for_input
from tests.unit.pipelex.tools.misc.served_response import served_response

SIGNED_URL = "https://files.example.com/reports/confidential-patient-diagnosis.pdf?token=secret-token-4471"
CHUNK_SIZE = 1000


class _CountingStream(httpx.AsyncByteStream):
    """A body served in chunks, which counts the chunks a reader took, endless when ``chunk_count`` is ``None``."""

    def __init__(self, *, chunk_count: int | None, chunk: bytes = b"x" * CHUNK_SIZE, failure: httpx.RequestError | None = None):
        self.chunk_count = chunk_count
        self.chunk = chunk
        self.failure = failure
        self.chunks_served = 0

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        while self.chunk_count is None or self.chunks_served < self.chunk_count:
            self.chunks_served += 1
            yield self.chunk
        if self.failure is not None:
            raise self.failure


class _PrefixedStream(httpx.AsyncByteStream):
    """A body served as ``prefix``, then as what ``rest`` serves."""

    def __init__(self, *, prefix: bytes, rest: httpx.AsyncByteStream):
        self.prefix = prefix
        self.rest = rest

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.prefix
        async for chunk in self.rest:
            yield chunk


def _transport_streaming(stream: httpx.AsyncByteStream, headers: dict[str, str] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(200, headers=headers, stream=stream))


def _transport_answering(content: bytes, headers: dict[str, str] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: served_response(content=content, headers=headers))


@pytest.mark.asyncio(loop_scope="class")
class TestFileFetchSizeCap:
    @pytest.mark.builds_problems_without_required_params(reason="the URL fetch knows not the input the URL came from")
    async def test_a_declared_length_past_the_cap_is_refused_before_the_body_is_read(self) -> None:
        stream = _CountingStream(chunk_count=5)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL,
                max_bytes=4999,
                transport=_transport_streaming(stream, headers={"Content-Length": "5000"}),
            )

        error = exc_info.value
        assert stream.chunks_served == 0
        assert (error.limit, error.size) == (4999, 5000)
        assert error.resolve_error_code() == CoreCode.INPUT_TOO_LARGE
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.domain == ProblemDomain.INPUT
        assert caller.is_retryable is False
        assert caller.params is not None
        assert caller.params.as_wire() == {"limit": 4999, "size": 5000}

    async def test_an_endless_body_is_cut_off_once_it_passes_the_cap(self) -> None:
        stream = _CountingStream(chunk_count=None)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=4500, transport=_transport_streaming(stream))

        assert stream.chunks_served == 5
        assert (exc_info.value.limit, exc_info.value.size) == (4500, 5000)

    async def test_a_compressed_body_is_counted_once_decoded(self) -> None:
        """A gzip bomb's wire size is under the cap; the bytes it decodes to are not, and those are what the cap counts."""
        decoded = b"\0" * 50_000
        encoded = gzip.compress(decoded)
        assert len(encoded) < 10_000

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL,
                max_bytes=10_000,
                transport=_transport_answering(encoded, headers={"Content-Encoding": "gzip"}),
            )

        assert exc_info.value.limit == 10_000
        assert exc_info.value.size > 10_000

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({"Content-Length": "3000"}, id="declared"),
            pytest.param(None, id="undeclared"),
        ],
    )
    async def test_a_body_exactly_at_the_cap_is_returned_whole(self, headers: dict[str, str] | None) -> None:
        stream = _CountingStream(chunk_count=3)

        raw_bytes, _ = await fetch_file_and_content_type_from_url_httpx(
            SIGNED_URL, max_bytes=3000, transport=_transport_streaming(stream, headers=headers)
        )

        assert raw_bytes == b"x" * 3000

    @pytest.mark.parametrize(
        ("chunk_count", "is_refused"),
        [
            pytest.param(2, False, id="under-the-cap"),
            pytest.param(4, True, id="past-the-cap"),
        ],
    )
    async def test_a_malformed_declared_length_falls_through_to_the_bytes_read(self, chunk_count: int, is_refused: bool) -> None:
        stream = _CountingStream(chunk_count=chunk_count)
        transport = _transport_streaming(stream, headers={"Content-Length": "a lot"})

        if is_refused:
            with pytest.raises(RemoteFileTooLargeError) as exc_info:
                await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=3000, transport=transport)
            assert exc_info.value.size == 4000
        else:
            raw_bytes = await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=3000, transport=transport)
            assert len(raw_bytes) == 2000

    async def test_the_configured_cap_applies_when_the_caller_names_none(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.network, "max_fetch_bytes", 1500)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, transport=_transport_streaming(_CountingStream(chunk_count=2)))

        assert (exc_info.value.limit, exc_info.value.size) == (1500, 2000)

    async def test_a_caller_s_cap_never_loosens_the_configured_one(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.network, "max_fetch_bytes", 1500)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=2000, transport=_transport_streaming(_CountingStream(chunk_count=2)))

        assert (exc_info.value.limit, exc_info.value.size) == (1500, 2000)

    async def test_a_tighter_caller_s_cap_wins(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.network, "max_fetch_bytes", 1500)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=500, transport=_transport_streaming(_CountingStream(chunk_count=2)))

        assert exc_info.value.limit == 500

    async def test_a_redirect_is_followed_without_reading_its_body(self) -> None:
        """Each hop's body would be read whole and uncapped if httpx followed the redirects itself."""
        hop_body = _CountingStream(chunk_count=50)

        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(302, headers={"Location": "https://files.example.com/final"}, stream=hop_body)
            return served_response(content=b"the file")

        raw_bytes = await fetch_file_from_url_httpx(url="https://files.example.com/start", max_bytes=1000, transport=httpx.MockTransport(_handler))

        assert raw_bytes == b"the file"
        assert hop_body.chunks_served == 0

    async def test_a_redirect_loop_is_refused_past_the_client_s_redirect_limit(self) -> None:
        hops: list[str] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            hops.append(request.url.path)
            return httpx.Response(302, headers={"Location": f"https://files.example.com/hop{len(hops)}"})

        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(url="https://files.example.com/start", transport=httpx.MockTransport(_handler))

        assert exc_info.value.reason == "the request failed (TooManyRedirects)"
        assert len(hops) == httpx.AsyncClient().max_redirects + 1

    async def test_only_the_content_codings_the_runtime_decodes_are_asked_for(self) -> None:
        seen: dict[str, str | None] = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            seen["accept-encoding"] = request.headers.get("accept-encoding")
            return served_response(content=b"ok")

        await fetch_file_from_url_httpx(url=SIGNED_URL, transport=httpx.MockTransport(_handler))

        assert seen["accept-encoding"] == "gzip, deflate"

    @pytest.mark.builds_problems_without_required_params(reason="the URL fetch knows not the input the URL came from")
    async def test_stacked_content_codings_are_refused_before_the_body_is_read(self) -> None:
        stream = _CountingStream(chunk_count=3)

        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, transport=_transport_streaming(stream, headers={"Content-Encoding": "gzip, gzip"}))

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert stream.chunks_served == 0
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_FILE_UNREADABLE
        assert caller.params is not None
        assert caller.params.as_wire() == {"reason": "the server answered in a content encoding the runtime does not read"}

    async def test_a_compressed_body_s_declared_length_is_not_held_against_the_decoded_cap(self) -> None:
        """An incompressible gzip body is a little longer on the wire than decoded: only the decoded bytes count."""
        decoded = os.urandom(100_000)
        encoded = gzip.compress(decoded)
        assert len(encoded) > len(decoded)

        raw_bytes = await fetch_file_from_url_httpx(
            url=SIGNED_URL,
            max_bytes=len(decoded),
            transport=_transport_answering(encoded, headers={"Content-Encoding": "gzip"}),
        )

        assert raw_bytes == decoded

    async def test_a_failure_while_the_body_streams_maps_as_before(self) -> None:
        stream = _CountingStream(chunk_count=1, failure=httpx.ReadTimeout("slow"))

        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=10_000, transport=_transport_streaming(stream))

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert exc_info.value.resolve_error_code() == CoreCode.INPUT_URL_UNREACHABLE
        assert exc_info.value.message == "Could not fetch a remote file: the request timed out"

    async def test_the_refusal_names_the_input_its_catch_site_knows_and_never_the_url(self) -> None:
        with pytest.raises(RemoteFileTooLargeError) as exc_info, fetching_for_input(input_name="scan"):
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=1500, transport=_transport_streaming(_CountingStream(chunk_count=None)))

        error = exc_info.value
        assert "1500" in error.message
        assert "2000" in error.message
        caller = error.to_problem(view=ProblemView.CALLER)
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert caller.code == CoreCode.INPUT_TOO_LARGE
        assert caller.params is not None
        assert caller.params.as_wire() == {"input": "scan", "limit": 1500, "size": 2000}
        assert caller.detail == "The input 'scan' reaches 2000, past the limit of 1500."
        for wire in (json.dumps(operator.to_wire()), json.dumps(caller.to_wire())):
            assert "confidential" not in wire
            assert "secret-token" not in wire
            assert "files.example.com" not in wire

    @pytest.mark.builds_problems_without_required_params(
        reason="re-codes a fetch failure by hand, without the provider and the defect a provider's catch site names"
    )
    async def test_a_provider_s_re_code_is_given_no_parameter_it_refuses(self, caplog: pytest.LogCaptureFixture) -> None:
        """`provider.response_invalid`, which a provider's file is re-coded as, declares neither the limit nor the size."""
        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=1500, transport=_transport_streaming(_CountingStream(chunk_count=None)))
        recoded = exc_info.value.with_error_code(CoreCode.PROVIDER_RESPONSE_INVALID)

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            operator = recoded.to_problem(view=ProblemView.OPERATOR)

        assert operator.code == CoreCode.PROVIDER_RESPONSE_INVALID
        assert (operator.params.as_wire() if operator.params is not None else {}) == {}
        assert [record.getMessage() for record in caplog.records if "does not declare" in record.getMessage()] == []

    async def test_junk_after_a_gzip_body_is_refused_without_reading_on(self) -> None:
        """Bytes after a gzip member are read as the next member, so junk there is refused, not consumed uncounted."""
        stream = _CountingStream(chunk_count=50, chunk=b"J" * CHUNK_SIZE)
        stream_with_member = _PrefixedStream(prefix=gzip.compress(b"hello"), rest=stream)

        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL, max_bytes=1000, transport=_transport_streaming(stream_with_member, headers={"Content-Encoding": "gzip"})
            )

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert exc_info.value.reason == "the server answered a compressed body that does not decode"
        assert stream.chunks_served == 1

    @pytest.mark.builds_problems_without_required_params(reason="the URL fetch knows not the input the URL came from")
    async def test_endless_nul_padding_after_a_gzip_body_is_refused_at_the_compressed_bound(self) -> None:
        """NUL padding is skipped, never decoded, so it is the compressed bound that stops it."""
        stream = _CountingStream(chunk_count=None, chunk=b"\x00" * CHUNK_SIZE)
        stream_with_member = _PrefixedStream(prefix=gzip.compress(b"hello"), rest=stream)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL, max_bytes=1000, transport=_transport_streaming(stream_with_member, headers={"Content-Encoding": "gzip"})
            )

        assert exc_info.value.bound == RemoteFileSizeBound.COMPRESSED
        assert stream.chunks_served <= raw_bound_of(limit=1000) // CHUNK_SIZE + 1

    async def test_a_truncated_gzip_body_is_refused(self) -> None:
        """A connection closed mid-body ends a response without a declared length, so the cut stream is what is checked."""
        compressed = gzip.compress(bytes(range(256)) * 400)

        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL,
                transport=_transport_streaming(httpx.ByteStream(compressed[: len(compressed) // 2]), headers={"Content-Encoding": "gzip"}),
            )

        assert not isinstance(exc_info.value, RemoteFileTooLargeError)
        assert exc_info.value.reason == "the server answered a compressed body that does not decode"

    async def test_an_empty_body_labelled_gzip_is_empty(self) -> None:
        raw_bytes = await fetch_file_from_url_httpx(url=SIGNED_URL, transport=_transport_answering(b"", headers={"Content-Encoding": "gzip"}))

        assert raw_bytes == b""

    @pytest.mark.builds_problems_without_required_params(reason="the URL fetch knows not the input the URL came from")
    async def test_a_compressed_body_past_the_raw_bound_is_refused_in_compressed_bytes(self) -> None:
        """Limit and size are both compressed bytes when it is the compressed input that passed its bound."""
        endless_header = _PrefixedStream(prefix=b"\x1f\x8b\x08\x08\x00\x00\x00\x00\x00\x03", rest=_CountingStream(chunk_count=None))

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL, max_bytes=1000, transport=_transport_streaming(endless_header, headers={"Content-Encoding": "gzip"})
            )

        error = exc_info.value
        assert error.bound == RemoteFileSizeBound.COMPRESSED
        assert error.limit == raw_bound_of(limit=1000)
        assert error.size > error.limit
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.params is not None
        assert caller.params.as_wire() == {"limit": raw_bound_of(limit=1000), "size": error.size}

    @pytest.mark.builds_problems_without_required_params(reason="the URL fetch knows not the input the URL came from")
    async def test_a_compressed_body_declaring_more_than_the_raw_bound_is_refused_unread(self) -> None:
        stream = _CountingStream(chunk_count=5)

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(
                url=SIGNED_URL,
                max_bytes=1000,
                transport=_transport_streaming(stream, headers={"Content-Encoding": "gzip", "Content-Length": "5000000000"}),
            )

        error = exc_info.value
        assert stream.chunks_served == 0
        assert (error.bound, error.limit, error.size) == (RemoteFileSizeBound.COMPRESSED, raw_bound_of(limit=1000), 5_000_000_000)

    async def test_a_decoded_refusal_names_the_decoded_bound(self) -> None:
        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=1500, transport=_transport_streaming(_CountingStream(chunk_count=2)))

        assert exc_info.value.bound == RemoteFileSizeBound.DECODED
