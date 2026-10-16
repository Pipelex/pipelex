from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from pipelex import log
from pipelex.config import get_config
from pipelex.libraries.method_trees import list_library_bundle_files
from pipelex.mthds_parsing.helpers import is_pipelex_file
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.error_fields import error_fields


def get_pipelex_mthds_files_from_package() -> list[Path]:
    """Get all MTHDS files from the pipelex package using importlib.resources.

    This works reliably whether pipelex is installed as a wheel, from source,
    or as a relative path import.

    Returns:
        List of Path objects to MTHDS files in pipelex package
    """
    mthds_files: list[Path] = []
    pipelex_package = files("pipelex")

    def _find_mthds_in_traversable(traversable: Traversable, *, collected: list[Path]) -> None:
        """Recursively find .mthds files in a Traversable."""
        excluded_dirs = get_config().interpreter.scan.excluded_dirs
        try:
            if not traversable.is_dir():
                return

            for child in sorted(traversable.iterdir(), key=lambda entry: entry.name):
                if child.is_file() and is_pipelex_file(Path(child.name)):
                    collected.append(Path(str(child)))
                elif child.is_dir():
                    # Skip excluded directories
                    if child.name not in excluded_dirs:
                        _find_mthds_in_traversable(child, collected=collected)
        except (PermissionError, OSError) as exc:
            log.warning(
                "A directory of the pipelex package could not be read and was left out",
                fields={OTelLogAttr.FILE_PATH: str(traversable), **error_fields(exc=exc)},
            )

    _find_mthds_in_traversable(pipelex_package, collected=mthds_files)
    log.verbose(f"Found {len(mthds_files)} MTHDS files in pipelex package")
    return mthds_files


def get_pipelex_package_dir_for_imports() -> Path | None:
    """Get the pipelex package directory as a Path for importing Python modules.

    Returns:
        Path to the pipelex package directory, or None if not accessible as filesystem
    """
    pipelex_package = files("pipelex")
    try:
        # Try to convert to Path (works for filesystem paths)
        pkg_path = Path(str(pipelex_package))
        if pkg_path.exists() and pkg_path.is_dir():
            return pkg_path
    except (TypeError, ValueError, OSError) as exc:
        log.warning("The pipelex package is not a directory, and its modules were not imported", fields=error_fields(exc=exc))
    return None


def get_pipelex_mthds_files_from_dirs(dirs: set[Path]) -> list[Path]:
    """The bundle files a load of these library directories reads, each spelled from its directory as given.

    The files are the `.mthds` members of each directory's method tree and of the trees nested in it
    (`pipelex.libraries.method_trees`), so a file the membership rule keeps out, such as one in a run's output folder,
    is never listed. A directory that does not exist holds none.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    return [bundle_file.path for bundle_file in list_library_bundle_files(library_dirs=sorted(dirs))]
