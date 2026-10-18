"""Checking a method's `requirements.txt` against the Python environment its PipeFunc steps run in, when the method loads.

The MTHDS standard (`mthds/docs/spec/method-tree.md`, "Python Dependencies: `requirements.txt`") lets a method declare
the Python packages its own Python needs in a `requirements.txt` at the root of its method tree: each line is blank, a
comment whose first character other than a space or a tab is `#`, or exactly one PEP 508 requirement, markers
included. A requirement naming a URL, an option of any kind (a line starting with `-`), a comment after a requirement
and a line continued with a backslash are refused, naming the line. Only the root's file declares anything.

Pipelex refuses a method whose requirements are not met when it loads, naming each package it cannot satisfy, and
never installs anything:

- A tree is checked when it holds `requirements.txt` at its root and holds Python, a `.py` file anywhere in it: a tree
  with no Python has nothing that could import a package. The check runs before any of the tree's Python is imported
  or captured, and before any of its pipes is built.
- The environment is the one the PipeFunc steps run in (`pipelex/libraries/package_environments.py`): this interpreter
  in the `direct` execution mode, and in a sandbox-hosted mode the package set the deployment states for its sandbox.
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
from mthds.protocol.problem.registry import MethodDependencyMissingKind, MethodDependencyMissingReason
from packaging.markers import Marker, UndefinedComparison, UndefinedEnvironmentName
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.libraries.exceptions import MethodRequirementsFileError, MethodRequirementsNotMetError
from pipelex.libraries.method_trees import list_library_dir_trees, listing_identity, reporting_host_library_tree_faults
from pipelex.libraries.package_environments import PythonPackageEnvironment, resolve_pipe_func_package_environment
from pipelex.methods.package_reason import MethodPackageReason

REQUIREMENTS_FILE_NAME = "requirements.txt"

# The parameters of `method.package_invalid` for a `requirements.txt` the standard refuses or that cannot be read.
_REQUIREMENTS_INVALID_PARAMS: dict[str, str] = {"reason": MethodPackageReason.REQUIREMENTS_INVALID, "path": REQUIREMENTS_FILE_NAME}

PYTHON_SUFFIX = ".py"

_UTF8_BOM = "\ufeff"

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
# A comment inside a line starts at a `#` that opens the line or follows whitespace, as pip reads one, so the fragment of
# a URL, such as `#sha256=…`, is not one.
_INLINE_COMMENT = re.compile(r"(^|\s+)#.*$")
_MARKER_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class RequirementLine(NamedTuple):
    """A requirement of a `requirements.txt`, with its 1-based line number and its text as written, stripped."""

    line_number: int
    text: str
    requirement: Requirement


class RefusedRequirementsLine(NamedTuple):
    """A line of a `requirements.txt` the standard refuses, with why."""

    line_number: int
    text: str
    reason: str


class ParsedRequirements(NamedTuple):
    """What a `requirements.txt` declares: its requirements, and the lines it holds that the standard refuses."""

    requirements: list[RequirementLine]
    refused_lines: list[RefusedRequirementsLine]


class UnmetRequirement(NamedTuple):
    """A requirement the environment does not meet, with why."""

    requirement_line: RequirementLine
    reason: str


def _refusal_reason(*, stripped: str) -> tuple[Requirement | None, str | None]:
    """The requirement a non-blank, non-comment line declares, or why the standard refuses the line."""
    if stripped.endswith("\\"):
        return None, "a line continued with a backslash is refused; write each requirement on a line of its own"
    if stripped.startswith("-"):
        return None, "an option line, such as -r, -e, -c or --index-url, is refused; write each package as a PEP 508 requirement"
    # The requirement is judged without the comment after it, so a comment that mentions a URL is not read as one.
    remainder = _INLINE_COMMENT.sub("", stripped).rstrip()
    try:
        requirement = Requirement(remainder)
    except InvalidRequirement as exc:
        if "://" in remainder:
            return None, "a requirement naming a URL is refused; name the package and the versions it accepts instead"
        parser_message = str(exc).splitlines()[0] if str(exc) else "it does not parse"
        return None, f"the line is not a PEP 508 requirement: {parser_message}"
    if requirement.url is not None:
        return None, "a requirement naming a URL is refused; name the package and the versions it accepts instead"
    if remainder != stripped:
        return None, "a comment after a requirement is refused; write the comment on a line of its own"
    return requirement, None


def parse_requirements_text(*, text: str) -> ParsedRequirements:
    """Read the lines of a `requirements.txt` as the MTHDS standard does, keeping every refused line rather than the first.

    A leading byte order mark is skipped, and a line may end with a carriage return before its line feed.
    """
    requirements: list[RequirementLine] = []
    refused_lines: list[RefusedRequirementsLine] = []
    text = text.removeprefix(_UTF8_BOM)
    for line_index, raw_line in enumerate(text.split("\n")):
        line_number = line_index + 1
        line = raw_line.removesuffix("\r")
        if not line.strip():
            continue
        if line.lstrip(" \t").startswith("#"):
            continue
        stripped = line.strip()
        requirement, reason = _refusal_reason(stripped=stripped)
        if requirement is not None:
            requirements.append(RequirementLine(line_number=line_number, text=stripped, requirement=requirement))
        elif reason is not None:
            refused_lines.append(RefusedRequirementsLine(line_number=line_number, text=stripped, reason=reason))
    return ParsedRequirements(requirements=requirements, refused_lines=refused_lines)


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
        raise MethodRequirementsFileError(msg, items=[PipelexBundleBlueprintValidationErrorData(source=source, message=msg)]).with_params(
            **_REQUIREMENTS_INVALID_PARAMS
        ) from exc
    except OSError as exc:
        msg = f"{judged.method_name} declares its packages in a {REQUIREMENTS_FILE_NAME} that cannot be read: {exc.strerror or type(exc).__name__}."
        raise MethodRequirementsFileError(msg, items=[PipelexBundleBlueprintValidationErrorData(source=source, message=msg)]).with_params(
            **_REQUIREMENTS_INVALID_PARAMS
        ) from exc


def _unmet_requirement_params(*, requirement: Requirement, environment: PythonPackageEnvironment) -> dict[str, str]:
    """The parameters of `method.dependency_missing` for a requirement the environment does not meet.

    The requirement's package is missing (`not_found`), or the environment holds a version of it, or of what one of its
    extras needs, that the requirement does not accept (`no_matching_version`).
    """
    is_installed = environment.version_of(distribution_name=requirement.name) is not None
    reason = MethodDependencyMissingReason.NO_MATCHING_VERSION if is_installed else MethodDependencyMissingReason.NOT_FOUND
    return {"kind": MethodDependencyMissingKind.REQUIREMENT, "name": requirement.name, "reason": reason}


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
    raise MethodRequirementsFileError(msg, items=items).with_params(**_REQUIREMENTS_INVALID_PARAMS)


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
                params=_unmet_requirement_params(requirement=requirement_line.requirement, environment=environment),
            )
        )
    advice = environment.advice(requirement_texts=[unmet_requirement.requirement_line.text for unmet_requirement in unmet])
    msg = (
        f"{judged.method_name} needs Python packages that {environment.description} "
        f"does not have, as its {REQUIREMENTS_FILE_NAME} declares: {'; '.join(line_texts)}. {advice}"
    )
    first_requirement = unmet[0].requirement_line.requirement
    raise MethodRequirementsNotMetError(msg, items=items).with_params(
        **_unmet_requirement_params(requirement=first_requirement, environment=environment)
    )


def _ensure_judged_methods_met(*, judged_methods: Iterable[JudgedMethod], names_host_paths: bool) -> None:
    """Refuse the first of the methods whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    Each tree is judged once however often it is given, in the order given. The environment is resolved only once a tree
    declares a requirement to judge, so methods declaring none never read it.

    Raises:
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or cannot be read.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    environment: PythonPackageEnvironment | None = None
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
        if environment is None:
            environment = resolve_pipe_func_package_environment(names_host_paths=names_host_paths)
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
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements.
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
        MethodRequirementsNotMetError: The environment does not meet the package's requirements.
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
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    with reporting_host_library_tree_faults():
        library_trees = list_library_dir_trees(library_dirs=library_dirs, limits=limits)
    ensure_method_requirements_met(trees=[library_tree.tree for library_tree in library_trees], names_host_paths=False)
