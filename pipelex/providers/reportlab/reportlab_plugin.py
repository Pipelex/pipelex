from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.render_job import DocumentRendererProtocol
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar

REPORTLAB_ENGINE = "reportlab"


def _make_reportlab_pdf_renderer() -> DocumentRendererProtocol:
    from pipelex.providers.reportlab.reportlab_pdf_renderer import ReportlabPdfRenderer  # ruff: ignore[import-outside-top-level]

    return ReportlabPdfRenderer()


class ReportlabDocGenPlugin:
    """Built-in document engine that prints a `pdf` from the auto-layout of a `PipeDocGen` step's inputs, on ReportLab.

    Registering imports nothing of ReportLab: the factory imports the engine, which imports ReportLab and registers
    its bundled fonts, once per process, the first time a document is printed with it.
    """

    name = "reportlab"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_document_renderer(
            doc_gen_format=DocGenFormat.PDF,
            source=DocGenSource.LAYOUT,
            engine=REPORTLAB_ENGINE,
            make_renderer=_make_reportlab_pdf_renderer,
        )
