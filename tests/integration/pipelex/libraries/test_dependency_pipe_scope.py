"""A dependency package's pipes call their own sub-pipes, never the consumer's, and its private pipes stay private.

A dependency is registered in the consumer's library under `alias->domain.code`, and every reader of a sub-pipe ref —
validation, the pre-run walks, execution — looks the ref up in the consumer's library. So a ref the package wrote
must be stored in that aliased form: stored as `domain.code`, it finds nothing, and the consumer's load fails, or it
finds the consumer's own pipe of the same `domain.code` and runs that one in the dependency's place, silently.

The packages are invented and installed under a temporary `.mthds/methods/`, with fetch-on-miss disabled.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.pipe_run.dry_run_in_process import dry_run_pipe_in_process
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.libraries.installed_packages import (
    install_package,
    install_probe,
    isolate_installed_methods,
    refusal_types,
    sole_step_target,
    write_consumer,
)
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData, TwoPackagesSharingADomainTestData

PROBE_ALIAS = ProbePackageTestData.DEP_ALIAS


class TestDependencyPipeScope:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_dependency_runs_its_own_helper_not_the_consumer_s(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The consumer declares `probe_dep.helper` too: the dependency's entry still reaches its own helper."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path)
        consumer_files = write_consumer(
            root=tmp_path,
            bundles={
                "consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE,
                "consumer_probe_dep.mthds": ProbePackageTestData.CONSUMER_HELPER_BUNDLE,
            },
        )
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            step_target = sole_step_target(library=library, pipe_key=f"{PROBE_ALIAS}->probe_dep.entry")
            resolved_helper = library.pipe_library.get_required_pipe(pipe_code=step_target)
            dependency_helper = library.dependency_libraries[PROBE_ALIAS].pipe_library.get_required_pipe(pipe_code="probe_dep.helper")
            assert resolved_helper is dependency_helper
            assert resolved_helper.description == "DEPENDENCY helper"

            with scoped_current_library(library_id=library_id):
                graph_spec = await dry_run_pipe_in_process(
                    pipe=library.pipe_library.get_required_pipe(pipe_code="probe_consumer.go"),
                    library_id=library_id,
                )
        finally:
            library_manager.teardown(library_id=library_id)

        graph_json = graph_spec.model_dump_json()
        assert "DEPENDENCY helper" in graph_json
        assert "CONSUMER helper" not in graph_json

    def test_a_dependency_with_an_internal_controller_loads_alone(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """With nothing of the dependency's domain in the consumer, the load succeeds and the entry needs the helper's input."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path)
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            with scoped_current_library(library_id=library_id):
                entry = library.pipe_library.get_required_pipe(pipe_code=f"{PROBE_ALIAS}->probe_dep.entry")
                needed_input_names = set(entry.needed_inputs().root)
        finally:
            library_manager.teardown(library_id=library_id)

        assert needed_input_names == {"data"}

    def test_two_packages_declaring_the_same_domain_code_each_call_their_own(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        for name in TwoPackagesSharingADomainTestData.PACKAGES:
            install_package(
                root=tmp_path,
                method_name=name,
                manifest=TwoPackagesSharingADomainTestData.manifest(name=name),
                bundles={"shared.mthds": TwoPackagesSharingADomainTestData.bundle(name=name)},
            )
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": TwoPackagesSharingADomainTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            reached: dict[str, str] = {}
            for name, alias in TwoPackagesSharingADomainTestData.PACKAGES.items():
                step_target = sole_step_target(library=library, pipe_key=f"{alias}->shared.entry")
                reached[name] = library.pipe_library.get_required_pipe(pipe_code=step_target).description
        finally:
            library_manager.teardown(library_id=library_id)

        assert reached == {"left": "LEFT helper", "right": "RIGHT helper"}

    def test_a_missing_pipe_of_a_loaded_dependency_is_refused(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A typo in a reference to a loaded package is reported as what it is, not as an extraneous input."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path)
        missing_ref = f"{PROBE_ALIAS}->probe_dep.nope"
        consumer_files = write_consumer(
            root=tmp_path,
            bundles={
                "consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE,
                "typo.mthds": ProbePackageTestData.consumer_calling(pipe_ref=missing_ref).replace("probe_consumer", "probe_typo"),
            },
        )
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with pytest.raises(LibraryLoadingError) as exc_info:
                library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
        finally:
            library_manager.teardown(library_id=library_id)

        items = exc_info.value.pipe_concept_validation_errors or []
        assert [(item.error_type, item.pipe_code, item.missing_pipe_code) for item in items] == [
            (PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY, "go", missing_ref)
        ]
        assert "has no pipe" in str(exc_info.value)

    def test_a_crate_of_the_consumer_loads_without_its_dependency(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A worker loads the consumer's crate with no package loaded: a reference into an alias never loaded is still tolerated."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path)
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        worker_library_id, worker_library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None

            library_manager.load_from_crate(library_id=worker_library_id, crate=crate)

            assert "probe_consumer.go" in worker_library.pipe_library.get_pipes_dict()
            assert not worker_library.dependency_libraries
        finally:
            library_manager.teardown(library_id=worker_library_id)
            library_manager.teardown(library_id=library_id)

    def test_a_consumer_pipe_wrapping_a_dependency_pipe_of_the_same_domain_code_needs_its_inputs(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The walk over needed inputs must not take the dependency's `probe_dep.entry` for the consumer's, already visited."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path)
        consumer_files = write_consumer(
            root=tmp_path, bundles={"consumer_probe_dep.mthds": ProbePackageTestData.CONSUMER_ENTRY_WRAPPING_THE_DEPENDENCY_BUNDLE}
        )
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            with scoped_current_library(library_id=library_id):
                needed_input_names = set(library.pipe_library.get_required_pipe(pipe_code="probe_dep.entry").needed_inputs().root)
        finally:
            library_manager.teardown(library_id=library_id)

        assert needed_input_names == {"data"}

    def test_a_dependency_pipe_that_fails_to_build_is_refused_naming_why(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The package declares `helper`, so a reference to it is not to a pipe the package lacks: the refusal says it failed to build."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path, bundle=ProbePackageTestData.DEP_BUNDLE_WITH_AN_UNBUILDABLE_HELPER)
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with pytest.raises(LibraryLoadingError) as exc_info:
                library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
        finally:
            library_manager.teardown(library_id=library_id)

        assert refusal_types(exc_info.value) == [PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY]
        assert "could not build" in str(exc_info.value)
        assert "no_such_function_anywhere" in str(exc_info.value)
        assert "has no pipe" not in str(exc_info.value)
