from pathlib import Path

import pytest
from mthds.method_tree.models import MethodTree
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.doc_gen.input_shape import InputShapeKind
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.resolve_bundle import resolve_crate_from_method_dir
from pipelex.pipeline.validate_bundle import ValidateBundleResult, validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import (
    METHOD_MANIFEST,
    StubEngines,
    caller_text,
    only_problem_item,
    refusal_messages,
    write_bundle,
)
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_DOCX_TEMPLATE_STEP = 'format = "docx"\ntemplate_file = "invoice.docx"'


async def _validate_with_html_template_file(*, directory: Path, load: str, template_bytes: bytes) -> ValidateBundleResult:
    """Validate the test bundle with a pdf step naming `invoice.html`, loaded from its directory or sent as content with the file."""
    step_fields = 'format = "pdf"\ntemplate_file = "invoice.html"'
    match load:
        case "from_its_directory":
            (directory / "invoice.html").write_bytes(template_bytes)
            return await validate_bundle(mthds_file_path=write_bundle(directory=directory, step_fields=step_fields))
        case _:
            return await validate_bundle(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)],
                submitted_files={"invoice.html": template_bytes},
            )


async def _load_method(*, load: str, method_dir: Path, bundle_path: Path) -> None:
    """Validate the bundle file, or resolve the crate of its method's folder as the runner's crate routes do."""
    match load:
        case "validate":
            await validate_bundle(mthds_file_path=bundle_path)
        case _:
            resolve_crate_from_method_dir(method_dir=method_dir)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenTemplateFiles:
    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize(
        ("template_file", "expected_code", "expected"),
        [
            ("invoice.docx", CoreCode.METHOD_RESOURCE_MISSING, "resolves to 'invoice.docx', which is not a file of the tree."),
            ("ignored.docx", CoreCode.METHOD_RESOURCE_MISSING, "which is not a file of the tree: it is kept out by a .gitignore pattern"),
            (
                ".templates/invoice.docx",
                CoreCode.METHOD_RESOURCE_MISSING,
                "which is not a file of the tree: it is kept out by a path segment starting with a dot",
            ),
        ],
        ids=["missing_file", "gitignored", "hidden"],
    )
    @pytest.mark.parametrize("load", ["validate", "resolve"])
    async def test_a_template_file_is_a_file_of_the_bundle_s_method_tree(
        self, tmp_path: Path, template_file: str, expected_code: CoreCode, expected: str, load: str
    ) -> None:
        """A template file must be a file of the method's tree, validated or resolved: one its membership rule keeps out is never read."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        (method_dir / "ignored.docx").write_bytes(b"docx")
        (method_dir / ".gitignore").write_text("ignored.docx\n", encoding="utf-8")
        (method_dir / ".templates").mkdir()
        (method_dir / ".templates" / "invoice.docx").write_bytes(b"docx")
        bundle_path = write_bundle(directory=method_dir, step_fields=f'format = "docx"\ntemplate_file = "{template_file}"')

        with pytest.raises(ValidateBundleError) as exc_info:
            await _load_method(load=load, method_dir=method_dir, bundle_path=bundle_path)

        assert only_problem_item(exc_info.value).code == expected_code
        assert expected in refusal_messages(exc_info.value)

    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize("load", ["validate", "resolve"])
    async def test_a_template_file_outside_the_tree_is_the_method_s_security_refusal_not_a_verdict(self, tmp_path: Path, load: str) -> None:
        """A template file that climbs out of the method's tree is refused under its security code, never absorbed into a verdict."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        (tmp_path / "outside.docx").write_bytes(b"docx")
        bundle_path = write_bundle(directory=method_dir, step_fields='format = "docx"\ntemplate_file = "../outside.docx"')

        with pytest.raises(PipelexError) as exc_info:
            await _load_method(load=load, method_dir=method_dir, bundle_path=bundle_path)

        assert not isinstance(exc_info.value, ValidateBundleError)
        assert exc_info.value.resolve_error_code() == CoreCode.SECURITY_METHOD_PATH_REFUSED
        assert "climbs above the root of its method tree" in exc_info.value.message

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_template_file_climbs_through_dot_dot_to_another_folder_of_its_tree(self, tmp_path: Path) -> None:
        """A `..` may climb out of the bundle's folder to a file elsewhere in its method tree, which the step reads."""
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "invoice.html").write_text("<h1>{{ invoice.number }}</h1>", encoding="utf-8")
        (tmp_path / "bundles").mkdir()
        bundle_path = write_bundle(
            directory=tmp_path / "bundles", step_fields='format = "pdf"\ntemplate_file = "../templates/invoice.html"', as_method=False
        )
        (tmp_path / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")

        result = await validate_bundle(mthds_file_path=bundle_path)

        (pipe,) = result.pipes
        assert isinstance(pipe, PipeDocGen)
        assert pipe.template is None
        assert pipe.template_file_text == "<h1>{{ invoice.number }}</h1>"
        assert isinstance(pipe.template_file_ref, MethodFileRef)
        assert pipe.template_file_ref.tree_path == "templates/invoice.html"

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_bundle_file_named_alone_reads_no_file_beside_it(self, tmp_path: Path) -> None:
        """With no METHODS.toml at or above its folder, a bundle named alone is a one-file tree: the file beside it is refused."""
        (tmp_path / "invoice.docx").write_bytes(b"docx")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP, as_method=False)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.domain == ProblemDomain.METHOD
        assert only_problem_item(exc_info.value).code == CoreCode.METHOD_RESOURCE_MISSING
        report = refusal_messages(exc_info.value)
        assert "names the template file 'invoice.docx'" in report
        assert "Run the method's folder instead, or add a METHODS.toml to it." in report

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_symbolic_link_in_the_method_refuses_its_tree(self, tmp_path: Path) -> None:
        """A tree holds regular files only, so a link anywhere in the method refuses it before any step reads through it."""
        (tmp_path / "outside.docx").write_bytes(b"docx")
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        (method_dir / "linked.docx").symlink_to(tmp_path / "outside.docx")
        bundle_path = write_bundle(directory=method_dir, step_fields='format = "docx"\ntemplate_file = "linked.docx"')

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        assert "holds a symbolic link, 'linked.docx'" in refusal_messages(exc_info.value)

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_template_file_named_by_an_absolute_path_is_refused_without_repeating_it(self, tmp_path: Path) -> None:
        """Even an absolute path to a file inside the bundle's directory is refused, and the refusal never carries the host's path."""
        (tmp_path / "invoice.docx").write_bytes(b"docx")
        absolute_template = tmp_path / "invoice.docx"
        bundle_path = write_bundle(directory=tmp_path, step_fields=f'format = "docx"\ntemplate_file = "{absolute_template}"')

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        report = refusal_messages(exc_info.value)
        assert "a path relative to the bundle's file, in its method, and this one cannot be: it is absolute" in report
        assert str(absolute_template) not in report
        assert str(absolute_template) not in caller_text(exc_info.value)

    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize("load", ["from_its_directory", "from_content"])
    async def test_an_html_template_file_that_is_not_utf8_is_refused_naming_it(self, tmp_path: Path, load: str) -> None:
        """A template saved in another encoding is refused at load, naming the file, rather than crashing the load, however it came."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await _validate_with_html_template_file(directory=tmp_path, load=load, template_bytes="<p>Facture émise</p>".encode("latin-1"))

        assert "could not read the template file 'invoice.html' as UTF-8 text" in refusal_messages(exc_info.value)

    @pytest.mark.usefixtures("stub_engines")
    async def test_an_html_template_file_changed_after_its_tree_was_listed_is_refused_not_read_from_disk(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The load reads the file as its tree's listing recorded it, or not at all: bytes changed since are never read unchecked."""
        (tmp_path / "invoice.html").write_bytes(b"<h1>{{ invoice.number }}</h1>")
        bundle_path = write_bundle(directory=tmp_path, step_fields='format = "pdf"\ntemplate_file = "invoice.html"')
        hold_tree = LOCAL_METHOD_FILES.hold_tree

        def hold_then_change(*, holder: str, tree: MethodTree) -> None:
            hold_tree(holder=holder, tree=tree)
            (tmp_path / "invoice.html").write_bytes(b"<h1>{{ invoice.customer }}</h1>")

        mocker.patch.object(LOCAL_METHOD_FILES, "hold_tree", side_effect=hold_then_change)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        assert "could not read the template file 'invoice.html' as its method tree listed it" in refusal_messages(exc_info.value)

    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize("load", ["from_its_directory", "from_content"])
    async def test_an_html_template_file_reads_the_same_whichever_way_its_bundle_loads(self, tmp_path: Path, load: str) -> None:
        """The step holds the file's text as written, its line endings included, read from disk as from the submitted bytes."""
        template_bytes = b"<h1>{{ invoice.number }}</h1>\r\n<p>Due on receipt</p>\r\n"

        result = await _validate_with_html_template_file(directory=tmp_path, load=load, template_bytes=template_bytes)

        (pipe,) = result.pipes
        assert isinstance(pipe, PipeDocGen)
        assert pipe.template_file_text == template_bytes.decode("utf-8")

    async def test_the_engine_s_checker_findings_fail_the_dry_run(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """The dry run hands the checker the file's bytes, the inputs' shapes and the mock data, and an error finding fails it."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The tag {{ invoice.totl }} names no field")]

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        item = only_problem_item(exc_info.value)
        assert item.code == PipelexErrorCode.DOCGEN_TEMPLATE_INVALID
        assert "invoice.totl" in item.detail
        (request,) = stub_engines.check_requests
        assert request.template == b"docx bytes"
        assert request.template_name == "invoice.docx"
        assert set(request.inputs["invoice"].fields) == {"number", "customer", "notes", "line_items"}
        assert request.data is not None
        assert set(request.data) == {"invoice"}

    async def test_an_anything_input_reaches_the_checker_with_an_undeclared_shape(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """An `Anything` input has no content class to describe, so the checker is told its shape is not declared."""
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        (tmp_path / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")
        bundle_path = tmp_path / "invoice.mthds"
        bundle_path.write_text(
            PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP).replace(
                'inputs      = { invoice = "Invoice" }', 'inputs      = { invoice = "Invoice", thing = "Anything" }'
            ),
            encoding="utf-8",
        )

        await validate_bundle(mthds_file_path=bundle_path)

        (request,) = stub_engines.check_requests
        assert request.inputs["thing"].kind == InputShapeKind.ANY
        assert request.inputs["invoice"].kind == InputShapeKind.STRUCTURE

    async def test_warnings_alone_pass_and_print_nothing(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """A warning is not raised and the dry run prints nothing: the step's dry run output carries it for the verdict.

        `test_pipe_doc_gen_template_warnings.py` follows it from there to every validate surface, and to the log when the
        sweep's caller asks for no warnings.
        """
        (tmp_path / "invoice.docx").write_bytes(b"docx bytes")
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        stub_engines.findings = [
            TemplateFinding(severity=TemplateFindingSeverity.WARNING, message="The notes are never printed", location="the field notes on page 2")
        ]

        result = await validate_bundle(mthds_file_path=bundle_path, collect_dry_run_warnings=True)

        assert len(stub_engines.check_requests) == 1
        assert stub_engines.engine.jobs == []
        assert [warning.message for warning in result.dry_run_result["doc_gen_tests.print_invoice"].warnings] == [
            "PipeDocGen 'print_invoice', template file 'invoice.docx': The notes are never printed (the field notes on page 2)"
        ]
