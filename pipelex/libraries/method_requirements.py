"""Checking a method's `requirements.txt` against the Python environment its PipeFunc steps run in, when the method loads.

The MTHDS standard (`mthds/docs/spec/method-tree.md`, "Python Dependencies: `requirements.txt`") lets a method declare
the Python packages its own Python needs in a `requirements.txt` at the root of its method tree, whose lines are read
as `pipelex/core/method_trees/requirements_file.py` reads them: a line the standard refuses is named with why.

Pipelex refuses a method whose requirements are not met when it loads, naming each package it cannot satisfy, and
never installs anything:

- A tree is checked when it holds `requirements.txt` at its root and holds Python, a `.py` file anywhere in it: a tree
  with no Python has nothing that could import a package. The check runs before any of the tree's Python is imported
  or captured, and before any of its pipes is built.
- The environment is the one the PipeFunc steps run in (`pipelex/libraries/package_environments.py`): this interpreter
  in the `direct` execution mode, and in a sandbox-hosted mode the packages the deployment states its sandbox offers
  for the tree's requirements, asked for each tree, so trees judged together each get the offer stated for their own.
  A deployment that cannot hold a tree's requirements in any environment refuses them with its own reason, which the
  method's refusal carries.
- A requirement whose marker is false in that environment is not needed there and is not checked. One is met when the
  environment holds a distribution of its name at a version its specifier contains, pre-releases included, and, for
  each extra it names, when what the extra needs is met in turn.

A refusal names the file by its path in the method's tree, and names paths on this host, the method's root and this
interpreter, only where it may: a check inside a load does, since its refusal is either the caller's own disk's or,
around a host's own library directories, the host's fault, which `reporting_host_library_tree_faults` withholds from
the caller. A dependency package is named by its address, and a server checking a caller's method it holds in a
directory of its own names no path on the host at all (`ensure_served_method_requirements_met`).
"""

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.models import MethodTree, TreeLimits
from packaging.markers import Marker, UndefinedComparison, UndefinedEnvironmentName
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.method_trees.requirements_file import (
    REQUIREMENTS_FILE_NAME,
    RefusedRequirementsLine,
    RequirementLine,
    parse_requirements_text,
)
from pipelex.libraries.exceptions import MethodRequirementsFileError, MethodRequirementsNotMetError
from pipelex.libraries.method_trees import list_library_dir_trees, listing_identity, reporting_host_library_tree_faults
from pipelex.libraries.package_environments import PythonPackageEnvironment, resolve_pipe_func_package_environment
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageRefusal

PYTHON_SUFFIX = ".py"

# The variables a PEP 508 marker can read. `extra` is not the environment's to state: a line of a requirements file
# names no extra of its own, so it reads as empty, as pip reads it.
_MARKER_VARIABLES = frozenset(
    {
        "implementation_name",
        "implementation_version",
        "os_name",
        "platform_machine",
        "platform_python_implementation",
        "platform_release",
        "platform_system",
        "platform_version",
        "python_full_version",
        "python_version",
        "sys_platform",
        "extras",
        "dependency_groups",
    }
)
_QUOTED_MARKER_VALUE = re.compile(r"\"[^\"]*\"|'[^']*'")
_MARKER_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class UnmetRequirement(NamedTuple):
    """A requirement the environment does not meet, with why."""

    requirement_line: RequirementLine
    reason: str


def marker_variables_of(*, marker: Marker) -> set[str]:
    """The PEP 508 variables a marker reads, its quoted values set aside so a value spelled like a variable is never one."""
    unquoted = _QUOTED_MARKER_VALUE.sub(" ", str(marker))
    return {word for word in _MARKER_WORD.findall(unquoted) if word in _MARKER_VARIABLES or word == "extra"}


def _evaluate_marker(*, marker: Marker, environment: PythonPackageEnvironment, extra: str) -> bool:
    """A marker's value in the environment, reading `extra` as given.

    Raises:
        UndefinedComparison: The marker compares values that are not versions.
        UndefinedEnvironmentName: The marker reads a variable the evaluation does not define.
        InvalidVersion: The marker compares, as versions, a value that is not one; releases of `packaging` before 22
            raise it where later ones compare the values as strings.
    """
    return marker.evaluate(environment={**environment.marker_environment, "extra": extra})


