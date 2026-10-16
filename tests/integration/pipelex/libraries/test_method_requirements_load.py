from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.exceptions import MethodRequirementsNotMetError, PipeFuncPackageSetUnstatedError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer, PipeFuncPackageOfferFactoryFn, PipeFuncPackageOfferRegistry
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig
from pipelex.system.registries.func_registry import func_registry
from tests.integration.pipelex.libraries.installed_packages import isolate_installed_methods, vendor_probe
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData

_ABSENT_PACKAGE = "pipelex-requirements-test-absent"
_FUNCTION_NAME = "requirements_test_crunch"
_OFFER = PipeFuncPackageOffer(
    environment="the Daytona sandbox snapshot 'pipelex-base-test'",
    distributions={"pandas": "2.2.3", "openpyxl": "3.1.5"},
    marker_environment={"python_version": "3.12", "sys_platform": "linux"},
)
_MANIFEST = '[package]\naddress = "github.com/pipelex-tests/requirements-load"\nversion = "1.0.0"\ndescription = "A method with requirements"\n'

_MTHDS = f"""\
domain = "requirements_load"
main_pipe = "crunch"

[concept]
Note = "A note produced by the method's own code"

[pipe.crunch]
type = "PipeFunc"
description = "Crunch numbers in the method's own code"
inputs = {{}}
output = "Note"
function_name = "{_FUNCTION_NAME}"
"""


def _funcs_py(*, sentinel: Path) -> str:
    """A PipeFunc module whose import, were it ever imported, would write the sentinel file."""
    return f"""\
from pathlib import Path

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

Path({str(sentinel)!r}).write_text("imported", encoding="utf-8")


@pipe_func(name="{_FUNCTION_NAME}")
async def {_FUNCTION_NAME}(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="crunched")
"""


