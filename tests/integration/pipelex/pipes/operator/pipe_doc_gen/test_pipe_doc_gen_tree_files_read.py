from pathlib import Path

import pytest

from pipelex.core.method_trees.tree_file_reads import TreeFileRead, TreeFileUse
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import METHOD_MANIFEST, write_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_PIPE_REF = "doc_gen_tests.print_invoice"
_TEMPLATE = """<link rel="stylesheet" href="../styles/print.css">
<style>h1 { background: url('../images/band.png'); }</style>
<img src="logo.png"><img src="logo.png"><img src="data:image/png;base64,iVBORw0KGgo="><img src="https://cdn.example.com/x.png">
<img src="{{ invoice.customer }}">
<h1>{{ invoice.number }}</h1>
"""
_FILES = {
    "templates/logo.png": b"\x89PNG logo",
    "images/band.png": b"\x89PNG band",
    "styles/print.css": b'@font-face { font-family: Brand; src: url("../fonts/brand.woff2"); }\n',
    "fonts/brand.woff2": b"wOF2 brand",
    "notes/README.md": b"# Read by people, by no step\n",
}


def _write_method(*, method_dir: Path) -> None:
    """A method folder whose step prints from `templates/invoice.html`, with the files its template names and one no step reads."""
    method_dir.mkdir(parents=True)
    for tree_path, data in _FILES.items():
        (method_dir / tree_path).parent.mkdir(parents=True, exist_ok=True)
        (method_dir / tree_path).write_bytes(data)
    (method_dir / "templates" / "invoice.html").write_text(_TEMPLATE, encoding="utf-8")
    write_bundle(directory=method_dir, step_fields='format = "pdf"\ntemplate_file = "templates/invoice.html"')


@pytest.mark.usefixtures("stub_engines")
@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenTreeFilesRead:
    async def test_the_report_names_the_template_file_and_each_file_its_html_names(self, tmp_path: Path) -> None:
        """The template first, then its literal URLs' files, a stylesheet's own after it, each once; a computed URL is the print's."""
        method_dir = tmp_path / "method"
        _write_method(method_dir=method_dir)

        report = await validate_bundles_in_process(method_dir=method_dir, library_dirs_are_callers=True)

        assert report.tree_files_read == {
            _PIPE_REF: [
                TreeFileRead(tree_path="templates/invoice.html", use=TreeFileUse.TEMPLATE),
                TreeFileRead(tree_path="styles/print.css", use=TreeFileUse.TEMPLATE_ASSET),
                TreeFileRead(tree_path="images/band.png", use=TreeFileUse.TEMPLATE_ASSET),
                TreeFileRead(tree_path="templates/logo.png", use=TreeFileUse.TEMPLATE_ASSET),
                TreeFileRead(tree_path="fonts/brand.woff2", use=TreeFileUse.TEMPLATE_ASSET),
            ]
        }
        # A file no step reads, the README and the bundle itself, is in no reader's list.
        assert report.tree_file_readers == {
            "fonts/brand.woff2": [_PIPE_REF],
            "images/band.png": [_PIPE_REF],
            "styles/print.css": [_PIPE_REF],
            "templates/invoice.html": [_PIPE_REF],
            "templates/logo.png": [_PIPE_REF],
        }
        # Files are named by their tree paths, never by where the method sits on this host.
        assert str(tmp_path) not in report.model_dump_json(include={"tree_files_read", "tree_file_readers"})

    async def test_an_inline_template_s_files_resolve_against_its_bundle(self, tmp_path: Path) -> None:
        method_dir = tmp_path / "method"
        (method_dir / "bundles").mkdir(parents=True)
        (method_dir / "assets").mkdir()
        (method_dir / "assets" / "logo.png").write_bytes(b"\x89PNG inline")
        (method_dir / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")
        step_fields = "format = \"pdf\"\ntemplate = '''<img src=\"../assets/logo.png\"><h1>{{ invoice.number }}</h1>'''"
        write_bundle(directory=method_dir / "bundles", step_fields=step_fields, as_method=False)

        report = await validate_bundles_in_process(method_dir=method_dir, library_dirs_are_callers=True)

        assert report.tree_files_read == {_PIPE_REF: [TreeFileRead(tree_path="assets/logo.png", use=TreeFileUse.TEMPLATE_ASSET)]}
        assert report.tree_file_readers == {"assets/logo.png": [_PIPE_REF]}

    async def test_a_file_submitted_with_content_is_named_by_the_path_it_is_keyed_by(self) -> None:
        """Bundles from content strings sit at the root of the tree their files make, so the template's tree path is its key, collapsed."""
        report = await validate_bundles_in_process(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "docx"\ntemplate_file = "templates/invoice.docx"')],
            submitted_files={"./templates/invoice.docx": b"PK docx template bytes"},
        )

        assert report.tree_files_read == {_PIPE_REF: [TreeFileRead(tree_path="templates/invoice.docx", use=TreeFileUse.TEMPLATE)]}
        assert report.tree_file_readers == {"templates/invoice.docx": [_PIPE_REF]}

    async def test_a_step_laying_its_inputs_out_reads_no_file(self) -> None:
        report = await validate_bundles_in_process(mthds_contents=[PipeDocGenTestData.bundle(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)])

        assert report.tree_files_read == {_PIPE_REF: []}
        assert report.tree_file_readers == {}