def _unmet_reason(
    *,
    requirement: Requirement,
    environment: PythonPackageEnvironment,
    followed_extras: set[tuple[str, str]],
) -> str | None:
    """Why the environment does not meet a requirement whose marker it already judged true, or None when it does."""
    installed_version = environment.version_of(distribution_name=requirement.name)
    if installed_version is None:
        return f"{requirement.name} is missing"
    try:
        version = Version(installed_version)
    except InvalidVersion:
        return f"{requirement.name} {installed_version} is there, a version no specifier can be compared with"
    if not requirement.specifier.contains(version, prereleases=True):
        return f"{requirement.name} {installed_version} is there"
    for extra in sorted(requirement.extras):
        extra_reason = _unmet_extra_reason(distribution_name=requirement.name, extra=extra, environment=environment, followed_extras=followed_extras)
        if extra_reason is not None:
            return extra_reason
    return None


def _unmet_extra_reason(
    *,
    distribution_name: str,
    extra: str,
    environment: PythonPackageEnvironment,
    followed_extras: set[tuple[str, str]],
) -> str | None:
    """Why the environment does not meet what an extra of a distribution it holds needs, or None when it does.

    An extra needs each requirement of the distribution's metadata whose marker holds with the extra and not without
    it. Each extra is followed once, so extras that name one another end.
    """
    key = (canonicalize_name(distribution_name), canonicalize_name(extra))
    if key in followed_extras:
        return None
    followed_extras.add(key)
    dependencies = environment.dependencies_of(distribution_name=distribution_name)
    if dependencies is None:
        return (
            f"{environment.description} does not state what the extra '{extra}' of {distribution_name} needs; "
            "list the packages it needs in requirements.txt instead"
        )
    for dependency_text in dependencies:
        try:
            dependency = Requirement(dependency_text)
        except InvalidRequirement:
            # Metadata of an installed distribution that no installer could have read either; it needs nothing here.
            continue
        if dependency.marker is None:
            continue
        try:
            needed_by_extra = _evaluate_marker(marker=dependency.marker, environment=environment, extra=extra)
            needed_anyway = _evaluate_marker(marker=dependency.marker, environment=environment, extra="")
        except (UndefinedComparison, UndefinedEnvironmentName, InvalidVersion):
            continue
        if not needed_by_extra or needed_anyway:
            continue
        dependency_reason = _unmet_reason(requirement=dependency, environment=environment, followed_extras=followed_extras)
        if dependency_reason is not None:
            return f"the extra '{extra}' of {distribution_name} needs '{dependency_text}', and {dependency_reason}"
    return None


def unmet_requirements(*, requirements: Iterable[RequirementLine], environment: PythonPackageEnvironment) -> list[UnmetRequirement]:
    """The requirements the environment does not meet, in the order given, each with why."""
    unmet: list[UnmetRequirement] = []
    for requirement_line in requirements:
        reason = _requirement_line_unmet_reason(requirement_line=requirement_line, environment=environment)
        if reason is not None:
            unmet.append(UnmetRequirement(requirement_line=requirement_line, reason=reason))
    return unmet


def _requirement_line_unmet_reason(*, requirement_line: RequirementLine, environment: PythonPackageEnvironment) -> str | None:
    marker = requirement_line.requirement.marker
    if marker is not None:
        unstated = sorted(marker_variables_of(marker=marker) - set(environment.marker_environment) - {"extra"})
        if unstated:
            return f"its marker reads {', '.join(unstated)}, which {environment.description} does not state"
        try:
            if not _evaluate_marker(marker=marker, environment=environment, extra=""):
                return None
        except (UndefinedComparison, UndefinedEnvironmentName, InvalidVersion) as exc:
            return f"its marker cannot be evaluated: {exc}"
    return _unmet_reason(requirement=requirement_line.requirement, environment=environment, followed_extras=set())


def holds_requirements_to_check(*, tree: MethodTree) -> bool:
    """Whether a tree's requirements are checked when it loads: it lies on disk, declares them at its root, and holds Python."""
    if tree.directory is None or REQUIREMENTS_FILE_NAME not in tree.members:
        return False
    return any(tree_path.endswith(PYTHON_SUFFIX) for tree_path in tree.tree_paths)


class JudgedMethod(NamedTuple):
    """A method tree whose requirements are judged, with how a refusal names it and its file."""

    tree: MethodTree
    method_name: str
    requirements_source: str


