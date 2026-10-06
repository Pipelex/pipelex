"""A load's own methods directories answer a reference by address first, and are never written.

A host that receives a bundle with the packages it calls hands the engine their directory, laid out like
`.mthds/methods/`, as `methods_dirs`. A reference is looked up there by manifest identity before the installed stores
and fetch-on-miss, so the shipped copy answers even with fetching off, wins over an installed copy of the same
address, and is never installed anywhere.

The packages are invented; every test isolates the installed store, and none reaches the network.
"""

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library import Library
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.libraries.installed_packages import install_probe_globally, isolate_installed_methods, vendor_probe
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData

PROBE_ALIAS = ProbePackageTestData.DEP_ALIAS
VENDORED_HELPER = "DEPENDENCY helper"
INSTALLED_HELPER = "INSTALLED helper"
INSTALLED_BUNDLE = ProbePackageTestData.DEP_BUNDLE.replace(VENDORED_HELPER, INSTALLED_HELPER)


def _load_consumer(*, consumer: str, methods_dirs: list[Path] | None) -> tuple[str, Library]:
    """Open a library and load the consumer into it; the caller tears it down."""
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=consumer)
    library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint], methods_dirs=methods_dirs)
    return library_id, library


def _helper_description(*, library: Library, alias: str = PROBE_ALIAS) -> str | None:
    return library.dependency_libraries[alias].pipe_library.get_required_pipe(pipe_code="probe_dep.helper").description


class TestVendoredMethodsDirs:
    def test_a_shipped_package_answers_the_reference_with_fetching_off(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        resolve_mock = mocker.patch("pipelex.libraries.library_manager.resolve_address_based_method")
        methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods")

        library_id, library = _load_consumer(consumer=ProbePackageTestData.CONSUMER_BUNDLE, methods_dirs=[methods_dir])
        try:
            assert _helper_description(library=library) == VENDORED_HELPER
        finally:
            get_library_manager().teardown(library_id=library_id)
        # A hit goes neither to the installed stores nor to fetch-on-miss, and nothing is installed.
        resolve_mock.assert_not_called()
        assert not (tmp_path / "global-methods").exists()

    def test_the_shipped_copy_wins_over_an_installed_one(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe_globally(root=tmp_path, bundle=INSTALLED_BUNDLE)
        methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods")

        library_id, library = _load_consumer(consumer=ProbePackageTestData.CONSUMER_BUNDLE, methods_dirs=[methods_dir])
        try:
            assert _helper_description(library=library) == VENDORED_HELPER
        finally:
            get_library_manager().teardown(library_id=library_id)

    def test_a_miss_in_the_shipped_packages_goes_on_to_the_installed_store(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe_globally(root=tmp_path, bundle=INSTALLED_BUNDLE)
        empty_methods_dir = tmp_path / "request-methods"
        empty_methods_dir.mkdir()

        library_id, library = _load_consumer(consumer=ProbePackageTestData.CONSUMER_BUNDLE, methods_dirs=[empty_methods_dir])
        try:
            assert _helper_description(library=library) == INSTALLED_HELPER
        finally:
            get_library_manager().teardown(library_id=library_id)

    def test_a_tag_pin_answered_by_a_shipped_copy_uses_it_and_says_so(
        self, tmp_path: Path, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods")
        pinned_alias = f"{PROBE_ALIAS}@v9.9.9"

        with caplog.at_level(logging.WARNING):
            library_id, library = _load_consumer(
                consumer=ProbePackageTestData.consumer_calling(pipe_ref=f"{pinned_alias}->probe_dep.entry"), methods_dirs=[methods_dir]
            )
        try:
            assert _helper_description(library=library, alias=pinned_alias) == VENDORED_HELPER
        finally:
            get_library_manager().teardown(library_id=library_id)
        warnings = [record.message for record in caplog.records if record.levelno == logging.WARNING and "@v9.9.9" in record.message]
        assert len(warnings) == 1, warnings
        assert PROBE_ALIAS in warnings[0]
        assert "1.0.0" in warnings[0]

    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_runner_protocol_runs_the_shipped_dependency(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe_globally(root=tmp_path, bundle=INSTALLED_BUNDLE)
        methods_dir = vendor_probe(methods_dir=tmp_path / "request-methods")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config, methods_dirs=[methods_dir])

        response = await runner.execute(pipe_code="go", mthds_contents=[ProbePackageTestData.CONSUMER_BUNDLE], inputs={"data": "hello"})

        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        descriptions = {node.description for node in graph_spec.nodes}
        assert VENDORED_HELPER in descriptions
        assert INSTALLED_HELPER not in descriptions
