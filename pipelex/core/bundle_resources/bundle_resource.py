"""The files submitted with bundles loaded from content strings: the path each is keyed by, and the rule that path follows.

A bundle loaded from a directory finds the files its steps name in its method tree. A bundle submitted as content
strings, which is how the runner's routes receive one, has no directory, so the files come with it, each keyed by the
bundle-relative path a step names, read as if every bundle of the submission sat in one directory. The library places
those bundles at the root of the tree these files make (`LibraryManager`), so a step resolves a file it names there, as
it would in a folder, and the run's crate names that tree by its digest like any other: no file's bytes travel with it.
"""

from collections.abc import Mapping
from pathlib import PurePosixPath

from pipelex.core.bundle_resources.exceptions import BundleResourcePathError


def resource_path_refusal(*, path: str) -> str | None:
    """Why `path` cannot name a file inside a bundle, or None when it can.

    The one rule for a bundle-relative path, held by the key of a file submitted with a bundle and by the path a step
    names, such as a `PipeDocGen` step's `template_file`, so any file a step names can be submitted with its bundle.
    The reason never repeats the path, which a host library's step would otherwise put in front of a caller.
    """
    if not path.strip():
        return "it is empty"
    if "\\" in path:
        return "it holds a backslash; write the path with forward slashes"
    if ":" in path:
        return "it holds a colon"
    if "\x00" in path:
        return "it holds a NUL character"
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute():
        return "it is absolute; write it relative to the bundle"
    if ".." in pure_path.parts:
        return "it leaves the bundle through a '..' segment"
    if not pure_path.parts:
        return "it names no file"
    return None


def canonical_resource_path_or_none(*, path: str) -> str | None:
    """The one spelling of a bundle-relative path, or None when it cannot name a file inside the bundle.

    `.` segments and repeated slashes collapse, so `./invoice.xlsx` and `invoice.xlsx` name one file.
    """
    if resource_path_refusal(path=path) is not None:
        return None
    return PurePosixPath(path).as_posix()


def canonical_resource_path(*, path: str) -> str:
    """The one spelling of a bundle-relative path, the key a submitted file is held and looked up under.

    POSIX separators only, relative, and inside the bundle: an absolute path, a `..` segment, a backslash, a colon
    and an empty path are refused. `.` segments and repeated slashes collapse, so `./invoice.xlsx` and
    `invoice.xlsx` name one file.

    Raises:
        BundleResourcePathError: the path cannot name a file inside the bundle.
    """
    refusal = resource_path_refusal(path=path)
    if refusal is not None:
        msg = f"The file '{path}' submitted with the bundle cannot be one of its files: {refusal}."
        raise BundleResourcePathError(msg)
    return PurePosixPath(path).as_posix()


def canonical_submitted_files(*, files: Mapping[str, bytes]) -> dict[str, bytes]:
    """The files submitted with bundles, keyed by their canonical bundle-relative path.

    Raises:
        BundleResourcePathError: a path cannot name a file inside the bundle, or two paths name the same file.
    """
    canonical_files: dict[str, bytes] = {}
    for path, content in files.items():
        canonical_path = canonical_resource_path(path=path)
        if canonical_path in canonical_files:
            msg = f"Two files submitted with the bundle name the same file '{canonical_path}'."
            raise BundleResourcePathError(msg)
        canonical_files[canonical_path] = content
    return canonical_files
