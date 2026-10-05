"""Helpers that install invented method packages under a temporary `.mthds/methods/` and write a consumer beside them."""

from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.library import Library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.libraries.test_data import ProbePackageTestData


def isolate_installed_methods(*, mocker: MockerFixture, root: Path) -> None:
    """Point package discovery at `root` and disable fetch-on-miss, so only the packages a test installs exist."""
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", root / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", root / "project-methods")
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)


def install_package(*, root: Path, method_name: str, manifest: str, bundles: dict[str, str]) -> None:
    package_dir = root / ".mthds" / "methods" / method_name
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(manifest, encoding="utf-8")
    for file_name, bundle in bundles.items():
        (package_dir / file_name).write_text(bundle, encoding="utf-8")


def install_probe(
    *,
    root: Path,
    manifest: str = ProbePackageTestData.MANIFEST_EXPORTING_EVERYTHING,
    bundle: str = ProbePackageTestData.DEP_BUNDLE,
) -> None:
    install_package(root=root, method_name=ProbePackageTestData.METHOD_NAME, manifest=manifest, bundles={"probe_dep.mthds": bundle})


def write_consumer(*, root: Path, bundles: dict[str, str]) -> list[Path]:
    paths: list[Path] = []
    for file_name, bundle in bundles.items():
        path = root / file_name
        path.write_text(bundle, encoding="utf-8")
        paths.append(path)
    return paths


def sole_step_target(*, library: Library, pipe_key: str) -> str:
    """The pipe ref the single step of the sequence held under `pipe_key` names."""
    pipe = library.pipe_library.get_required_pipe(pipe_code=pipe_key)
    assert isinstance(pipe, PipeSequence)
    assert len(pipe.sequential_sub_pipes) == 1
    return pipe.pipe_steps[0].pipe_code


def refusal_types(exc: LibraryLoadingError) -> list[PipeValidationErrorType | None]:
    return [item.error_type for item in exc.pipe_concept_validation_errors or []]
