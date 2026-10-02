from pathlib import Path

import pytest
from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from pytest_mock import MockerFixture

from pipelex.core.pipes.exceptions import PipeLoadRefusalError
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library import Library
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager import LibraryManager
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_PACKAGE_ADDRESS = "github.com/acme/invoicing"
_TEMPLATE = "<h1>{{ invoice.number }}</h1>"


@pytest.mark.usefixtures("stub_engines")
class TestPipeDocGenDependencyTemplateFile:
    def _load_dependency(self, *, mocker: MockerFixture, package_root: Path, template: str | None) -> Library:
        """Load the invoice bundle, whose step reads `invoice.html`, as a dependency package installed at `package_root`."""
        bundle_dir = package_root / "invoice"
        bundle_dir.mkdir(parents=True)
        if template is not None:
            (bundle_dir / "invoice.html").write_text(template, encoding="utf-8")
        mthds_file = bundle_dir / "invoice.mthds"
        mthds_file.write_text(PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate_file = "invoice.html"'), encoding="utf-8")
        resolved_dep = ResolvedDependency(
            alias="invoicing",
            address=_PACKAGE_ADDRESS,
            manifest=MethodsManifest(address=_PACKAGE_ADDRESS, version="1.0.0", description="Invoicing methods"),
            package_root=package_root,
            mthds_files=[mthds_file],
            exported_pipe_codes=None,
        )
        library = LibraryFactory.make_empty()
        mocker.patch.object(get_library_manager(), "get_current_library", return_value=library)
        LibraryManager()._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            library=library, package_address=_PACKAGE_ADDRESS, resolved_dep=resolved_dep
        )
        return library

    def test_a_dependency_s_template_file_is_found_beside_its_bundle(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A dependency's source names the package, not a path, and its template file still loads from the installed package."""
        library = self._load_dependency(mocker=mocker, package_root=tmp_path, template=_TEMPLATE)

        pipe = library.dependency_libraries["invoicing"].pipe_library.get_required_pipe(pipe_code="doc_gen_tests.print_invoice")
        assert isinstance(pipe, PipeDocGen)
        assert pipe.template == _TEMPLATE

    def test_a_dependency_s_missing_template_file_is_refused_without_the_host_path(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The refusal is located at the package's address and names the template file as the method does, never where the host installed it."""
        with pytest.raises(PipeLoadRefusalError) as exc_info:
            self._load_dependency(mocker=mocker, package_root=tmp_path, template=None)

        refusal = exc_info.value
        assert refusal.source == f"{_PACKAGE_ADDRESS}/invoice/invoice.mthds"
        report = str(refusal.to_error_report().model_dump())
        assert "'invoice.html', which does not exist beside its bundle" in report
        assert str(tmp_path) not in report
