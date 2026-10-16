import copy
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pytest
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.doc_gen.exceptions import TemplateUrlRefusedError
from pipelex.cogt.doc_gen.render_job import METHOD_FILE_URL_PREFIX, RenderedDocument, RenderJob, RenderResources
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import (
    METHOD_MANIFEST,
    RecordingMethodFileStore,
    StubEngine,
    StubEngines,
    WorkerLikePipeRun,
    write_bundle,
)
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")\s]+)['"]?\s*\)""")
_DATA_IMAGE = "data:image/png;base64,iVBORw0KGgo="
_TEMPLATE = f"""<link rel="stylesheet" href="../styles/print.css">
<style>h1 {{ background: url('../images/band.png'); }}</style>
<img src="logo.png"><img src="{_DATA_IMAGE}">
<h1>{{{{ invoice.number }}}}</h1>
"""
_STYLESHEET = '@font-face { font-family: Brand; src: url("../fonts/brand.woff2"); }\nbody { font-family: Brand; }\n'
_ASSETS = {
    "templates/logo.png": b"\x89PNG logo",
    "images/band.png": b"\x89PNG band",
    "styles/print.css": _STYLESHEET.encode(),
    "fonts/brand.woff2": b"wOF2 brand",
}


class _ReferencesInHtml(HTMLParser):
    """The URLs an HTML document names that a printer reads: images, stylesheets, attachments, and the `url()` of its inline styles."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self._in_style = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        match tag:
            case "img":
                if attributes.get("src"):
                    self.references.append(attributes["src"] or "")
            case "link" | "a":
                if attributes.get("rel") in {"stylesheet", "attachment"} and attributes.get("href"):
                    self.references.append(attributes["href"] or "")
            case "style":
                self._in_style = True
            case _:
                pass

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    @override
    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.references.extend(_CSS_URL.findall(data))


class _AssetReadingEngine(StubEngine):
    """A stub engine that reads the files its HTML names as an HTML printer does, through the resources it is handed.

    Each URL is joined to the job's base URL, and each URL a stylesheet names to the stylesheet's own URL, as HTML and CSS
    resolve them; a `data:` URL is the printer's own to decode, and with no base URL a relative URL is handed as written.
    """

    def __init__(self) -> None:
        super().__init__()
        self.read: dict[str, bytes] = {}

    @override
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        self.jobs.append(job)
        parser = _ReferencesInHtml()
        parser.feed(job.html or "")
        for reference in parser.references:
            self._read(reference=reference, base_url=job.base_url, resources=resources)
        return RenderedDocument(data=b"%PDF-stub")

    def _read(self, *, reference: str, base_url: str | None, resources: RenderResources) -> None:
        if reference.startswith("data:"):
            return
        url = urljoin(base_url, reference) if base_url is not None else reference
        loaded = resources.load(uri=url, position=f"the file '{reference}' the document names")
        self.read[reference] = loaded.data
        if reference.endswith(".css"):
            for css_reference in _CSS_URL.findall(loaded.data.decode()):
                self._read(reference=css_reference, base_url=url, resources=resources)


def _write_files_no_template_may_read(*, method_dir: Path, outside_dir: Path) -> None:
    """Files on disk a template must never read: one outside the method, a hidden and a gitignored one, and the method's Python."""
    (outside_dir / "outside.png").write_bytes(b"outside")
    (method_dir / ".private").mkdir()
    (method_dir / ".private" / "logo.png").write_bytes(b"hidden")
    (method_dir / "ignored.png").write_bytes(b"ignored")
    (method_dir / ".gitignore").write_text("ignored.png\n", encoding="utf-8")
    (method_dir / "funcs").mkdir()
    (method_dir / "funcs" / "private_logic.py").write_text("SECRET = 42\n", encoding="utf-8")


def _write_method(*, method_dir: Path, template: str = _TEMPLATE) -> Path:
    """A method folder whose step prints from `templates/invoice.html`, with the files its template names beside it."""
    method_dir.mkdir(parents=True, exist_ok=True)
    for tree_path, data in _ASSETS.items():
        (method_dir / tree_path).parent.mkdir(parents=True, exist_ok=True)
        (method_dir / tree_path).write_bytes(data)
    (method_dir / "templates" / "invoice.html").write_text(template, encoding="utf-8")
    return write_bundle(directory=method_dir, step_fields='format = "pdf"\ntemplate_file = "templates/invoice.html"')


