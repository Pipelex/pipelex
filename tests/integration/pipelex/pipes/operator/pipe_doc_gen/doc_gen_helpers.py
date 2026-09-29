from pathlib import Path

import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.render_job import RenderedDocument, RenderJob, RenderResources
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest, TemplateFinding
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.plugins.document_renderer_registry import DocumentRendererEntry, DocumentRendererKey, DocumentRendererRegistry
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData


class StubEngine:
    """An engine that prints the job it was handed as its bytes, and remembers it."""

    def __init__(self) -> None:
        self.jobs: list[RenderJob] = []

    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:  # ruff: ignore[unused-method-argument]
        self.jobs.append(job)
        return RenderedDocument(data=b"%PDF-stub " + job.model_dump_json().encode())


class StubEngines:
    """The stub engines of one test: a pdf from the layout and from HTML, and a docx from a template file with a checker."""

    def __init__(self) -> None:
        self.engine = StubEngine()
        self.nb_builds = 0
        self.findings: list[TemplateFinding] = []
        self.check_requests: list[TemplateCheckRequest] = []

    def make_engine(self) -> StubEngine:
        self.nb_builds += 1
        return self.engine

    def check_template(self, *, request: TemplateCheckRequest) -> list[TemplateFinding]:
        self.check_requests.append(request)
        return self.findings

    def registry(self) -> DocumentRendererRegistry:
        entries: dict[DocumentRendererKey, DocumentRendererEntry] = {}
        for doc_gen_format, source, check_template in (
            (DocGenFormat.PDF, DocGenSource.LAYOUT, None),
            (DocGenFormat.PDF, DocGenSource.HTML, None),
            (DocGenFormat.DOCX, DocGenSource.TEMPLATE_FILE, self.check_template),
        ):
            entries[DocumentRendererKey(doc_gen_format=doc_gen_format, source=source, engine="stub")] = DocumentRendererEntry(
                engine="stub", make_renderer=self.make_engine, check_template=check_template, source_plugin="stub-plugin"
            )
        return DocumentRendererRegistry(entries=entries, engine_choices={})


async def refusal_report(*, step_fields: str) -> str:
    """The error report, as text, of validating the test bundle with the given PipeDocGen step, which must be refused."""
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)])
    return str(exc_info.value.to_error_report().model_dump())


def write_bundle(*, directory: Path, step_fields: str) -> Path:
    """Write the test bundle with the given PipeDocGen step into a directory, for a step that names a template file."""
    bundle_path = directory / "invoice.mthds"
    bundle_path.write_text(PipeDocGenTestData.bundle(step_fields=step_fields), encoding="utf-8")
    return bundle_path
