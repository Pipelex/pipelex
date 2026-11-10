from datetime import UTC, datetime, timedelta

from pytest_mock import MockerFixture

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import NodeKind
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.tools.document_conversion.readable_pdf import PdfOrigin, ReadablePdf
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import FileConvertedEvent
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config

_PIPELINE_RUN_ID = "run_file_conversion_001"
_GRAPH_ID = "graph-file-conversion"
_T0 = datetime(2026, 11, 10, 9, 0, 0, tzinfo=UTC)
_MADE_PDF = ReadablePdf(
    pdf_uri="pipelex-storage://run/assets/report.docx.pdf",
    origin=PdfOrigin.MADE,
    converter_name="gotenberg",
    converter_version="gotenberg-8.40.0",
    page_count=2,
    conversion_seconds=1.25,
)


def _make_tracer() -> tuple[GraphTracer, TraceContext, InMemoryEventLog]:
    event_log = InMemoryEventLog()
    tracer = GraphTracer()
    context = tracer.setup(
        graph_id=_GRAPH_ID,
        data_inclusion=make_defaulted_data_inclusion_config(),
        event_log=event_log,
        pipeline_run_id=_PIPELINE_RUN_ID,
        run_mode=PipeRunMode.LIVE,
    )
    return tracer, context, event_log


class TestGraphTracerFileConversionEvents:
    def test_a_conversion_is_recorded_on_the_step_and_the_graph_still_assembles(self) -> None:
        tracer, context, event_log = _make_tracer()
        step_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.extract_report",
            trace_context=context,
            pipe_code="extract_report",
            pipe_type="PipeExtract",
            node_kind=NodeKind.OPERATOR,
            started_at=_T0,
        )

        tracer.register_file_conversion(node_id=step_id, input_name="report", format_key="docx", readable_pdf=_MADE_PDF)
        tracer.on_pipe_end_success(node_id=step_id, ended_at=_T0 + timedelta(seconds=2))
        tracer.teardown()

        events = event_log.read_events(_PIPELINE_RUN_ID)
        conversions = [event for event in events if isinstance(event, FileConvertedEvent)]
        assert len(conversions) == 1
        conversion = conversions[0]
        assert (conversion.node_id, conversion.input_name, conversion.format_key) == (step_id, "report", "docx")
        assert (conversion.origin, conversion.converter_name, conversion.converter_version) == (PdfOrigin.MADE, "gotenberg", "gotenberg-8.40.0")
        assert (conversion.page_count, conversion.conversion_seconds) == (2, 1.25)
        assert conversion.path == "tests.extract_report"
        assert conversion.mode == PipeRunMode.LIVE
        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)
        assert [node.node_id for node in graph_spec.nodes] == [step_id]

    def test_a_conversion_on_a_node_the_tracer_never_started_is_not_recorded(self) -> None:
        tracer, _context, event_log = _make_tracer()

        tracer.register_file_conversion(node_id="someone-elses-node", input_name="report", format_key="docx", readable_pdf=_MADE_PDF)

        assert not [event for event in event_log.read_events(_PIPELINE_RUN_ID) if isinstance(event, FileConvertedEvent)]

    def test_the_manager_routes_a_conversion_to_the_run_tracer(self, mocker: MockerFixture) -> None:
        manager = GraphTracerManager()
        tracer = mocker.MagicMock()
        mocker.patch.object(manager, "_get_tracer", return_value=tracer)

        manager.register_file_conversion(lookup_key=_GRAPH_ID, node_id="step", input_name=None, format_key="xlsx", readable_pdf=_MADE_PDF)

        tracer.register_file_conversion.assert_called_once_with(node_id="step", input_name=None, format_key="xlsx", readable_pdf=_MADE_PDF)
