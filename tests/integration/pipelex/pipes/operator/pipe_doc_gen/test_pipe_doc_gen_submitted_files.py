"""A bundle loaded from content strings brings the template files its PipeDocGen steps read, as the runner's routes receive it."""

from pathlib import Path
from typing import Any

import pytest
from mthds.method_tree.digest import digest_of_contents
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError, ValidationErrorCategory
from pipelex.cogt.doc_gen.doc_gen_format import DocGenSource
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
from pipelex.core.method_trees.exceptions import MethodFileUnavailableError
from pipelex.core.method_trees.tree_bundle import TreeBundleRef
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.doc_gen.template_file_stage import DocGenTemplateFileStage
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import (
    METHOD_MANIFEST,
    RecordingMethodFileStore,
    StubEngines,
    WorkerLikePipeRun,
    caller_text,
    diagnosed_error_classes,
    only_problem_item,
    refusal_messages,
    write_bundle,
)
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_DOCX_TEMPLATE_STEP = 'format = "docx"\ntemplate_file = "templates/invoice.docx"'
_DOCX_BYTES = b"PK docx template bytes"


_ESCAPING_DOCX_STEP = 'format = "docx"\ntemplate_file = "../invoice.docx"'


def _docx_files() -> dict[str, bytes]:
    return {"./templates/invoice.docx": _DOCX_BYTES}


