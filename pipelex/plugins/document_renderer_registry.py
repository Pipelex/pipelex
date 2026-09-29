from collections.abc import Callable
from typing import NamedTuple, TypeAlias

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.render_job import DocumentRendererProtocol
from pipelex.cogt.doc_gen.template_check import TemplateCheckerProtocol
from pipelex.plugins.exceptions import DocumentEngineChoiceError

# A plugin's factory for one document engine. Called once per process, the first time a document is printed
# with the engine, never at registration, so an engine's library (ReportLab, WeasyPrint, openpyxl) is imported
# only by a process that prints with it, and only once.
MakeDocumentRendererFn: TypeAlias = Callable[[], DocumentRendererProtocol]


class DocumentRendererKey(NamedTuple):
    doc_gen_format: DocGenFormat
    source: DocGenSource
    engine: str


class DocumentRendererEntry(NamedTuple):
    """One engine's contribution: how to build it, and the template checker it offers, if any."""

    engine: str
    make_renderer: MakeDocumentRendererFn
    check_template: TemplateCheckerProtocol | None
    source_plugin: str


def engine_choice_key(*, doc_gen_format: DocGenFormat, source: DocGenSource) -> str:
    """The key of `runtime.doc_gen.engines` that chooses the engine for a format and a source: 'pdf.layout'."""
    return f"{doc_gen_format}.{source}"


class DocumentRendererRegistry:
    """Read view over the document engines contributed by discovered plugins, keyed by format and source.

    Built once at boot from the registrar's accumulated `document_renderers` and stored on the runtime hub.
    The built-in `ReportlabDocGenPlugin` prints a `pdf` from the layout tree, and the Pipelex document
    generation plugin prints the other formats and sources. A format and source that no installed engine
    prints resolve to None, which `PipeDocGen` refuses when the method loads; when several installed
    engines print them, `runtime.doc_gen.engines` chooses one.
    """

    def __init__(self, *, entries: dict[DocumentRendererKey, DocumentRendererEntry], engine_choices: dict[str, str]):
        self._entries = dict(entries)
        self._engine_choices = dict(engine_choices)
        self._renderers: dict[DocumentRendererKey, DocumentRendererProtocol] = {}

    def resolve(self, *, doc_gen_format: DocGenFormat, source: DocGenSource) -> DocumentRendererEntry | None:
        """The engine that prints a format from a source here, or None when no installed engine does.

        Raises:
            DocumentEngineChoiceError: the configuration chooses an engine that is not installed, or several are
                installed and it chooses none.
        """
        candidates = {key.engine: entry for key, entry in self._entries.items() if key.doc_gen_format == doc_gen_format and key.source == source}
        if not candidates:
            return None
        chosen_engine = self._engine_choices.get(engine_choice_key(doc_gen_format=doc_gen_format, source=source))
        if chosen_engine is not None:
            chosen_entry = candidates.get(chosen_engine)
            if chosen_entry is None:
                raise DocumentEngineChoiceError(
                    doc_gen_format=doc_gen_format, source=source, chosen_engine=chosen_engine, installed_engines=list(candidates)
                )
            return chosen_entry
        if len(candidates) > 1:
            raise DocumentEngineChoiceError(doc_gen_format=doc_gen_format, source=source, chosen_engine=None, installed_engines=list(candidates))
        return next(iter(candidates.values()))

    def get_renderer(self, *, doc_gen_format: DocGenFormat, source: DocGenSource) -> DocumentRendererProtocol | None:
        """The engine instance that prints a format from a source, built on first use and kept for the process."""
        entry = self.resolve(doc_gen_format=doc_gen_format, source=source)
        if entry is None:
            return None
        key = DocumentRendererKey(doc_gen_format=doc_gen_format, source=source, engine=entry.engine)
        renderer = self._renderers.get(key)
        if renderer is None:
            renderer = entry.make_renderer()
            self._renderers[key] = renderer
        return renderer

    @property
    def keys(self) -> list[DocumentRendererKey]:
        return list(self._entries)
