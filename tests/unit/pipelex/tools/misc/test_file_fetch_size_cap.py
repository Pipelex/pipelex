import gzip
import json
import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.config import get_config
from pipelex.errors.problem import ProblemView
from pipelex.tools.misc.exceptions import RemoteFileFetchError, RemoteFileTooLargeError
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx, fetch_file_from_url_httpx, fetching_for_input

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


def _transport_streaming(stream: httpx.AsyncByteStream, headers: dict[str, str] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(200, headers=headers, stream=stream))


def _transport_answering(content: bytes, headers: dict[str, str] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(200, content=content, headers=headers))


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

    async def test_a_caller_s_cap_overrides_the_configured_one(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().runtime.network, "max_fetch_bytes", 1500)

        raw_bytes = await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=2000, transport=_transport_streaming(_CountingStream(chunk_count=2)))
        assert len(raw_bytes) == 2000

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await fetch_file_from_url_httpx(url=SIGNED_URL, max_bytes=500, transport=_transport_streaming(_CountingStream(chunk_count=2)))
        assert exc_info.value.limit == 500

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
