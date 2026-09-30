from pathlib import Path

import pytest
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_worker_abstract import DocGenWorkerAbstract
from pipelex.cogt.doc_gen.render_job import RenderedDocument, RenderJob, RenderResources
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest, TemplateFinding
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.plugins.inference_backend_registry import MakeWorkerFn
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

# The sdks of the kit's doc_gen models the stubs stand in for: a pdf from the layout, a pdf from HTML, and a docx.
STUB_DOC_GEN_SDKS = ("reportlab", "weasyprint", "docxtpl")


class StubEngine:
    """An engine that prints the job it was handed as its bytes, and remembers it."""

    def __init__(self) -> None:
        self.jobs: list[RenderJob] = []

    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:  # ruff: ignore[unused-method-argument]
        self.jobs.append(job)
        return RenderedDocument(data=b"%PDF-stub " + job.model_dump_json().encode())


class StubDocGenWorker(DocGenWorkerAbstract):
    """The worker the stub sdks make: it prints on the test's engine and checks templates with the test's checker."""

    def __init__(self, *, inference_model: InferenceModelSpec, engines: "StubEngines"):
        super().__init__(inference_model=inference_model)
        self._engines = engines

    @override
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        return self._engines.engine.render(job=job, resources=resources)

    @override
    def check_template(self, *, request: TemplateCheckRequest) -> list[TemplateFinding]:
        return self._engines.check_template(request=request)


class StubEngines:
    """The stub engines of one test, registered for the sdks of `reportlab-pdf`, `weasyprint-pdf` and `docxtpl-docx`."""

    def __init__(self) -> None:
        self.engine = StubEngine()
        self.nb_builds = 0
        self.findings: list[TemplateFinding] = []
        self.check_requests: list[TemplateCheckRequest] = []
        self.models: list[str] = []

    def make_worker(
        self,
        *,
        inference_model: InferenceModelSpec,
        backend: InferenceBackend,  # ruff: ignore[unused-method-argument]
        sdk_clients: SdkClientRegistry,  # ruff: ignore[unused-method-argument]
        reporting_delegate: ReportingProtocol | None,  # ruff: ignore[unused-method-argument]
    ) -> InferenceWorkerAbstract:
        self.nb_builds += 1
        self.models.append(inference_model.name)
        return StubDocGenWorker(inference_model=inference_model, engines=self)

    def check_template(self, *, request: TemplateCheckRequest) -> list[TemplateFinding]:
        self.check_requests.append(request)
        return self.findings

    def backends(self) -> dict[str, MakeWorkerFn]:
        return dict.fromkeys(STUB_DOC_GEN_SDKS, self.make_worker)


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
