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
from pipelex.libraries.library import Library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_run.dry_run_in_process import dry_run_pipe_in_process
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData, TwoDomainPackageTestData, TwoPackagesSharingADomainTestData

PROBE_ALIAS = ProbePackageTestData.DEP_ALIAS


def _isolate_installed_methods(*, mocker: MockerFixture, root: Path) -> None:
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", root / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", root / "project-methods")
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)


def _install_package(*, root: Path, method_name: str, manifest: str, bundles: dict[str, str]) -> None:
    package_dir = root / ".mthds" / "methods" / method_name
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(manifest, encoding="utf-8")
    for file_name, bundle in bundles.items():
        (package_dir / file_name).write_text(bundle, encoding="utf-8")


def _install_probe(*, root: Path, manifest: str = ProbePackageTestData.MANIFEST_EXPORTING_EVERYTHING) -> None:
    _install_package(
        root=root,
        method_name=ProbePackageTestData.METHOD_NAME,
        manifest=manifest,
        bundles={"probe_dep.mthds": ProbePackageTestData.DEP_BUNDLE},
    )


def _write_consumer(*, root: Path, bundles: dict[str, str]) -> list[Path]:
    paths: list[Path] = []
    for file_name, bundle in bundles.items():
        path = root / file_name
        path.write_text(bundle, encoding="utf-8")
        paths.append(path)
    return paths


def _sole_step_target(*, library: Library, pipe_key: str) -> str:
    pipe = library.pipe_library.get_required_pipe(pipe_code=pipe_key)
    assert isinstance(pipe, PipeSequence)
    assert len(pipe.sequential_sub_pipes) == 1
    return pipe.sequential_sub_pipes[0].pipe_code


def _refusal_types(exc: LibraryLoadingError) -> list[PipeValidationErrorType | None]:
    return [item.error_type for item in exc.pipe_concept_validation_errors or []]


class TestDependencyPipeScope:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_dependency_runs_its_own_helper_not_the_consumer_s(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The consumer declares `probe_dep.helper` too: the dependency's entry still reaches its own helper."""
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path)
        consumer_files = _write_consumer(
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

            step_target = _sole_step_target(library=library, pipe_key=f"{PROBE_ALIAS}->probe_dep.entry")
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
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path)
        consumer_files = _write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
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
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        for name in TwoPackagesSharingADomainTestData.PACKAGES:
            _install_package(
                root=tmp_path,
                method_name=name,
                manifest=TwoPackagesSharingADomainTestData.manifest(name=name),
                bundles={"shared.mthds": TwoPackagesSharingADomainTestData.bundle(name=name)},
            )
        consumer_files = _write_consumer(root=tmp_path, bundles={"consumer.mthds": TwoPackagesSharingADomainTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)

            reached: dict[str, str] = {}
            for name, alias in TwoPackagesSharingADomainTestData.PACKAGES.items():
                step_target = _sole_step_target(library=library, pipe_key=f"{alias}->shared.entry")
                reached[name] = library.pipe_library.get_required_pipe(pipe_code=step_target).description
        finally:
            library_manager.teardown(library_id=library_id)

        assert reached == {"left": "LEFT helper", "right": "RIGHT helper"}

    def test_a_missing_pipe_of_a_loaded_dependency_is_refused(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A typo in a reference to a loaded package is reported as what it is, not as an extraneous input."""
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path)
        missing_ref = f"{PROBE_ALIAS}->probe_dep.nope"
        consumer_files = _write_consumer(
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
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path)
        consumer_files = _write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
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


class TestDependencyPrivatePipes:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_exported_controller_runs_its_private_helper(self, tmp_path: Path, mocker: MockerFixture) -> None:
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = _write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
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
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        private_ref = f"{PROBE_ALIAS}->probe_dep.helper"
        consumer_files = _write_consumer(
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
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = _write_consumer(
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

        assert _refusal_types(exc_info.value) == [PipeValidationErrorType.UNEXPORTED_PIPE_DEPENDENCY]
        assert "does not export" in str(exc_info.value)

    def test_a_private_pipe_nothing_public_reaches_is_not_loaded(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`orphan` names a model no deck defines: it is never built, so it cannot refuse the consumer's load."""
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = _write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
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
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_package(
            root=tmp_path,
            method_name=TwoDomainPackageTestData.METHOD_NAME,
            manifest=TwoDomainPackageTestData.MANIFEST,
            bundles={"dom_a.mthds": TwoDomainPackageTestData.BUNDLE_A, "dom_b.mthds": TwoDomainPackageTestData.BUNDLE_B},
        )
        private_ref = f"{TwoDomainPackageTestData.DEP_ALIAS}->dom_b.x"
        consumer_files = _write_consumer(
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

        assert _refusal_types(exc_info.value) == [PipeValidationErrorType.UNEXPORTED_PIPE_DEPENDENCY]

    def test_the_entry_door_reaches_a_private_helper_by_hand(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """`[exports]` governs references from inside a method, not a pipe a person names at a CLI argument or an API field."""
        _isolate_installed_methods(mocker=mocker, root=tmp_path)
        _install_probe(root=tmp_path, manifest=ProbePackageTestData.MANIFEST_EXPORTING_ONLY_THE_ENTRY)
        consumer_files = _write_consumer(root=tmp_path, bundles={"consumer.mthds": ProbePackageTestData.CONSUMER_BUNDLE})
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        try:
            library_manager.load_libraries(library_id=library_id, library_file_paths=consumer_files)
            helper = library.pipe_library.get_required_entry_pipe(pipe_code=f"{PROBE_ALIAS}->probe_dep.helper")
        finally:
            library_manager.teardown(library_id=library_id)

        assert helper.description == "DEPENDENCY helper"
