"""The files submitted with bundles loaded from content strings: the path each is keyed by, and the rule that path follows.

A bundle loaded from a directory finds the files its steps name in its method tree. A bundle submitted as content
strings, which is how the runner's routes receive one, has no directory, so the files come with it, each keyed by the
bundle-relative path a step names, read as if every bundle of the submission sat in one directory. The library places
those bundles at the root of the tree these files make (`LibraryManager`), so a step resolves a file it names there, as
it would in a folder, and the run's crate names that tree by its digest like any other: no file's bytes travel with it.
"""

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath

from mthds.protocol.problem.registry import CoreCode, SecurityInputPathRefusedRule

from pipelex.core.bundle_resources.exceptions import BundleResourcePathError

# The field of a run request the files submitted with its bundles ride, which a refusal of one of their paths names.
SUBMITTED_FILES_FIELD = "resources"


def root_escape_refusal(*, path: str) -> str | None:
    r"""Why `path`, written relative to a root, would reach outside that root, or None when it stays below it.

    The one rule telling a path that tries to leave its root, a security refusal (``security.input_path_refused`` for a
    caller's path), from a path of the wrong shape, a refusal of the request: it is held by the key of a file submitted
    with a bundle, by a file submitted beside a method, and by a key of a method tree a request carries, which the
    standard's reader refuses without saying why. The path is read with either separator, as a system that follows a
    backslash would read it: it leaves its root when it is absolute or rooted (`/etc/passwd`, `\etc`), when it names a
    drive or a network share (`C:/Windows`, `C:secrets`, `\\server\share`), or when one of its segments is `..`. Any
    other path that is refused, empty, holding a backslash, a colon or a NUL character, is of the wrong shape. The
    reason never repeats the path.
    """
    windows_path = PureWindowsPath(path)
    if windows_path.drive:
        return "it names a drive or a network share; write it relative to the bundle"
    if windows_path.root:
        return "it is absolute; write it relative to the bundle"
    if ".." in windows_path.parts:
        return "it leaves the bundle through a '..' segment"
    return None


def root_escape_rule(*, path: str) -> SecurityInputPathRefusedRule | None:
    """The rule of ``security.input_path_refused`` that `path` breaks by leaving its root, or None when it stays below it.

    The same reading as `root_escape_refusal`, as the registry's rule: a path naming a drive or a network share, and a
    rooted path, are `absolute`, and a path climbing with a `..` segment is `parent_segment`.
    """
    windows_path = PureWindowsPath(path)
    if windows_path.drive or windows_path.root:
        return SecurityInputPathRefusedRule.ABSOLUTE
    if ".." in windows_path.parts:
        return SecurityInputPathRefusedRule.PARENT_SEGMENT
    return None


def resource_path_refusal(*, path: str) -> str | None:
    """Why `path` cannot name a file inside a bundle, or None when it can.

    The one rule for a bundle-relative path, held by the key of a file submitted with a bundle and by the path a step
    names, such as a `PipeDocGen` step's `template_file`, so any file a step names can be submitted with its bundle.
    A path that leaves the bundle says so first (`root_escape_refusal`). The reason never repeats the path, which a host
    library's step would otherwise put in front of a caller.
    """
    if not path.strip():
        return "it is empty"
    escape = root_escape_refusal(path=path)
    if escape is not None:
        return escape
    if "\\" in path:
        return "it holds a backslash; write the path with forward slashes"
    if ":" in path:
        return "it holds a colon"
    if "\x00" in path:
        return "it holds a NUL character"
    if not PurePosixPath(path).parts:
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

    POSIX separators only, relative, and inside the bundle: an absolute path, a drive, a `..` segment, a backslash, a
    colon and an empty path are refused. `.` segments and repeated slashes collapse, so `./invoice.xlsx` and
    `invoice.xlsx` name one file.

    Raises:
        BundleResourcePathError: the path cannot name a file inside the bundle: ``security.input_path_refused`` for a
            path that leaves it (`root_escape_refusal`), ``request.invalid`` for a path of the wrong shape.
    """
    refusal = resource_path_refusal(path=path)
    if refusal is not None:
        msg = f"The file '{path}' submitted with the bundle cannot be one of its files: {refusal}."
        raise BundleResourcePathError(msg).with_error_code(path_refusal_code(path=path)).with_params(**path_refusal_params(path=path))
    return PurePosixPath(path).as_posix()


def path_refusal_code(*, path: str) -> CoreCode:
    """The code of the refusal of a caller's path: a security refusal when it leaves its root, else a refusal of the request."""
    if root_escape_rule(path=path) is not None:
        return CoreCode.SECURITY_INPUT_PATH_REFUSED
    return CoreCode.REQUEST_INVALID


def path_refusal_params(*, path: str) -> dict[str, str]:
    """The parameters of the refusal `path_refusal_code` names for a submitted file's path.

    The rule a path leaving its root breaks, for ``security.input_path_refused``, else the request's field the submitted
    files ride, `resources`, for ``request.invalid``.
    """
    rule = root_escape_rule(path=path)
    if rule is not None:
        return {"rule": rule}
    return {"field": SUBMITTED_FILES_FIELD}


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
            raise BundleResourcePathError(msg).with_error_code(CoreCode.REQUEST_INVALID).with_params(field=SUBMITTED_FILES_FIELD)
        canonical_files[canonical_path] = content
    return canonical_files