def _method(*, directory: Path, requirements: str, sentinel: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.mthds").write_text(_MTHDS, encoding="utf-8")
    (directory / "funcs.py").write_text(_funcs_py(sentinel=sentinel), encoding="utf-8")
    (directory / "requirements.txt").write_text(requirements, encoding="utf-8")
    return directory


def _offering(mocker: MockerFixture, *, offer: PipeFuncPackageOffer | None) -> None:
    """Register what the `sandbox` execution mode's plugin would state, or nothing at all when `offer` is None."""

    def stated_offer(_config: PipeFuncConfig) -> PipeFuncPackageOffer | None:
        return offer

    offers: dict[str, PipeFuncPackageOfferFactoryFn] = {} if offer is None else {"sandbox": stated_offer}
    mocker.patch("pipelex.libraries.package_environments.get_pipe_func_package_offer_registry", return_value=PipeFuncPackageOfferRegistry(offers))


class TestMethodRequirementsLoad:
    def test_locally_an_unmet_requirement_refuses_the_method_before_its_python_is_imported(self, tmp_path: Path) -> None:
        sentinel = tmp_path / "funcs-module-ran"
        library_dir = _method(directory=tmp_path / "method", requirements=f"pydantic>=2\n{_ABSENT_PACKAGE}>=1\n", sentinel=sentinel)
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id), pytest.raises(MethodRequirementsNotMetError) as exc_info:
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
        finally:
            library_manager.teardown(library_id=library_id)

        assert f"The method rooted at '{library_dir.resolve()}'" in exc_info.value.message
        assert f"line 2 '{_ABSENT_PACKAGE}>=1'" in exc_info.value.message
        assert "uv pip install --python" in exc_info.value.message
        assert not sentinel.exists(), "the method's Python was imported before its requirements were checked"
        assert func_registry.get_function(_FUNCTION_NAME) is None

    def test_a_bundle_file_named_alone_loads_under_its_trees_requirements_on_every_load(self, tmp_path: Path) -> None:
        """A retry of the same blueprint, placed in its tree by the refused load, is refused again rather than taken as judged."""
        sentinel = tmp_path / "funcs-module-ran"
        method_dir = _method(directory=tmp_path / "method", requirements=f"{_ABSENT_PACKAGE}\n", sentinel=sentinel)
        (method_dir / "METHODS.toml").write_text(_MANIFEST, encoding="utf-8")
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=method_dir / "main.mthds")
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                with pytest.raises(MethodRequirementsNotMetError, match=_ABSENT_PACKAGE):
                    library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
                assert blueprint.tree_bundle is not None
                with pytest.raises(MethodRequirementsNotMetError, match=_ABSENT_PACKAGE):
                    library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
        finally:
            library_manager.teardown(library_id=library_id)

    def test_a_dependency_package_whose_requirements_are_not_met_refuses_the_load(self, mocker: MockerFixture, tmp_path: Path) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods")
        package_dir = methods_dir / ProbePackageTestData.METHOD_NAME
        sentinel = tmp_path / "funcs-module-ran"
        (package_dir / "funcs.py").write_text(_funcs_py(sentinel=sentinel), encoding="utf-8")
        (package_dir / "requirements.txt").write_text(f"pydantic>=2\n{_ABSENT_PACKAGE}>=1\n", encoding="utf-8")
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=ProbePackageTestData.CONSUMER_BUNDLE)
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id), pytest.raises(MethodRequirementsNotMetError) as exc_info:
                library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint], methods_dirs=[methods_dir])
        finally:
            library_manager.teardown(library_id=library_id)

        message = exc_info.value.message
        assert message.startswith(f"The method package '{ProbePackageTestData.DEP_ALIAS}' needs Python packages")
        assert f"line 2 '{_ABSENT_PACKAGE}>=1' ({_ABSENT_PACKAGE} is missing)" in message
        assert str(tmp_path) not in message
        items = exc_info.value.blueprint_validation_errors
        assert [(item.source, item.line) for item in items] == [(f"{ProbePackageTestData.DEP_ALIAS}/requirements.txt", 2)]
        assert not sentinel.exists()

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_on_a_sandbox_hosted_deployment_the_stated_package_set_is_the_whole_offer(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _offering(mocker, offer=_OFFER)
        sentinel = tmp_path / "funcs-module-ran"
        refused_dir = _method(directory=tmp_path / "refused", requirements="pandas>=2\npandas>=3\n", sentinel=sentinel)
        accepted_dir = _method(directory=tmp_path / "accepted", requirements="pandas>=2\nopenpyxl==3.1.5\n", sentinel=sentinel)
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id):
                with pytest.raises(MethodRequirementsNotMetError) as exc_info:
                    library_manager.load_libraries(library_id=library_id, library_dirs=[refused_dir])
                assert library_manager.get_crate(library_id=library_id) is None

                pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[accepted_dir])
                assert [pipe.code for pipe in pipes] == ["crunch"]
                crate = library_manager.get_crate(library_id=library_id)
                assert crate is not None
                assert "funcs.py" in crate.python_sources
        finally:
            library_manager.teardown(library_id=library_id)

        # A load's refusal names the method's root: it is the caller's own disk's, or the host's fault, withheld from the caller.
        message = exc_info.value.message
        assert message.startswith(f"The method rooted at '{refused_dir.resolve()}' needs Python packages that the Daytona sandbox snapshot")
        assert "line 2 'pandas>=3' (pandas 2.2.3 is there)" in message
        assert not sentinel.exists()

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_sandbox_hosted_deployment_stating_no_package_set_refuses_a_method_with_requirements(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _offering(mocker, offer=None)
        library_dir = _method(directory=tmp_path / "method", requirements="pandas\n", sentinel=tmp_path / "funcs-module-ran")
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with scoped_current_library(library_id=library_id), pytest.raises(PipeFuncPackageSetUnstatedError, match="'sandbox' execution mode"):
                library_manager.load_libraries(library_id=library_id, library_dirs=[library_dir])
        finally:
            library_manager.teardown(library_id=library_id)
