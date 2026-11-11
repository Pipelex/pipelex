from collections.abc import Callable

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.tools.document_conversion.exceptions import (
    ConversionLimitKind,
    DocumentConverterAnswerError,
    DocumentConverterMisconfiguredError,
    DocumentConverterUnavailableError,
    DocumentFormatNotConvertibleError,
    DocumentTooLargeToConvertError,
    DocumentUnreadableByConverterError,
)
from pipelex.tools.document_conversion.gotenberg_converter import (
    CONVERTER_VERSION_HEADER,
    GOTENBERG_CONVERTER_NAME,
    UNAVAILABLE_RETRY_DELAYS_SECONDS,
    GotenbergConverter,
)

BASE_URL = "http://gotenberg.test:3000"
PDF_BYTES = b"%PDF-1.7\nthe pdf"
SOURCE_BYTES = b"PK\x03\x04 an office file"
BUDGET_SECONDS = 120.0
MAX_SOURCE_BYTES = 1_000
NO_PAUSES = (0.0, 0.0, 0.0)
GOTENBERG_VERSION = "9.2.0"

Answer = httpx.Response | Exception


class _ScriptedGotenberg:
    """A Gotenberg that answers each request with the next answer of its script, and keeps every request it was sent."""

    def __init__(self, *, answers: list[Answer]) -> None:
        self.answers = list(answers)
        self.convert_requests: list[httpx.Request] = []
        self.other_requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/forms/libreoffice/convert":
            self.other_requests.append(request)
            return httpx.Response(404, text="not a route this test expects")
        self.convert_requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _make_converter(
    *,
    gotenberg: _ScriptedGotenberg,
    unavailable_retry_delays_seconds: tuple[float, ...] = NO_PAUSES,
) -> GotenbergConverter:
    return GotenbergConverter(
        base_url=f"{BASE_URL}/",
        timeout_seconds=360,
        budget_seconds=BUDGET_SECONDS,
        max_source_bytes=MAX_SOURCE_BYTES,
        transport=httpx.MockTransport(gotenberg.handle),
        unavailable_retry_delays_seconds=unavailable_retry_delays_seconds,
    )


def _pdf(*, version: str | None = GOTENBERG_VERSION) -> httpx.Response:
    """A `200` carrying the PDF, naming `version` in its `Gotenberg-Version` header, or no version when None."""
    headers = {CONVERTER_VERSION_HEADER: version} if version is not None else {}
    return httpx.Response(200, content=PDF_BYTES, headers=headers)


def _status(status: int) -> httpx.Response:
    return httpx.Response(status, text="an answer")


def _patch_elapsed(*, mocker: MockerFixture, elapsed: float) -> None:
    """Make every attempt read as having lasted `elapsed` seconds."""
    readings = iter([0.0, elapsed] * 10)
    mocker.patch("pipelex.tools.document_conversion.gotenberg_converter.monotonic", side_effect=lambda: next(readings))


