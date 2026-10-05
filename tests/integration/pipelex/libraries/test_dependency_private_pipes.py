"""A dependency package's private pipes travel with the exported pipes that call them, and stay private to the package.

A package's public pipes are the ones its manifest exports, by domain, and its bundles' `main_pipe`. Whatever they reach
inside the package is loaded with them; a private pipe nothing public reaches is not built at all. A consumer referencing
a private pipe, loaded or withheld, is refused at load with `UNEXPORTED_PIPE_DEPENDENCY`.

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
    write_consumer,
)
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData, TwoDomainPackageTestData

PROBE_ALIAS = ProbePackageTestData.DEP_ALIAS


class TestDependencyPrivatePipes:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_exported_controller_runs_its_private_helper(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            assert "probe_dep.helper" in library.dependency_libraries[PROBE_ALIAS].pipe_library.get_pipes_dict()
            with scoped_current_library(library_id=library_id):
                graph_spec = await dry_run_pipe_in_process(
                    pipe=library.pipe_library.get_required_pipe(pipe_code="probe_consumer.go"),
                    library_id=library_id,
                )
        finally:
            library_manager.teardown(library_id=library_id)

        assert "DEPENDENCY helper" in graph_spec.model_dump_json()

    def test_a_consumer_cannot_reference_a_private_helper(self, tmp_path: Path, mocker: MockerFixture) -> None:
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        private_ref = f"{PROBE_ALIAS}->probe_dep.helper"
        consumer_files = write_consumer(
            root=tmp_path,
            bundles={
                "consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE,
                "sneaky.mthds": ProbePackageTestData.consumer_calling(pipe_ref=private_ref).replace("probe_consumer", "probe_sneaky"),
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
            (PipeValidationErrorType.UNEXPORTED_PIPE_DEPENDENCY, "go", private_ref)
        ]

    @pytest.mark.parametrize("orphan_ref", [f"{PROBE_ALIAS}->probe_dep.orphan", f"{PROBE_ALIAS}->orphan"])
    def test_a_reference_to_a_withheld_private_pipe_is_refused_as_unexported(self, tmp_path: Path, mocker: MockerFixture, orphan_ref: str) -> None:
        """`orphan` is never built, but the package declares it: a reference to it is unexported, not missing."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = write_consumer(
            root=tmp_path,
            bundles={
                "consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE,
                "sneaky.mthds": ProbePackageTestData.consumer_calling(pipe_ref=orphan_ref).replace("probe_consumer", "probe_sneaky"),
            },
        )
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with pytest.raises(LibraryLoadingError) as exc_info:
                library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
        finally:
            library_manager.teardown(library_id=library_id)

        assert refusal_types(exc_info.value) == [PipeValidationErrorType.UNEXPORTED_PIPE_DEPENDENCY]
        assert "does not export" in str(exc_info.value)

    def test_a_private_pipe_nothing_public_reaches_is_not_loaded(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`orphan` names a model no deck defines: it is never built, so it cannot refuse the consumer's load."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
            child_pipe_refs = set(library.dependency_libraries[PROBE_ALIAS].pipe_library.get_pipes_dict())
        finally:
            library_manager.teardown(library_id=library_id)

        assert child_pipe_refs == {"probe_dep.entry", "probe_dep.helper"}

    def test_exports_are_scoped_by_domain(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Exporting `dom_a.x` does not export `dom_b.x`, though both are named `x`."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_package(
            root=tmp_path,
            method_name=TwoDomainPackageTestData.METHOD_NAME,
            manifest=TwoDomainPackageTestData.MANIFEST,
            bundles={"dom_a.mthds": TwoDomainPackageTestData.BUNDLE_A, "dom_b.mthds": TwoDomainPackageTestData.BUNDLE_B},
        )
        private_ref = f"{TwoDomainPackageTestData.DEP_ALIAS}->dom_b.x"
        consumer_files = write_consumer(
            root=tmp_path,
            bundles={
                "public.mthds": ProbePackageTestData.consumer_calling(pipe_ref=f"{TwoDomainPackageTestData.DEP_ALIAS}->dom_a.x"),
                "sneaky.mthds": ProbePackageTestData.consumer_calling(pipe_ref=private_ref).replace("probe_consumer", "probe_sneaky"),
            },
        )
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        try:
            with pytest.raises(LibraryLoadingError) as exc_info:
                library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
        finally:
            library_manager.teardown(library_id=library_id)

        assert refusal_types(exc_info.value) == [PipeValidationErrorType.UNEXPORTED_PIPE_DEPENDENCY]

    def test_the_entry_door_reaches_a_private_helper_by_hand(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`[exports]` governs references from inside a method, not a pipe a person names at a CLI argument or an API field."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
            helper = library.pipe_library.get_required_entry_pipe(pipe_code=f"{PROBE_ALIAS}->probe_dep.helper")
        finally:
            library_manager.teardown(library_id=library_id)

        assert helper.description == "DEPENDENCY helper"

    def test_a_private_helper_named_through_the_package_alias_travels_with_its_caller(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`entry` names its private helper as `alias->helper`, with no domain: the helper is still loaded, and the call allowed."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_probe(
            root=tmp_path,
            manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY,
            bundle=ProbePackageTestData.DEP_BUNDLE_CALLING_ITS_HELPER_BY_ALIAS,
        )
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
            child_pipe_refs = set(library.dependency_libraries[PROBE_ALIAS].pipe_library.get_pipes_dict())
        finally:
            library_manager.teardown(library_id=library_id)

        assert child_pipe_refs == {"probe_dep.entry", "probe_dep.helper"}

    def test_a_private_pipe_sharing_an_exported_pipe_s_code_does_not_make_a_bare_reference_ambiguous(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """`dom_a.x` is exported and calls the private `dom_b.x`: a consumer's `alias->x` means the exported one."""
        isolate_installed_methods(mocker=mocker, root=tmp_path)
        install_package(
            root=tmp_path,
            method_name=TwoDomainPackageTestData.METHOD_NAME,
            manifest=TwoDomainPackageTestData.MANIFEST,
            bundles={"dom_a.mthds": TwoDomainPackageTestData.BUNDLE_A, "dom_b.mthds": TwoDomainPackageTestData.BUNDLE_B},
        )
        bare_ref = f"{TwoDomainPackageTestData.DEP_ALIAS}->x"
        consumer_files = write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.consumer_calling(pipe_ref=bare_ref)})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
            resolved = library.pipe_library.get_required_pipe(pipe_code=bare_ref)
        finally:
            library_manager.teardown(library_id=library_id)

        assert resolved.pipe_ref == "dom_a.x"
