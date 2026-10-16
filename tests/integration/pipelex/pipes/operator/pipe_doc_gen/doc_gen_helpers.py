from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from pipelex.core.method_trees.method_file_store import MethodFileStoreProtocol
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import get_current_library, get_library_manager, set_current_library
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
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
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

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
            case InferenceFamily.LLM | InferenceFamily.IMG_GEN | InferenceFamily.EXTRACT | InferenceFamily.SEARCH | InferenceFamily.JUDGMENT:
                pass
    return backends


def make_models_manager(*, plugin_model_declarations: PluginModelDeclarations, backends_dir_path: Path | None = None) -> ModelManager:
    """A model manager set up from this runtime's configuration with the given plugins' declarations.

    Set up the way a boot that needs no inference is: the internal models, the plugins' included, resolve through the
    internal backend. A test that needs other backend files hands their directory in.
    """
    models_manager = ModelManager()
    models_manager.setup(
        secrets_provider=get_secrets_provider(),
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


class RecordingMethodFileStore(MethodFileStoreProtocol):
    """A method file store serving what another serves, recording the read scope of every read, and refusing all when told to."""

    def __init__(self, *, served_by: MethodFileStoreProtocol) -> None:
        self._served_by = served_by
        self.read_scopes: list[str | None] = []
        self.refuses = False

    @override
    async def read_tree_listing(self, *, tree_digest: str, read_scope: str | None) -> bytes | None:
        self.read_scopes.append(read_scope)
        if self.refuses:
            return None
        return await self._served_by.read_tree_listing(tree_digest=tree_digest, read_scope=read_scope)

    @override
    async def read_blob(self, *, sha256: str, read_scope: str | None) -> bytes | None:
        self.read_scopes.append(read_scope)
        if self.refuses:
            return None
        return await self._served_by.read_blob(sha256=sha256, read_scope=read_scope)


METHOD_MANIFEST = """[package]
address = "github.com/pipelex-tests/invoice-printer"
version = "1.0.0"
description = "Prints an invoice from a template file"
"""


def write_bundle(*, directory: Path, step_fields: str, as_method: bool = True) -> Path:
    """Write the test bundle with the given PipeDocGen step into a directory, for a step that names a template file.

    With `as_method`, the directory also holds a `METHODS.toml`, so the bundle file named alone is rooted at the
    directory and its step finds the files beside it in its method tree. Without one, the file named alone is the
    one-file tree of that file, from which a reference to any other file is refused.
    """
    bundle_path = directory / "invoice.mthds"
    bundle_path.write_text(PipeDocGenTestData.bundle(step_fields=step_fields), encoding="utf-8")
    if as_method:
        (directory / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")
    return bundle_path


class WorkerLikePipeRun(PipeRunProtocol):
    """Runs a job the way a remote worker does: loads the crate it was handed into a library of its own and runs its own pipe.

    Installed as the hub's pipe run, as a boot orchestrator's plugin installs its own (the `remote_worker` fixture). Its
    pipe, rebuilt from the crate, which names the step's tree by digest and carries none of its files, reads nothing as it
    is built, and its print stage reads the template file through the method file store, as a Temporal activity does.
    `worker_read_scope`, when given, replaces the run's read scope on the worker.
    """

    def __init__(self, *, in_process_pipe_run: PipeRunProtocol, worker_read_scope: str | None = None) -> None:
        self._in_process_pipe_run = in_process_pipe_run
        self.worker_read_scope = worker_read_scope
        self.received_crates: list[LibraryCrate] = []
        self.worker_pipes: list[PipeAbstract] = []

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        crate = pipe_job.library_crate
        assert crate is not None
        self.received_crates.append(crate)
        library_manager = get_library_manager()
        submitter_library_id = get_current_library()
        worker_library_id = f"worker-{pipe_job.job_metadata.run_metadata.pipeline_run_id}"
        worker_library = library_manager.open_fresh_library(library_id=worker_library_id)
        submitter_class_registry = library_manager.get_library(library_id=submitter_library_id).get_class_registry()
        if submitter_class_registry is not None:
            worker_library.set_class_registry(submitter_class_registry)
        set_current_library(library_id=worker_library_id)
        try:
            library_manager.load_from_crate(library_id=worker_library_id, crate=crate, is_crate_prevalidated=True)
            worker_pipe = library_manager.get_library(library_id=worker_library_id).pipe_library.get_required_pipe(pipe_code=pipe_job.pipe.pipe_ref)
            self.worker_pipes.append(worker_pipe)
            job_metadata = pipe_job.job_metadata
            if self.worker_read_scope is not None:
                run_metadata = job_metadata.run_metadata.model_copy(update={"read_scope": self.worker_read_scope})
                job_metadata = job_metadata.model_copy(update={"run_metadata": run_metadata})
            worker_job = pipe_job.model_copy(update={"pipe": worker_pipe, "job_metadata": job_metadata})
            return await self._in_process_pipe_run.run(worker_job, delivery_assignment=delivery_assignment)
        finally:
            set_current_library(library_id=submitter_library_id)
            library_manager.teardown(library_id=worker_library_id)