def _judged_method(*, tree: MethodTree, names_host_paths: bool) -> JudgedMethod:
    """A tree as a refusal names it: by its root on this host when it may name host paths, and as "The method" otherwise.

    The file is named by its path in the tree either way, never by its path on the host.
    """
    method_name = f"The method rooted at '{tree.directory}'" if names_host_paths and tree.directory is not None else "The method"
    return JudgedMethod(tree=tree, method_name=method_name, requirements_source=REQUIREMENTS_FILE_NAME)


def _read_requirements_text(*, judged: JudgedMethod) -> str:
    """The text of a tree's `requirements.txt`.

    Raises:
        MethodRequirementsFileError: The file cannot be read, or is not UTF-8 text.
    """
    location = judged.tree.file_location(REQUIREMENTS_FILE_NAME)
    source = judged.requirements_source
    try:
        return location.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{judged.method_name} declares its packages in a {REQUIREMENTS_FILE_NAME} that is not UTF-8 text, so they cannot be read."
        raise MethodRequirementsFileError(msg, items=[PipelexBundleBlueprintValidationErrorData(source=source, message=msg)]) from exc
    except OSError as exc:
        msg = f"{judged.method_name} declares its packages in a {REQUIREMENTS_FILE_NAME} that cannot be read: {exc.strerror or type(exc).__name__}."
        raise MethodRequirementsFileError(msg, items=[PipelexBundleBlueprintValidationErrorData(source=source, message=msg)]) from exc


def _raise_refused_lines(*, judged: JudgedMethod, refused_lines: list[RefusedRequirementsLine]) -> None:
    """Refuse the file for its lines the standard refuses, naming each.

    Raises:
        MethodRequirementsFileError: Always.
    """
    items: list[PipelexBundleBlueprintValidationErrorData] = []
    line_texts: list[str] = []
    for refused_line in refused_lines:
        line_text = f"line {refused_line.line_number} '{refused_line.text}': {refused_line.reason}"
        line_texts.append(line_text)
        items.append(
            PipelexBundleBlueprintValidationErrorData(
                source=judged.requirements_source,
                line=refused_line.line_number,
                message=f"{REQUIREMENTS_FILE_NAME} {line_text}.",
            )
        )
    msg = (
        f"{judged.method_name} declares its packages in a {REQUIREMENTS_FILE_NAME} holding lines the MTHDS standard "
        f"refuses, where each line is blank, a comment, or exactly one PEP 508 requirement: {'; '.join(line_texts)}."
    )
    raise MethodRequirementsFileError(msg, items=items)


def _raise_unmet(*, judged: JudgedMethod, unmet: list[UnmetRequirement], environment: PythonPackageEnvironment) -> None:
    """Refuse the method for the requirements the environment does not meet, naming each and what its author can do.

    Raises:
        MethodRequirementsNotMetError: Always.
    """
    items: list[PipelexBundleBlueprintValidationErrorData] = []
    line_texts: list[str] = []
    for unmet_requirement in unmet:
        requirement_line = unmet_requirement.requirement_line
        line_text = f"line {requirement_line.line_number} '{requirement_line.text}' ({unmet_requirement.reason})"
        line_texts.append(line_text)
        items.append(
            PipelexBundleBlueprintValidationErrorData(
                source=judged.requirements_source,
                line=requirement_line.line_number,
                message=f"The requirement '{requirement_line.text}' is not met by {environment.description}: {unmet_requirement.reason}.",
            )
        )
    advice = environment.advice(requirement_texts=[unmet_requirement.requirement_line.text for unmet_requirement in unmet])
    msg = (
        f"{judged.method_name} needs Python packages that {environment.description} "
        f"does not have, as its {REQUIREMENTS_FILE_NAME} declares: {'; '.join(line_texts)}. {advice}"
    )
    raise MethodRequirementsNotMetError(msg, items=items)


def _refused_by_deployment_error(*, judged: JudgedMethod, refusal: PipeFuncPackageRefusal) -> MethodRequirementsNotMetError:
    """The refusal of a method whose requirements the deployment cannot hold in any environment, carrying its reason.

    The deployment's reason is about the requirements together, such as a conflict its resolver found among them, so the
    one item it rides on names the file and no line.
    """
    msg = (
        f"{judged.method_name} needs Python packages that {refusal.environment} cannot offer, "
        f"as its {REQUIREMENTS_FILE_NAME} declares: {refusal.reason}"
    )
    item = PipelexBundleBlueprintValidationErrorData(
        source=judged.requirements_source,
        message=f"The requirements are refused by {refusal.environment}: {refusal.reason}",
    )
    return MethodRequirementsNotMetError(msg, items=[item])


