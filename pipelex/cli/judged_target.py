"""What `validate bundle` and `fix bundle` judge, on both CLIs, and the one fix loop that fixes it.

Both commands read their `path` argument the same way (`pipelex.cli.bundle_target_resolution`, `FolderReading.WHOLE_TREE`):
a `.mthds` file is judged as a bundle file, a folder as its whole method tree. `fix` must patch exactly what `validate`
judged, so the two CLIs share the target this module defines, the path it names, and the dispatch to the fix loop.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.models import MethodTree

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.cli.bundle_target_resolution import BundleTargetResolutionError, FolderReading, resolve_bundle_target_core
from pipelex.pipeline.fixes.fix_loop import FixBundleResult, fix_bundle_file, fix_method_folder


class JudgedBundleTarget(NamedTuple):
    """What `validate` and `fix` judge: one bundle file, or a method's whole folder, and the library loaded with it."""

    #: The file named, or None for a folder.
    bundle_path: Path | None
    #: The folder named, `~` expanded, judged as its whole method tree, or None for a file.
    method_dir: Path | None
    #: The folder's method tree, or None for a file.
    method_tree: MethodTree | None
    #: The folder, then the `-L` directories, `~` expanded; None for a file named with no `-L`.
    library_dirs: list[Path] | None

    @property
    def judged_path(self) -> Path:
        """The path the verdict names: the method's folder, as the caller gave it, or the bundle file.

        Raises:
            PipelexUnexpectedError: The target names neither, which no resolution produces.
        """
        if self.method_dir is not None:
            return self.method_dir
        if self.bundle_path is not None:
            return self.bundle_path
        msg = "A bundle target was resolved to neither a bundle file nor a method's folder."
        raise PipelexUnexpectedError(msg)


def resolve_judged_target(*, path: str, library_dir: list[str] | None) -> JudgedBundleTarget | BundleTargetResolutionError:
    """Resolve the `path` argument of `validate bundle` or `fix bundle` into what the command judges.

    Args:
        path: The `path` argument, a `.mthds` file or a method's folder, `~` expanded.
        library_dir: The `-L/--library-dir` values as passed, `~` expanded.

    Raises:
        EmptyMethodTreeError: The folder holds no bundle.
        ValidateBundleError: The folder's tree is refused or past this machine's limits, the invalid verdict.
        PipelexConfigError: This machine's configuration, read for the tree's limits, does not validate.
    """
    result = resolve_bundle_target_core(path, library_dir=library_dir, reading=FolderReading.WHOLE_TREE)
    if isinstance(result, BundleTargetResolutionError):
        return result
    return JudgedBundleTarget(
        bundle_path=result.bundle_path,
        method_dir=result.method_dir,
        method_tree=result.method_tree,
        library_dirs=result.library_dirs,
    )


async def fix_judged_target(
    *,
    target: JudgedBundleTarget,
    writable_library_dirs: Sequence[Path] | None,
    allow_signatures: bool,
    max_iterations: int | None,
    select_codes: Sequence[str] | None,
    ignore_codes: Sequence[str] | None,
) -> FixBundleResult:
    """Run the fix loop on what `validate` judged: a method's folder, judged whole, else a bundle file.

    Args:
        target: The resolved target, or its copy in the `--diff` preview's sandbox.
        writable_library_dirs: The directories the loop may write, as the preview's sandbox gives them, or None for
            the scope a real run derives from the target.
        allow_signatures: Whether `PipeSignature` placeholders pass the exit gate.
        max_iterations: The apply-round cap, or None for the configured one.
        select_codes: The only fix rules to apply, or None for every rule.
        ignore_codes: The fix rules to skip, or None.

    Raises:
        PipelexUnexpectedError: The target names neither a folder nor a file.
    """
    if target.method_dir is not None:
        return await fix_method_folder(
            method_dir=target.method_dir,
            library_dirs=target.library_dirs,
            writable_library_dirs=writable_library_dirs,
            allow_signatures=allow_signatures,
            max_iterations=max_iterations,
            select_codes=select_codes,
            ignore_codes=ignore_codes,
        )
    return await fix_bundle_file(
        target.judged_path,
        library_dirs=target.library_dirs,
        writable_library_dirs=writable_library_dirs,
        allow_signatures=allow_signatures,
        max_iterations=max_iterations,
        select_codes=select_codes,
        ignore_codes=ignore_codes,
    )