def _bundle_file_climbing_in_its_method_tree(*, method_dir: Path) -> Path:
    """Write a method whose bundle file, in `bundles/`, names its template through `..` in `templates/`, and return that file."""
    (method_dir / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")
    (method_dir / "templates").mkdir()
    (method_dir / "templates" / "invoice.docx").write_bytes(_DOCX_BYTES)
    (method_dir / "bundles").mkdir()
    return write_bundle(directory=method_dir / "bundles", step_fields='format = "docx"\ntemplate_file = "../templates/invoice.docx"', as_method=False)


async def _load_from_content(*, load: str, content: str, submitted_files: dict[str, bytes] | None) -> None:
    """Validate the content or run it, as the runner's routes do with a bundle sent as a string."""
    match load:
        case "validate":
            await validate_bundle(mthds_contents=[content], submitted_files=submitted_files)
        case _:
            await PipelexMTHDSProtocol(submitted_files=submitted_files).execute(mthds_contents=[content], inputs=PipeDocGenTestData.INVOICE_INPUTS)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenSubmittedFiles:
    async def test_a_bundle_validates_with_its_template_file_and_the_check_runs_on_its_bytes(self, stub_engines: StubEngines) -> None:
        """The dry run hands the engine's checker the bytes submitted with the bundle, found by the path the step names."""
        await validate_bundle(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            submitted_files=_docx_files(),
        )

        (request,) = stub_engines.check_requests
        assert request.template == _DOCX_BYTES
        assert request.template_name == "templates/invoice.docx"

    async def test_a_step_naming_its_template_with_a_repeated_slash_reads_the_file_submitted_under_its_one_spelling(
        self, stub_engines: StubEngines
    ) -> None:
        """Blueprint validation accepts `templates//invoice.docx`, so the step finds the file submitted as `templates/invoice.docx`."""
        await validate_bundle(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "docx"\ntemplate_file = "templates//invoice.docx"')],
            submitted_files={"templates/invoice.docx": _DOCX_BYTES},
        )

        (request,) = stub_engines.check_requests
        assert request.template == _DOCX_BYTES

    async def test_the_check_s_errors_on_a_submitted_template_fail_the_validation(self, stub_engines: StubEngines) -> None:
        stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The tag {{ invoice.totl }} names no field")]

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
                submitted_files=_docx_files(),
            )

        item = only_problem_item(exc_info.value)
        assert item.code == PipelexErrorCode.DOCGEN_TEMPLATE_INVALID
        assert "invoice.totl" in item.detail

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_template_file_not_supplied_is_refused_saying_so(self) -> None:
        """The refusal is the bundle's verdict, located on the step, and names the path the file is expected under."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)])

        item = only_problem_item(exc_info.value)
        assert item.code == CoreCode.METHOD_RESOURCE_MISSING
        assert item.location is not None
        assert item.location.pipe == "print_invoice"
        assert "'templates/invoice.docx'" in item.detail
        assert "names the template file 'templates/invoice.docx', which was not supplied with its bundle" in refusal_messages(exc_info.value)

    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize("template_file", ["../invoice.docx", "templates/../invoice.docx"], ids=["leaves_the_bundle", "dot_dot_inside"])
    @pytest.mark.parametrize("load", ["validate", "run"])
    @pytest.mark.parametrize("sends_a_file", [False, True], ids=["sends_nothing", "sends_a_file"])
    async def test_a_template_file_no_submitted_file_could_be_keyed_by_is_a_blueprint_item_at_the_step(
        self, template_file: str, load: str, sends_a_file: bool
    ) -> None:
        """The step's file is held to the rule the files sent with its bundle are keyed by, when its blueprint validates.

        Whatever the request sends, the step is the verdict's one item, a blueprint one located at the step, which
        names the field and never repeats the path, rather than a load refusal saying the file was not supplied.
        """
        content = PipeDocGenTestData.bundle(step_fields=f'format = "docx"\ntemplate_file = "{template_file}"')
        submitted_files = {"invoice.docx": _DOCX_BYTES} if sends_a_file else None

        with pytest.raises(ValidateBundleError) as exc_info:
            await _load_from_content(load=load, content=content, submitted_files=submitted_files)

        items = exc_info.value.validation_error_items()
        assert items is not None
        (item,) = items
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.pipe_code == "print_invoice"
        assert item.domain_code == "doc_gen_tests"
        assert item.field_path == "pipe.print_invoice"
        assert "PipeDocGen's 'template_file'" in item.message
        assert "it leaves the bundle through a '..' segment" in item.message
        assert template_file not in item.message

    async def test_a_bundle_its_caller_read_from_a_file_here_climbs_through_dot_dot_in_its_method_tree(
        self, stub_engines: StubEngines, tmp_path: Path
    ) -> None:
        """Contents read from a file named in `bundle_uris` are that file's bundle, whose step may climb through `..` in its tree."""
        bundle_path = _bundle_file_climbing_in_its_method_tree(method_dir=tmp_path)

        await PipelexMTHDSProtocol(bundle_uris=[str(bundle_path)], pipe_run_mode=PipeRunMode.DRY).execute(
            mthds_contents=[bundle_path.read_text(encoding="utf-8")],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        assert [check_request.template for check_request in stub_engines.check_requests] == [_DOCX_BYTES]

    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize("uri_kind", ["label", "stale_path", "directory"])
    async def test_a_content_whose_uri_names_no_file_here_reads_only_the_files_submitted_with_it(self, tmp_path: Path, uri_kind: str) -> None:
        """A URI naming no file on this host, a label, a path to no file or a directory, gives its content no method tree to climb in."""
        bundle_uri = {"label": "invoice-printer", "stale_path": str(tmp_path / "gone.mthds"), "directory": str(tmp_path)}[uri_kind]

        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol(bundle_uris=[bundle_uri], pipe_run_mode=PipeRunMode.DRY).execute(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=_ESCAPING_DOCX_STEP)],
                inputs=PipeDocGenTestData.INVOICE_INPUTS,
            )

        (item,) = exc_info.value.validation_error_items() or []
        assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
        assert item.field_path == "pipe.print_invoice"
        assert "it leaves the bundle through a '..' segment" in item.message

    @pytest.mark.parametrize("file_first", [True, False], ids=["file_first", "label_first"])
    async def test_in_a_mixed_list_the_file_read_here_climbs_in_its_tree_and_the_other_content_does_not(
        self, stub_engines: StubEngines, tmp_path: Path, file_first: bool
    ) -> None:
        """Each content takes the origin its own URI gives it, wherever it sits in the list.

        Beside a content under a label whose step names no file, the file's step climbs through `..` in its tree. Beside one
        whose step climbs, that step is the verdict's one item, and the file's own `..` is not refused.
        """
        bundle_path = _bundle_file_climbing_in_its_method_tree(method_dir=tmp_path)
        read_here = (bundle_path.read_text(encoding="utf-8"), str(bundle_path))
        under_a_label = (PipeDocGenTestData.bundle_in_the_other_domain(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP), "invoice-printer")
        escaping_under_a_label = (PipeDocGenTestData.bundle_in_the_other_domain(step_fields=_ESCAPING_DOCX_STEP), "invoice-printer")

        def _ordered(other: tuple[str, str]) -> list[tuple[str, str]]:
            return [read_here, other] if file_first else [other, read_here]

        entries = _ordered(under_a_label)
        await PipelexMTHDSProtocol(bundle_uris=[uri for _, uri in entries], pipe_run_mode=PipeRunMode.DRY).execute(
            pipe_code="doc_gen_tests.print_invoice",
            mthds_contents=[content for content, _ in entries],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )
        assert [check_request.template for check_request in stub_engines.check_requests] == [_DOCX_BYTES]

        entries = _ordered(escaping_under_a_label)
        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol(bundle_uris=[uri for _, uri in entries], pipe_run_mode=PipeRunMode.DRY).execute(
                pipe_code="doc_gen_tests.print_invoice",
                mthds_contents=[content for content, _ in entries],
                inputs=PipeDocGenTestData.INVOICE_INPUTS,
            )
        (item,) = exc_info.value.validation_error_items() or []
        assert (item.category, item.domain_code, item.pipe_code) == (
            ValidationErrorCategory.BLUEPRINT_VALIDATION,
            PipeDocGenTestData.OTHER_DOMAIN,
            "print_invoice",
        )
        assert "it leaves the bundle through a '..' segment" in item.message

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_file_no_step_names_is_refused_as_the_request_s_fault_not_as_a_verdict(self) -> None:
        submitted_files = {"templates/invoice.docx": _DOCX_BYTES, "templates/logo.png": b"png"}

        with pytest.raises(BundleResourceNotNamedError) as exc_info:
            await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)], submitted_files=submitted_files)

        assert "'templates/logo.png'" in exc_info.value.message

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_submitted_html_template_is_read_and_checked_when_the_method_loads(self) -> None:
        """An HTML template file is checked against the inputs at load, as one beside a bundle on disk is."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate_file = "invoice.html"')],
                submitted_files={"invoice.html": b"<h1>{{ invoice.numbr }}</h1>"},
            )

        assert "numbr" in caller_text(exc_info.value)

    async def test_a_run_prints_with_the_submitted_html_template(self, stub_engines: StubEngines) -> None:
        await PipelexMTHDSProtocol(submitted_files={"invoice.html": b"<h1>{{ invoice.number }}</h1>"}).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate_file = "invoice.html"')],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.HTML
        assert job.html == "<h1>INV-2026-0142</h1>"

    async def test_a_run_hands_the_engine_the_submitted_template_file(self, stub_engines: StubEngines) -> None:
        result = await PipelexMTHDSProtocol(submitted_files=_docx_files()).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename is not None
        assert document.filename.endswith(".docx")
        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.TEMPLATE_FILE
        assert job.template == _DOCX_BYTES
        assert job.template_name == "templates/invoice.docx"
        assert job.data["invoice"]["number"] == "INV-2026-0142"

    async def test_a_dry_run_checks_the_submitted_template_file_and_prints_nothing(self, stub_engines: StubEngines) -> None:
        result = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, submitted_files=_docx_files()).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename is not None
        assert document.filename.endswith(".docx")
        (request,) = stub_engines.check_requests
        assert request.template == _DOCX_BYTES
        assert stub_engines.engine.jobs == []

    @pytest.mark.parametrize("pipe_run_mode", [pytest.param(PipeRunMode.LIVE, id="live"), pytest.param(PipeRunMode.DRY, id="dry")])
    @pytest.mark.parametrize(
        ("step_fields", "submitted_files"),
        [
            pytest.param(_DOCX_TEMPLATE_STEP, {"templates/invoice.docx": _DOCX_BYTES}, id="office"),
            pytest.param('format = "pdf"\ntemplate_file = "invoice.html"', {"invoice.html": b"<h1>{{ invoice.number }}</h1>"}, id="html"),
        ],
    )
    async def test_a_run_handed_to_a_remote_worker_reads_its_template_through_the_method_file_store(
        self,
        stub_engines: StubEngines,
        remote_worker: WorkerLikePipeRun,
        recording_store: RecordingMethodFileStore,
        mocker: MockerFixture,
        pipe_run_mode: PipeRunMode,
        step_fields: str,
        submitted_files: dict[str, bytes],
    ) -> None:
        """The crate names the step's tree by digest and carries none of its files, and the print stage reads the template under the run's read scope.

        An HTML template file is rendered there too, a dry print included, with the step's data typed by the run's crate.
        """
        remote_worker.worker_read_scope = "acme/runs"
        render_spy = mocker.spy(DocGenTemplateFileStage, "render_html_template_file")

        await PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode, submitted_files=submitted_files).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        (received_crate,) = remote_worker.received_crates
        assert received_crate.tree_bundles["doc_gen_tests.print_invoice"] == TreeBundleRef(
            tree_digest=digest_of_contents(submitted_files), tree_path=None
        )
        assert "invoice.number }}" not in received_crate.model_dump_json()
        # The worker's step, built from the crate, read no file: its compose stage names the template, and its print reads it.
        (worker_pipe,) = remote_worker.worker_pipes
        assert isinstance(worker_pipe, PipeDocGen)
        assert worker_pipe.template_file_text is None
        # An HTML template's print receives the stuffs the step's inputs name and the run's concepts, none of its pipes.
        for render_call in render_spy.call_args_list:
            render_context = render_call.kwargs["template_file"].render_context
            assert set(render_context.working_memory_raw["root"]) == {"invoice"}
            assert render_context.concepts_crate["pipes"] == {}
            assert "doc_gen_tests.Invoice" in render_context.concepts_crate["concepts"]
            assert render_context.crate_fingerprint == received_crate.fingerprint
        assert recording_store.read_scopes
        assert set(recording_store.read_scopes) == {"acme/runs"}
        match (pipe_run_mode, step_fields):
            case (PipeRunMode.LIVE, 'format = "docx"\ntemplate_file = "templates/invoice.docx"'):
                assert [job.template for job in stub_engines.engine.jobs] == [_DOCX_BYTES]
                assert render_spy.call_count == 0
            case (PipeRunMode.DRY, 'format = "docx"\ntemplate_file = "templates/invoice.docx"'):
                assert [request.template for request in stub_engines.check_requests] == [_DOCX_BYTES]
                assert stub_engines.engine.jobs == []
                assert render_spy.call_count == 0
            case (PipeRunMode.LIVE, _):
                assert [job.html for job in stub_engines.engine.jobs] == ["<h1>INV-2026-0142</h1>"]
                assert render_spy.call_count == 1
            case (PipeRunMode.DRY, _):
                assert stub_engines.engine.jobs == []
                assert render_spy.call_count == 1

    async def test_a_template_file_the_store_does_not_serve_fails_the_print_naming_it(
        self, stub_engines: StubEngines, remote_worker: WorkerLikePipeRun, recording_store: RecordingMethodFileStore
    ) -> None:
        """A worker whose store serves no file of the step's tree cannot print, and says which file by its tree path, not a host path."""
        recording_store.refuses = True

        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, submitted_files=_docx_files()).execute(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
                inputs=PipeDocGenTestData.INVOICE_INPUTS,
            )

        assert remote_worker.received_crates
        assert MethodFileUnavailableError.__name__ in diagnosed_error_classes(exc_info.value)
        assert stub_engines.check_requests == []

    @pytest.mark.parametrize(
        ("step_fields", "template_name", "template_bytes"),
        [
            pytest.param(_DOCX_TEMPLATE_STEP, "templates/invoice.docx", _DOCX_BYTES, id="office"),
            pytest.param('format = "pdf"\ntemplate_file = "invoice.html"', "invoice.html", b"<h1>{{ invoice.number }}</h1>", id="html"),
        ],
    )
    async def test_a_caller_s_source_label_never_reads_beside_it_on_this_host(
        self, stub_engines: StubEngines, tmp_path: Path, step_fields: str, template_name: str, template_bytes: bytes
    ) -> None:
        """A label naming a real bundle file on this host, beside which the template file exists, still reads nothing from disk."""
        bundle_path = write_bundle(directory=tmp_path, step_fields=step_fields)
        (tmp_path / template_name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / template_name).write_bytes(template_bytes)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle_path.read_text(encoding="utf-8")], mthds_sources=[str(bundle_path)])

        assert "which was not supplied with its bundle" in refusal_messages(exc_info.value)
        assert stub_engines.check_requests == []

    @pytest.mark.parametrize("pipe_run_mode", [pytest.param(PipeRunMode.LIVE, id="live"), pytest.param(PipeRunMode.DRY, id="dry")])
    async def test_a_bundle_its_caller_read_from_a_file_here_reads_its_template_beside_that_file(
        self, stub_engines: StubEngines, tmp_path: Path, pipe_run_mode: PipeRunMode
    ) -> None:
        """A caller that read the bundle's file itself, and names it in `bundle_uris`, runs it as a bundle loaded from that file.

        Nothing loads the bundle's directory, so the contents are what loads, and their step reads the template beside the file.
        """
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "invoice.docx").write_bytes(_DOCX_BYTES)

        await PipelexMTHDSProtocol(bundle_uris=[str(bundle_path)], pipe_run_mode=pipe_run_mode).execute(
            mthds_contents=[bundle_path.read_text(encoding="utf-8")],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        match pipe_run_mode:
            case PipeRunMode.LIVE:
                assert [job.template for job in stub_engines.engine.jobs] == [_DOCX_BYTES]
            case PipeRunMode.DRY:
                assert [check_request.template for check_request in stub_engines.check_requests] == [_DOCX_BYTES]
                assert stub_engines.engine.jobs == []

    async def test_a_source_the_bundle_s_text_writes_on_its_step_never_reads_beside_it_on_this_host(
        self, stub_engines: StubEngines, tmp_path: Path
    ) -> None:
        """The step's own `source` key is overwritten when the pipe is built, on the validation path and on the run path."""
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "invoice.docx").write_bytes(_DOCX_BYTES)
        content = PipeDocGenTestData.bundle(step_fields=f'{_DOCX_TEMPLATE_STEP}\nsource = "{bundle_path}"')

        with pytest.raises(ValidateBundleError) as validate_exc_info:
            await validate_bundle(mthds_contents=[content])
        with pytest.raises(ValidateBundleError) as run_exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[content], inputs=PipeDocGenTestData.INVOICE_INPUTS)

        for exc_info in (validate_exc_info, run_exc_info):
            assert "which was not supplied with its bundle" in refusal_messages(exc_info.value)
        assert stub_engines.check_requests == []
        assert stub_engines.engine.jobs == []

    @pytest.mark.parametrize("is_remote", [pytest.param(False, id="in_process"), pytest.param(True, id="remote_worker")])
    async def test_a_step_read_from_a_file_here_reads_beside_it_and_never_a_submitted_file(
        self, request: pytest.FixtureRequest, stub_engines: StubEngines, tmp_path: Path, is_remote: bool
    ) -> None:
        """A host library's step and a submitted step naming the same template path each read their own file, here and on a worker.

        The crate names each step's tree by digest, so on a worker too each step's print reads the file of its own tree.
        """
        host_dir = tmp_path / "host"
        host_dir.mkdir()
        step_fields = 'format = "docx"\ntemplate_file = "invoice.docx"'
        (host_dir / "invoice.mthds").write_text(
            PipeDocGenTestData.bundle(step_fields=step_fields).replace("doc_gen_tests", "doc_gen_host"), encoding="utf-8"
        )
        (host_dir / "invoice.docx").write_bytes(b"host template")
        submitted = {"invoice.docx": b"submitted template"}
        host_inputs: dict[str, Any] = {"invoice": {**PipeDocGenTestData.INVOICE_INPUTS["invoice"], "concept": "doc_gen_host.Invoice"}}
        runs: list[tuple[str, dict[str, Any]]] = [
            ("doc_gen_host.print_invoice", host_inputs),
            ("doc_gen_tests.print_invoice", PipeDocGenTestData.INVOICE_INPUTS),
        ]

        if is_remote:
            request.getfixturevalue("remote_worker")

        for pipe_code, inputs in runs:
            await PipelexMTHDSProtocol(library_dirs=[str(host_dir)], submitted_files=submitted).execute(
                pipe_code=pipe_code,
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)],
                inputs=inputs,
            )

        assert [job.template for job in stub_engines.engine.jobs] == [b"host template", b"submitted template"]