def _ensure_judged_methods_met(*, judged_methods: Iterable[JudgedMethod], names_host_paths: bool) -> None:
    """Refuse the first of the methods whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    Each tree is judged once however often it is given, in the order given, against the environment stated for its own
    requirements: in a sandbox-hosted mode, the plugin providing the mode is asked for each tree declaring requirements,
    so trees judged together never share an environment stated for another's. Methods declaring none never read it.

    Raises:
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or cannot be read.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements, or the deployment refuses
            them with its own reason, no environment of its holding them.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    judged_trees: set[tuple[str, str, bool]] = set()
    for judged in judged_methods:
        tree_identity = listing_identity(tree=judged.tree)
        if tree_identity in judged_trees:
            continue
        judged_trees.add(tree_identity)
        if not holds_requirements_to_check(tree=judged.tree):
            continue
        parsed = parse_requirements_text(text=_read_requirements_text(judged=judged))
        if parsed.refused_lines:
            _raise_refused_lines(judged=judged, refused_lines=parsed.refused_lines)
        if not parsed.requirements:
            continue
        environment = resolve_pipe_func_package_environment(requirements=parsed.requirements, names_host_paths=names_host_paths)
        if isinstance(environment, PipeFuncPackageRefusal):
            raise _refused_by_deployment_error(judged=judged, refusal=environment)
        unmet = unmet_requirements(requirements=parsed.requirements, environment=environment)
        if unmet:
            _raise_unmet(judged=judged, unmet=unmet, environment=environment)


def ensure_method_requirements_met(*, trees: Iterable[MethodTree], names_host_paths: bool) -> None:
    """Refuse a method among the trees whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    Each tree is judged once however often it is given, in the order given, and the first refused ends the check.

    Args:
        trees: The method trees a load reads, each checked when it lies on disk, declares requirements and holds Python.
        names_host_paths: Whether a refusal may name the method's root and this interpreter by their paths on this host,
            as a load's may: its refusal is the caller's own disk's, or the host's fault, withheld from the caller.

    Raises:
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or cannot be read.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements, or the deployment refuses
            them with its own reason.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    _ensure_judged_methods_met(
        judged_methods=(_judged_method(tree=tree, names_host_paths=names_host_paths) for tree in trees),
        names_host_paths=names_host_paths,
    )


def ensure_package_requirements_met(*, tree: MethodTree, package_address: str) -> None:
    """Refuse a dependency package whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    The package is named by its address and its file by `<address>/requirements.txt`, never by the directory it was
    installed or fetched into, as its bundles are, since the package is the caller's dependency wherever it loads.

    Raises:
        MethodRequirementsFileError: The package's `requirements.txt` holds a line the standard refuses, or cannot be read.
        MethodRequirementsNotMetError: The environment does not meet the package's requirements, or the deployment
            refuses them with its own reason.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    judged = JudgedMethod(
        tree=tree,
        method_name=f"The method package '{package_address}'",
        requirements_source=f"{package_address}/{REQUIREMENTS_FILE_NAME}",
    )
    _ensure_judged_methods_met(judged_methods=[judged], names_host_paths=False)


def ensure_served_method_requirements_met(*, library_dirs: Sequence[Path], limits: TreeLimits | None = None) -> None:
    """Check the requirements of a caller's method a server holds in directories of its own, as loading them would, without loading them.

    For a server that hands the directories to a loader elsewhere, such as a validator on a worker that never reads
    them, or that loads them as its own library directories, so the refusal is the caller's and comes from the place
    that knows the method's files. The directories are the server's: a tree of them that cannot be listed is the
    host's fault, as a load of a host's library directories reports it, and a refusal names no path on the host, the
    directories' and this interpreter's included.

    Raises:
        HostLibraryTreeError: A tree of the directories could not be listed.
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or cannot be read.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements, or the deployment refuses
            them with its own reason.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    with reporting_host_library_tree_faults():
        library_trees = list_library_dir_trees(library_dirs=library_dirs, limits=limits)
    ensure_method_requirements_met(trees=[library_tree.tree for library_tree in library_trees], names_host_paths=False)
