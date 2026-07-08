"""Shared bundle target resolution for human and agent CLI wrappers."""

from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


class BundleTargetResolutionErrorKind(StrEnum):
    """Failure kinds for resolving a CLI bundle target."""

    NO_MTHDS_FILE = "no_mthds_file"
    AMBIGUOUS_MTHDS_FILES = "ambiguous_mthds_files"
    NOT_BUNDLE_TARGET = "not_bundle_target"


class BundleTargetResolutionSuccess(NamedTuple):
    """Successful bundle target resolution."""

    bundle_path: Path
    library_dirs: list[Path] | None
    auto_detected: bool


class BundleTargetResolutionError(NamedTuple):
    """Typed resolution failure for CLI-specific rendering."""

    kind: BundleTargetResolutionErrorKind
    input_path: str
    target_path: Path
    candidate_files: list[Path]


def resolve_bundle_target_core(
    path: str,
    *,
    library_dir: list[str] | None,
) -> BundleTargetResolutionSuccess | BundleTargetResolutionError:
    """Resolve a CLI path argument without deciding how errors are rendered."""
    library_dirs = [Path(library_dir_item).expanduser() for library_dir_item in library_dir] if library_dir else None
    target_path = Path(path).expanduser()

    if target_path.is_dir():
        default_bundle_path = target_path / DEFAULT_BUNDLE_FILE_NAME
        if default_bundle_path.is_file():
            bundle_path = default_bundle_path
        else:
            mthds_files = sorted(target_path.glob(f"*{MTHDS_EXTENSION}"), key=lambda file_path: file_path.name)
            if len(mthds_files) == 0:
                return BundleTargetResolutionError(
                    kind=BundleTargetResolutionErrorKind.NO_MTHDS_FILE,
                    input_path=path,
                    target_path=target_path,
                    candidate_files=[],
                )
            if len(mthds_files) > 1:
                return BundleTargetResolutionError(
                    kind=BundleTargetResolutionErrorKind.AMBIGUOUS_MTHDS_FILES,
                    input_path=path,
                    target_path=target_path,
                    candidate_files=mthds_files,
                )
            bundle_path = mthds_files[0]

        if library_dirs is None:
            library_dirs = [target_path]
        elif target_path not in library_dirs:
            library_dirs = [target_path, *library_dirs]

        return BundleTargetResolutionSuccess(
            bundle_path=bundle_path,
            library_dirs=library_dirs,
            auto_detected=True,
        )

    if is_pipelex_file(target_path):
        return BundleTargetResolutionSuccess(
            bundle_path=target_path,
            library_dirs=library_dirs,
            auto_detected=False,
        )

    return BundleTargetResolutionError(
        kind=BundleTargetResolutionErrorKind.NOT_BUNDLE_TARGET,
        input_path=path,
        target_path=target_path,
        candidate_files=[],
    )
