from pathlib import Path
from typing import Any

import pytest
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_worker_abstract import DocGenWorkerAbstract
from pipelex.cogt.doc_gen.render_job import RenderedDocument, RenderJob, RenderResources
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest, TemplateFinding
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.config import get_config
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, MakeWorkerFn
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import get_secrets_provider
from pipelex.system.pipelex_service.managed_gateway_configs import build_managed_gateway_configs
from pipelex.system.pipelex_service.pipelex_service_config import enabled_managed_gateway_sections
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

# The engines the stubs stand in for: the built-in pdf from the layout, and two of the document generation plugin's,
# a pdf from HTML and a docx, which the stub plugin declares as the real plugin would.
BUILT_IN_STUB_SDK = "reportlab"
PIPELEX_PDF_SPEC: dict[str, Any] = {
    "model_type": "doc_gen",
    "sdk": "weasyprint",
    "model_id": "print-pdf",
    "inputs": ["html", "layout"],
    "outputs": ["pdf"],
    "costs": {},
}
PIPELEX_DOCX_SPEC: dict[str, Any] = {
    "model_type": "doc_gen",
    "sdk": "docxtpl",
    "model_id": "write-docx",
    "inputs": ["layout", "template_file"],
    "outputs": ["docx"],
    "costs": {},
}


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
    """The stub engines of one test, registered for the sdks of `reportlab-pdf`, `pipelex-pdf` and `pipelex-docx`."""

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

    def register(self, registrar: PluginRegistrar) -> None:
        """Register as the document generation plugin does: a worker per sdk, the plugin's models, and their deck defaults."""
        for sdk in (BUILT_IN_STUB_SDK, PIPELEX_PDF_SPEC["sdk"], PIPELEX_DOCX_SPEC["sdk"]):
            registrar.add_inference_backend(family=InferenceFamily.DOC_GEN, sdk=sdk, make_worker=self.make_worker)
        registrar.add_internal_model(name="pipelex-pdf", spec=PIPELEX_PDF_SPEC)
        registrar.add_internal_model(name="pipelex-docx", spec=PIPELEX_DOCX_SPEC)
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.HTML, model="pipelex-pdf")
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.DOCX, source=DocGenSource.LAYOUT, model="pipelex-docx")
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.DOCX, source=DocGenSource.TEMPLATE_FILE, model="pipelex-docx")

    def make_registrar(self) -> PluginRegistrar:
        """A registrar holding only the stub plugin's contributions, built the way discovery builds one."""
        registrar = PluginRegistrar(config=get_config())
        registrar.begin_plugin(name="stub-doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
        self.register(registrar)
        return registrar


def make_doc_gen_backends(*, registrar: PluginRegistrar) -> dict[str, MakeWorkerFn]:
    """The document engine workers a registrar holds, keyed by sdk, for `InferenceBackendRegistry.with_family`."""
    backends: dict[str, MakeWorkerFn] = {}
    for (family, sdk), make_worker in registrar.inference_backends.items():
        match family:
            case InferenceFamily.DOC_GEN:
                backends[sdk] = make_worker
            case InferenceFamily.LLM | InferenceFamily.IMG_GEN | InferenceFamily.EXTRACT | InferenceFamily.SEARCH:
                pass
    return backends


def make_models_manager(*, plugin_model_declarations: PluginModelDeclarations, backends_dir_path: Path | None = None) -> ModelManager:
    """A model manager set up from this runtime's configuration with the given plugins' declarations.

    Set up the way a boot that needs no model specs is, with the managed gateways' placeholder specs: nothing is
    fetched, and the internal models, the plugins' included, resolve through the internal backend. A test that needs
    other backend files hands their directory in.
    """
    managed_gateway_sections = enabled_managed_gateway_sections()
    managed_gateway_configs = (
        build_managed_gateway_configs(remote_config=RemoteConfigFetcher.make_dummy_remote_config(), managed_gateway_sections=managed_gateway_sections)
        if managed_gateway_sections
        else None
    )
    models_manager = ModelManager()
    models_manager.setup(
        secrets_provider=get_secrets_provider(),
        managed_gateway_configs=managed_gateway_configs,
        gateway_config_source=None,
        plugin_model_declarations=plugin_model_declarations,
        needs_inference=False,
        backends_dir_path=str(backends_dir_path) if backends_dir_path is not None else None,
    )
    return models_manager


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