async def _run_from_its_folder(*, bundle_path: Path) -> None:
    await PipelexMTHDSProtocol(bundle_uris=[str(bundle_path)]).execute(
        mthds_contents=[bundle_path.read_text(encoding="utf-8")], inputs=PipeDocGenTestData.INVOICE_INPUTS
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenTemplateAssets:
    @pytest.fixture
    def engine(self, stub_engines: StubEngines) -> _AssetReadingEngine:
        stub_engines.engine = _AssetReadingEngine()
        return stub_engines.engine

    async def test_a_template_file_prints_with_the_image_stylesheet_and_font_beside_it_in_its_method(
        self, engine: _AssetReadingEngine, tmp_path: Path
    ) -> None:
        """Relative URLs resolve against the template, and a stylesheet's against the stylesheet, all read from the method tree."""
        await _run_from_its_folder(bundle_path=_write_method(method_dir=tmp_path / "method"))

        (job,) = engine.jobs
        assert job.base_url is not None
        assert job.base_url.startswith(METHOD_FILE_URL_PREFIX)
        assert job.base_url.endswith("/templates/invoice.html")
        assert engine.read == {
            "../styles/print.css": _ASSETS["styles/print.css"],
            "../fonts/brand.woff2": _ASSETS["fonts/brand.woff2"],
            "../images/band.png": _ASSETS["images/band.png"],
            "logo.png": _ASSETS["templates/logo.png"],
        }
        assert _DATA_IMAGE in (job.html or "")

    async def test_a_print_on_a_remote_worker_reads_the_files_through_the_method_file_store(
        self, engine: _AssetReadingEngine, remote_worker: WorkerLikePipeRun, recording_store: RecordingMethodFileStore, tmp_path: Path
    ) -> None:
        """The crate names the tree by digest, and every file the template names is read from the store under the run's read scope."""
        remote_worker.worker_read_scope = "acme/runs"

        await _run_from_its_folder(bundle_path=_write_method(method_dir=tmp_path / "method"))

        assert remote_worker.received_crates
        assert engine.read["logo.png"] == _ASSETS["templates/logo.png"]
        assert engine.read["../fonts/brand.woff2"] == _ASSETS["fonts/brand.woff2"]
        assert set(recording_store.read_scopes) == {"acme/runs"}

    async def test_an_inline_template_resolves_its_relative_urls_against_its_bundle(self, engine: _AssetReadingEngine, tmp_path: Path) -> None:
        method_dir = tmp_path / "method"
        (method_dir / "bundles").mkdir(parents=True)
        (method_dir / "assets").mkdir()
        (method_dir / "assets" / "logo.png").write_bytes(b"\x89PNG inline")
        (method_dir / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")
        step_fields = "format = \"pdf\"\ntemplate = '''<img src=\"../assets/logo.png\"><h1>{{ invoice.number }}</h1>'''"
        bundle_path = write_bundle(directory=method_dir / "bundles", step_fields=step_fields, as_method=False)

        await _run_from_its_folder(bundle_path=bundle_path)

        (job,) = engine.jobs
        assert job.base_url is not None
        assert job.base_url.endswith("/bundles/invoice.mthds")
        assert engine.read == {"../assets/logo.png": b"\x89PNG inline"}

    @pytest.mark.parametrize(
        ("reference", "expected"),
        [
            pytest.param("../../outside.png", "climbs above the root of its method tree", id="outside_the_tree"),
            pytest.param("../../../../../../outside.png", "climbs above the root of its method tree", id="far_outside_the_tree"),
            pytest.param("/outside.png", "starts with '/'", id="root_relative"),
            pytest.param("missing.png", "'templates/missing.png', which is not a file of the tree", id="absent"),
            pytest.param("../.private/logo.png", "kept out by a path segment starting with a dot", id="hidden"),
            pytest.param("../ignored.png", "kept out by a .gitignore pattern", id="gitignored"),
            pytest.param("../funcs/private_logic.py", "which is not an image, a stylesheet or a font", id="not_an_asset"),
        ],
    )
    async def test_a_literal_url_naming_no_asset_of_the_tree_is_refused_when_the_method_loads(
        self, engine: _AssetReadingEngine, tmp_path: Path, reference: str, expected: str
    ) -> None:
        """A URL the template writes as it is is the method's own, so a missing or forbidden file fails the load, not a print."""
        method_dir = tmp_path / "method"
        bundle_path = _write_method(method_dir=method_dir, template=f'<img src="{reference}"><h1>{{{{ invoice.number }}}}</h1>')
        _write_files_no_template_may_read(method_dir=method_dir, outside_dir=tmp_path)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        # The report names the caller's own bundle file as its source; the message names files by their tree paths alone.
        message = exc_info.value.message
        assert f"names '{reference}' in the template file 'templates/invoice.html'" in message
        assert expected in message
        assert str(tmp_path) not in message
        assert engine.jobs == []

    @pytest.mark.parametrize(
        ("element", "reference", "expected"),
        [
            pytest.param("img", "../../outside.png", "climbs above the root of the method tree", id="outside_the_tree"),
            pytest.param("img", "missing.png", "'templates/missing.png', which is not a file", id="absent"),
            pytest.param("img", "../.private/logo.png", "'.private/logo.png', which is not a file", id="hidden"),
            pytest.param("img", "../METHODS.toml", "'METHODS.toml', which is not an image, a stylesheet or a font", id="manifest"),
            pytest.param(
                "attachment", "../funcs/private_logic.py", "'funcs/private_logic.py', which is not an image, a stylesheet or a font", id="attachment"
            ),
        ],
    )
    async def test_a_url_a_run_s_input_supplies_reads_only_an_asset_of_the_tree(
        self, engine: _AssetReadingEngine, tmp_path: Path, element: str, reference: str, expected: str
    ) -> None:
        """A URL interpolated from the run's inputs is checked at print: it never reads outside the tree, nor a file that is no asset.

        A printer embeds a `rel="attachment"` link's file in the PDF, so a caller who may run a method but not read it would
        otherwise take its Python home in the document.
        """
        method_dir = tmp_path / "method"
        tag = '<img src="{{ invoice.customer }}">' if element == "img" else '<a rel="attachment" href="{{ invoice.customer }}">terms</a>'
        bundle_path = _write_method(method_dir=method_dir, template=f"{tag}<h1>{{{{ invoice.number }}}}</h1>")
        _write_files_no_template_may_read(method_dir=method_dir, outside_dir=tmp_path)
        inputs = copy.deepcopy(PipeDocGenTestData.INVOICE_INPUTS)
        inputs["invoice"]["content"]["customer"] = reference

        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol(bundle_uris=[str(bundle_path)]).execute(
                mthds_contents=[bundle_path.read_text(encoding="utf-8")], inputs=inputs
            )

        report = str(exc_info.value.to_error_report().model_dump())
        assert TemplateUrlRefusedError.__name__ in report
        assert expected in report
        assert str(tmp_path) not in report
        assert engine.read == {}

    async def test_a_bundle_named_alone_is_told_to_hand_over_its_folder(self, engine: _AssetReadingEngine, tmp_path: Path) -> None:
        """With no METHODS.toml at or above it, the bundle's tree is that one file, so the logo beside it is out of reach."""
        (tmp_path / "logo.png").write_bytes(b"\x89PNG logo")
        step_fields = "format = \"pdf\"\ntemplate = '''<img src=\"logo.png\"><h1>{{ invoice.number }}</h1>'''"
        bundle_path = write_bundle(directory=tmp_path, step_fields=step_fields, as_method=False)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=bundle_path)

        report = str(exc_info.value.to_error_report().model_dump())
        assert "Hand over the method's directory instead" in report
        assert engine.jobs == []

    async def test_an_inline_template_of_a_bundle_with_no_method_tree_names_no_file(self, engine: _AssetReadingEngine) -> None:
        """Bundles loaded from content strings with no file submitted beside them have no tree: a literal URL fails the load."""
        step_fields = "format = \"pdf\"\ntemplate = '''<img src=\"logo.png\"><h1>{{ invoice.number }}</h1>'''"

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)])

        assert "belongs to no method tree" in str(exc_info.value.to_error_report().model_dump())
        assert engine.jobs == []

    async def test_a_url_a_run_s_input_supplies_names_no_file_when_the_template_has_no_method_tree(self, engine: _AssetReadingEngine) -> None:
        step_fields = "format = \"pdf\"\ntemplate = '''<img src=\"{{ invoice.customer }}\"><h1>{{ invoice.number }}</h1>'''"
        inputs = copy.deepcopy(PipeDocGenTestData.INVOICE_INPUTS)
        inputs["invoice"]["content"]["customer"] = "logo.png"

        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)], inputs=inputs)

        report = str(exc_info.value.to_error_report().model_dump())
        assert TemplateUrlRefusedError.__name__ in report
        assert "belongs to no method's folder" in report
        (job,) = engine.jobs
        assert job.base_url is None
        assert engine.read == {}