@pytest.mark.asyncio(loop_scope="class")
class TestGotenbergConverter:
    async def test_a_200_is_the_pdf_posted_as_document_with_its_format_key(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[_pdf()])
        converter = _make_converter(gotenberg=gotenberg)

        converted = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="DOCX")

        assert converted.pdf_bytes == PDF_BYTES
        assert converted.converter_name == GOTENBERG_CONVERTER_NAME
        assert converted.converter_version == GOTENBERG_VERSION
        assert len(gotenberg.convert_requests) == 1
        request = gotenberg.convert_requests[0]
        assert request.method == "POST"
        assert str(request.url) == f"{BASE_URL}/forms/libreoffice/convert"
        body = request.read()
        assert b'name="files"; filename="document.docx"' in body
        assert SOURCE_BYTES in body
        # The version comes with the PDF: nothing else is asked.
        assert gotenberg.other_requests == []

    async def test_each_pdf_is_stamped_with_the_version_its_own_answer_names(self) -> None:
        """A converter redeployed between two conversions stamps the second PDF with its new version, as the platform does."""
        gotenberg = _ScriptedGotenberg(answers=[_pdf(version="9.2.0"), _pdf(version=" 9.3.1 ")])
        converter = _make_converter(gotenberg=gotenberg)

        first = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="xlsx")
        second = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="pptx")

        assert first.converter_version == "9.2.0"
        assert second.converter_version == "9.3.1"
        assert gotenberg.other_requests == []

    async def test_a_retried_conversion_is_stamped_with_the_version_of_the_answer_that_carried_the_pdf(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[httpx.Response(500, headers={CONVERTER_VERSION_HEADER: "9.2.0"}), _pdf(version="9.3.1")])
        converter = _make_converter(gotenberg=gotenberg)

        converted = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="docx")

        assert converted.converter_version == "9.3.1"

    @pytest.mark.parametrize("version", [None, "", "   "], ids=["no-header", "empty", "blank"])
    async def test_a_pdf_whose_answer_names_no_version_is_a_misconfigured_converter_and_final(self, version: str | None) -> None:
        """Gotenberg before 8.39.0, or a proxy stripping the header, answers so: a fault of the deployment, for its operator."""
        gotenberg = _ScriptedGotenberg(answers=[_pdf(version=version)])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentConverterMisconfiguredError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="docx")

        assert len(gotenberg.convert_requests) == 1
        error = exc_info.value
        assert CONVERTER_VERSION_HEADER in error.message
        assert "Gotenberg 8.39.0 or later" in error.message
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.RUNTIME_MISCONFIGURED
        assert problem.diagnostics is not None
        assert problem.diagnostics.params == {"component": "runtime.document_conversion"}

    @pytest.mark.parametrize("status", [400, 422, 500, 504])
    async def test_a_first_unreadable_answer_is_tried_once_more(self, status: int) -> None:
        gotenberg = _ScriptedGotenberg(answers=[_status(status), _pdf()])
        converter = _make_converter(gotenberg=gotenberg)

        converted = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="docx")

        assert converted.pdf_bytes == PDF_BYTES
        assert len(gotenberg.convert_requests) == 2

    @pytest.mark.parametrize("status", [400, 422, 500, 504])
    async def test_a_second_unreadable_answer_is_the_file_unreadable(self, status: int) -> None:
        gotenberg = _ScriptedGotenberg(answers=[_status(status), _status(status)])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentUnreadableByConverterError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="doc")

        assert len(gotenberg.convert_requests) == 2
        problem = exc_info.value.with_input(input_name="contract").to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.INPUT_FILE_UNREADABLE
        assert problem.params is not None
        assert problem.params.as_wire() == {"input": "contract", "file_type": "doc", "reason": "conversion_failed"}

    async def test_a_413_is_the_file_too_large_and_final(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[_status(413)])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="xlsx")

        assert len(gotenberg.convert_requests) == 1
        assert exc_info.value.limit_kind == ConversionLimitKind.BYTES
        problem = exc_info.value.with_input(input_name="budget").to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.INPUT_TOO_LARGE
        assert problem.params is not None
        # The converter's own limit is not known, and the runtime's was checked before sending: no limit is invented.
        assert exc_info.value.limit is None
        assert problem.params.as_wire() == {"input": "budget", "size": len(SOURCE_BYTES)}
        assert problem.detail == f"The input 'budget' reaches {len(SOURCE_BYTES)}, past what the step that reads it accepts."

    async def test_a_503_is_the_conversion_out_of_time_and_final(self, mocker: MockerFixture) -> None:
        _patch_elapsed(mocker=mocker, elapsed=124.0)
        gotenberg = _ScriptedGotenberg(answers=[_status(503)])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="xlsx")

        assert len(gotenberg.convert_requests) == 1
        error = exc_info.value
        assert error.resolve_error_code() == CoreCode.INPUT_TOO_LARGE
        assert error.limit_kind == ConversionLimitKind.SECONDS
        assert (error.limit, error.size) == (120, 124)
        assert "time limit of 120 seconds" in error.message
        # Seconds would read as a size in the code's sentence: the problem withholds them and says the file was too slow.
        problem = error.with_input(input_name="budget").to_problem(view=ProblemView.CALLER)
        assert problem.params is not None
        assert problem.params.as_wire() == {"input": "budget"}
        assert problem.detail == "The input 'budget' is too large for the step that reads it, in size or in the time it takes to process."
        assert problem.next_step.detail == "Make the input 'budget' smaller or simpler, then send the request again."

    async def test_a_429_is_tried_again_after_a_pause(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[_status(429), _pdf()])
        converter = _make_converter(gotenberg=gotenberg)

        converted = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="pptx")

        assert converted.pdf_bytes == PDF_BYTES
        assert len(gotenberg.convert_requests) == 2

    async def test_the_pauses_are_the_default_delays(self, mocker: MockerFixture) -> None:
        sleep = mocker.patch("pipelex.tools.document_conversion.gotenberg_converter.asyncio.sleep", new=mocker.AsyncMock())
        gotenberg = _ScriptedGotenberg(answers=[_status(429)] * (len(UNAVAILABLE_RETRY_DELAYS_SECONDS) + 1))
        converter = _make_converter(gotenberg=gotenberg, unavailable_retry_delays_seconds=UNAVAILABLE_RETRY_DELAYS_SECONDS)

        with pytest.raises(DocumentConverterUnavailableError):
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="pptx")

        assert [call.args[0] for call in sleep.await_args_list] == list(UNAVAILABLE_RETRY_DELAYS_SECONDS)

    @pytest.mark.parametrize(
        "make_answer",
        [
            lambda: _status(429),
            lambda: _status(404),
            lambda: httpx.ConnectError("connection refused"),
            lambda: httpx.ConnectTimeout("connect timed out"),
            lambda: httpx.RemoteProtocolError("server disconnected without sending a response"),
        ],
        ids=["429", "other-status", "connection-refused", "connect-timeout", "dropped-before-budget"],
    )
    async def test_an_answer_saying_nothing_about_the_file_is_tried_a_few_times_then_unavailable(self, make_answer: Callable[[], Answer]) -> None:
        nb_attempts = len(NO_PAUSES) + 1
        gotenberg = _ScriptedGotenberg(answers=[make_answer() for _ in range(nb_attempts)])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentConverterUnavailableError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="odt")

        assert len(gotenberg.convert_requests) == nb_attempts
        problem = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.RUNTIME_UNAVAILABLE
        assert problem.diagnostics is not None
        assert problem.diagnostics.params == {"dependency": "document_converter"}

    @pytest.mark.parametrize(
        "make_error",
        [
            lambda: httpx.RemoteProtocolError("server disconnected without sending a response"),
            lambda: httpx.ReadTimeout("read timed out"),
        ],
        ids=["dropped-after-budget", "read-timeout"],
    )
    async def test_a_connection_ending_after_the_budget_is_the_conversion_out_of_time(
        self, mocker: MockerFixture, make_error: Callable[[], Exception]
    ) -> None:
        _patch_elapsed(mocker=mocker, elapsed=300.0)
        gotenberg = _ScriptedGotenberg(answers=[make_error()])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="ods")

        assert len(gotenberg.convert_requests) == 1
        assert exc_info.value.limit_kind == ConversionLimitKind.SECONDS
        assert (exc_info.value.limit, exc_info.value.size) == (120, 300)

    async def test_a_200_that_is_not_a_pdf_is_a_fault_of_the_converter(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[httpx.Response(200, content=b"<html>not a pdf</html>")])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentConverterAnswerError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="odp")
        assert exc_info.value.resolve_error_code() == CoreCode.RUNTIME_UNEXPECTED

    async def test_a_source_past_the_limit_is_refused_before_anything_is_sent(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await converter.convert_to_pdf(data=b"x" * (MAX_SOURCE_BYTES + 1), format_key="xls")

        assert gotenberg.convert_requests == []
        assert (exc_info.value.limit, exc_info.value.size) == (MAX_SOURCE_BYTES, MAX_SOURCE_BYTES + 1)

    async def test_a_format_the_runtime_does_not_convert_is_refused(self) -> None:
        gotenberg = _ScriptedGotenberg(answers=[])
        converter = _make_converter(gotenberg=gotenberg)

        with pytest.raises(DocumentFormatNotConvertibleError):
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="pdf")
        assert gotenberg.convert_requests == []
