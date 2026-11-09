"""Run setup refuses a file a step asking for page views is certain to fail on, whatever that step's model reads.

Page views are drawn from a PDF by PDFium, so the rule is the renderer's and not the model's: a Word file given to a
model that reads Word files is still refused. The walk over the entry pipe has its own tests; here the consumers are
given, and only the comparison with the file inputs is exercised.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import PipelineInputFormatUnsupportedError
from pipelex.pipeline.file_input_consumers import FileConsumerKind, FileInputConsumer, check_file_inputs_against_consumers
from pipelex.pipeline.input_normalizer import FileInputKind, IdentifiedFileInput
from pipelex.tools.uri.resolved_uri import UriKind

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
HTML_MIME = "text/html"
WORD_READING_FORMATS = frozenset({"pdf", "docx"})
PDF_ONLY_FORMATS = frozenset({"pdf"})


def _consumer(
    *,
    asks_for_page_views: bool,
    readable_formats: frozenset[str] | None,
    reads_web_pages: bool = False,
    is_conditional: bool = False,
    model: str | None = "some-model",
) -> FileInputConsumer:
    return FileInputConsumer(
        slot_name="report",
        consumed_path=("report",),
        pipe_ref="domain.extract_report",
        pipe_code="extract_report",
        kind=FileConsumerKind.EXTRACT,
        model=model,
        readable_formats=readable_formats,
        reads_web_pages=reads_web_pages,
        is_conditional=is_conditional,
        asks_for_page_views=asks_for_page_views,
    )


def _file_input(*, mime_type: str | None, uri_kind: UriKind = UriKind.PIPELEX_STORAGE) -> IdentifiedFileInput:
    return IdentifiedFileInput(path=("report",), kind=FileInputKind.DOCUMENT, uri_kind=uri_kind, mime_type=mime_type)


def _check(*, mocker: MockerFixture, consumer: FileInputConsumer, file_input: IdentifiedFileInput) -> None:
    mocker.patch("pipelex.pipeline.file_input_consumers.collect_file_input_consumers", return_value={"report": [consumer]})
    check_file_inputs_against_consumers(entry_pipe=mocker.MagicMock(), file_inputs=[file_input])


class TestFileInputPageViewsCheck:
    def test_a_word_file_is_refused_even_by_a_model_that_reads_word_files(self, mocker: MockerFixture):
        with pytest.raises(PipelineInputFormatUnsupportedError) as exc_info:
            _check(
                mocker=mocker,
                consumer=_consumer(asks_for_page_views=True, readable_formats=WORD_READING_FORMATS),
                file_input=_file_input(mime_type=DOCX_MIME),
            )

        message = exc_info.value.message
        assert "Input 'report' is a Word document (.docx): pipe 'extract_report' asks for page views, which are drawn from a PDF." in message
        assert message.endswith("Give a PDF, or remove page_views from the step.")
        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("params") == {"input": "report", "format": "docx", "model": "pypdfium2"}, wire

    def test_a_pdf_passes(self, mocker: MockerFixture):
        _check(
            mocker=mocker,
            consumer=_consumer(asks_for_page_views=True, readable_formats=PDF_ONLY_FORMATS),
            file_input=_file_input(mime_type=PDF_MIME),
        )

    def test_the_same_word_file_passes_when_the_step_asks_for_no_page_views(self, mocker: MockerFixture):
        _check(
            mocker=mocker,
            consumer=_consumer(asks_for_page_views=False, readable_formats=WORD_READING_FORMATS),
            file_input=_file_input(mime_type=DOCX_MIME),
        )

    def test_a_url_declared_as_a_web_page_is_refused_even_by_a_model_that_fetches_web_pages(self, mocker: MockerFixture):
        """A web-page model skips the format check on an http(s) URL: page views do not."""
        with pytest.raises(PipelineInputFormatUnsupportedError, match=r"is an HTML page \(\.html\): pipe 'extract_report' asks for page views"):
            _check(
                mocker=mocker,
                consumer=_consumer(asks_for_page_views=True, readable_formats=frozenset(), reads_web_pages=True),
                file_input=_file_input(mime_type=HTML_MIME, uri_kind=UriKind.HTTP_URL),
            )

    def test_a_url_of_unknown_format_is_refused_when_the_model_reads_no_pdf(self, mocker: MockerFixture):
        """The `@default-extract-web-page` case: nothing that model reads can give page views, so the file's format does not matter."""
        with pytest.raises(PipelineInputFormatUnsupportedError) as exc_info:
            _check(
                mocker=mocker,
                consumer=_consumer(asks_for_page_views=True, readable_formats=frozenset(), reads_web_pages=True, model="linkup-fetch"),
                file_input=_file_input(mime_type=None, uri_kind=UriKind.HTTP_URL),
            )

        message = exc_info.value.message
        assert (
            "Input 'report': pipe 'extract_report' asks for page views, which are drawn from a PDF, and model 'linkup-fetch' reads web pages."
            in message
        )
        assert message.endswith("Use a model that reads PDFs, or remove page_views from the step.")
        assert exc_info.value.to_problem(view=ProblemView.CALLER).to_wire().get("params") == {
            "input": "report",
            "format": "unknown",
            "model": "pypdfium2",
        }

    def test_a_url_of_unknown_format_passes_when_the_model_reads_pdfs(self, mocker: MockerFixture):
        """It may be a PDF, and setup never fetches a URL: the renderer's own refusal is what judges it."""
        _check(
            mocker=mocker,
            consumer=_consumer(asks_for_page_views=True, readable_formats=PDF_ONLY_FORMATS, reads_web_pages=True),
            file_input=_file_input(mime_type=None, uri_kind=UriKind.HTTP_URL),
        )

    def test_a_conditional_consumer_is_left_to_the_step(self, mocker: MockerFixture):
        _check(
            mocker=mocker,
            consumer=_consumer(asks_for_page_views=True, readable_formats=WORD_READING_FORMATS, is_conditional=True),
            file_input=_file_input(mime_type=DOCX_MIME),
        )

    def test_a_consumer_whose_model_is_unresolved_is_still_refused_a_known_non_pdf(self, mocker: MockerFixture):
        """The rule does not depend on the model, so an opaque one does not shield the file."""
        with pytest.raises(PipelineInputFormatUnsupportedError, match="asks for page views"):
            _check(
                mocker=mocker,
                consumer=_consumer(asks_for_page_views=True, readable_formats=None, model=None),
                file_input=_file_input(mime_type=DOCX_MIME),
            )

    def test_a_consumer_whose_model_is_unresolved_leaves_an_unknown_format_alone(self, mocker: MockerFixture):
        _check(
            mocker=mocker,
            consumer=_consumer(asks_for_page_views=True, readable_formats=None, model=None),
            file_input=_file_input(mime_type=None),
        )

    def test_a_format_refusal_and_a_page_views_refusal_each_give_their_own_advice(self, mocker: MockerFixture):
        format_refused = _consumer(asks_for_page_views=False, readable_formats=PDF_ONLY_FORMATS)
        page_views_refused = _consumer(asks_for_page_views=True, readable_formats=WORD_READING_FORMATS)
        mocker.patch(
            "pipelex.pipeline.file_input_consumers.collect_file_input_consumers",
            return_value={"report": [format_refused, page_views_refused]},
        )

        with pytest.raises(PipelineInputFormatUnsupportedError) as exc_info:
            check_file_inputs_against_consumers(entry_pipe=mocker.MagicMock(), file_inputs=[_file_input(mime_type=DOCX_MIME)])

        message = exc_info.value.message
        assert message.endswith(
            "Give a file in a format its model reads, or use a model that reads this format. Give a PDF, or remove page_views from the step."
        )
