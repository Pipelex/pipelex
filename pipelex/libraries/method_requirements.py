"""Checking a method's `requirements.txt` against the Python environment its PipeFunc steps run in, when the method loads.

The MTHDS standard (`mthds/docs/spec/method-tree.md`, "Python Dependencies: `requirements.txt`") lets a method declare
the Python packages its own Python needs in a `requirements.txt` at the root of its method tree, whose lines are read
as `pipelex/core/method_trees/requirements_file.py` reads them: a line the standard refuses is named with why.

Pipelex refuses a method whose requirements are not met when it loads, naming each package it cannot satisfy, and
never installs anything:

- A tree is checked when it holds `requirements.txt` at its root and holds Python, a `.py` file anywhere in it: a tree
  with no Python has nothing that could import a package. The check runs before any of the tree's Python is imported,
  or scanned for structure classes on a sandbox-hosted deployment, and before any of its pipes is built.
- The environment is the one the PipeFunc steps run in (`pipelex/libraries/package_environments.py`): this interpreter
  in the `direct` execution mode, and in a sandbox-hosted mode the packages the deployment states its sandbox offers
  for the tree's requirements, asked for each tree, so trees judged together each get the offer stated for their own.
  A deployment that cannot hold a tree's requirements in any environment refuses them with its own reason, which the
  method's refusal carries.
- A tree is judged once per run: the run's listing (`pipelex.libraries.method_tree_listing`) keeps each tree a check
  found met, with the execution mode and the plugin factory it was judged against, so the later steps of a load, a load
  after a server's check of the same request, or a dependency package loaded again ask nothing more while those are
  unchanged, and two loads judging the tree at once ask once. A refused tree is never kept, and is judged again by the
  next check that reads it.
- The `requirements.txt` judged is read against the hash the tree's listing recorded, so the file judged is the file the
  run's digest names.
- A requirement whose marker is false in that environment is not needed there and is not checked. One is met when the
  environment holds a distribution of its name at a version its specifier contains, pre-releases included, and, for
  each extra it names, when what the extra needs is met in turn.

A refusal names the file by its path in the method's tree, and names paths on this host, the method's root and this
interpreter, only where it may: a check inside a load does, since its refusal is either the caller's own disk's or,
around a host's own library directories, the host's fault, which `reporting_host_library_tree_faults` withholds from
the caller. A dependency package is named by its address, and a server checking a caller's method it holds in a
directory of its own names no path on the host at all (`ensure_served_method_requirements_met`).
"""

import functools
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.models import MethodTree
from mthds.protocol.problem.registry import MethodDependencyMissingKind, MethodDependencyMissingReason
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
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.libraries.method_trees import listing_identity, read_tree_file_as_listed, reporting_host_library_tree_faults
from pipelex.libraries.package_environments import (
    PythonPackageEnvironment,
    current_pipe_func_environment_source,
    resolve_pipe_func_package_environment,
)
from pipelex.methods.package_reason import MethodPackageReason
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageRefusal

# The parameters of `method.package_invalid` for a `requirements.txt` the standard refuses or that cannot be read.
_REQUIREMENTS_INVALID_PARAMS: dict[str, str] = {"reason": MethodPackageReason.REQUIREMENTS_INVALID, "path": REQUIREMENTS_FILE_NAME}

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


class UnmetDistribution(NamedTuple):
    """Why a requirement is not met, and the distribution that fails it: the one required, or one an extra of it needs."""

    reason: str
    distribution_name: str
    missing_reason: MethodDependencyMissingReason


class UnmetRequirement(NamedTuple):
    """A requirement the environment does not meet, with why, and the distribution that fails it."""

    requirement_line: RequirementLine
    reason: str
    distribution_name: str
    missing_reason: MethodDependencyMissingReason


def marker_variables_of(*, marker: Marker) -> set[str]:
    """The PEP 508 variables a marker reads, its quoted values set aside so a value spelled like a variable is never one."""
    unquoted = _QUOTED_MARKER_VALUE.sub(" ", str(marker))
    return {word for word in _MARKER_WORD.findall(unquoted) if word in _MARKER_VARIABLES or word == "extra"}


def _evaluate_marker(*, marker: Marker, marker_environment: Mapping[str, str], extra: str) -> bool:
    """A marker's value in the marker environment, reading `extra` as given.

    Raises:
        UndefinedComparison: The marker compares values that are not versions.
        UndefinedEnvironmentName: The marker reads a variable the evaluation does not define.
        InvalidVersion: The marker compares, as versions, a value that is not one; releases of `packaging` before 22
            raise it where later ones compare the values as strings.
    """
    return marker.evaluate(environment={**marker_environment, "extra": extra})


def _unmet_reason(
    *,
    requirement: Requirement,
    environment: PythonPackageEnvironment,
    followed_extras: set[tuple[str, str]],
) -> UnmetDistribution | None:
    """Why the environment does not meet a requirement whose marker it already judged true, or None when it does.

    The distribution that fails it is the one required, missing or held at a version the requirement does not accept,
    or one that an extra of it needs, followed down the extras.
    """
    installed_version = environment.version_of(distribution_name=requirement.name)
    if installed_version is None:
        return UnmetDistribution(
            reason=f"{requirement.name} is missing", distribution_name=requirement.name, missing_reason=MethodDependencyMissingReason.NOT_FOUND
        )
    try:
        version = Version(installed_version)
    except InvalidVersion:
        return UnmetDistribution(
            reason=f"{requirement.name} {installed_version} is there, a version no specifier can be compared with",
            distribution_name=requirement.name,
            missing_reason=MethodDependencyMissingReason.NO_MATCHING_VERSION,
        )
    if not requirement.specifier.contains(version, prereleases=True):
        return UnmetDistribution(
            reason=f"{requirement.name} {installed_version} is there",
            distribution_name=requirement.name,
            missing_reason=MethodDependencyMissingReason.NO_MATCHING_VERSION,
        )
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
) -> UnmetDistribution | None:
    """Why the environment does not meet what an extra of a distribution it holds needs, or None when it does.

    An extra needs each requirement of the distribution's metadata whose marker holds with the extra and not without
    it. Each extra is followed once, so extras that name one another end. The distribution that fails is the one the
    extra needs; when the environment does not state what the extra needs, it is the distribution holding the extra,
    which is there in a form that cannot be shown to serve the requirement.
    """
    key = (canonicalize_name(distribution_name), canonicalize_name(extra))
    if key in followed_extras:
        return None
    followed_extras.add(key)
    dependencies = environment.dependencies_of(distribution_name=distribution_name)
    if dependencies is None:
        return UnmetDistribution(
            reason=(
                f"{environment.description} does not state what the extra '{extra}' of {distribution_name} needs; "
                "list the packages it needs in requirements.txt instead"
            ),
            distribution_name=distribution_name,
            missing_reason=MethodDependencyMissingReason.NO_MATCHING_VERSION,
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
            needed_by_extra = _evaluate_marker(marker=dependency.marker, marker_environment=environment.marker_environment, extra=extra)
            needed_anyway = _evaluate_marker(marker=dependency.marker, marker_environment=environment.marker_environment, extra="")
        except (UndefinedComparison, UndefinedEnvironmentName, InvalidVersion):
            continue
        if not needed_by_extra or needed_anyway:
            continue
        dependency_unmet = _unmet_reason(requirement=dependency, environment=environment, followed_extras=followed_extras)
        if dependency_unmet is not None:
            return dependency_unmet._replace(
                reason=f"the extra '{extra}' of {distribution_name} needs '{dependency_text}', and {dependency_unmet.reason}"
            )
    return None


def unmet_requirements(*, requirements: Iterable[RequirementLine], environment: PythonPackageEnvironment) -> list[UnmetRequirement]:
    """The requirements the environment does not meet, in the order given, each with why."""
    unmet: list[UnmetRequirement] = []
    for requirement_line in requirements:
        unmet_distribution = _requirement_line_unmet_reason(requirement_line=requirement_line, environment=environment)
        if unmet_distribution is not None:
            unmet.append(
                UnmetRequirement(
                    requirement_line=requirement_line,
                    reason=unmet_distribution.reason,
                    distribution_name=unmet_distribution.distribution_name,
                    missing_reason=unmet_distribution.missing_reason,
                )
            )
    return unmet


def requirements_needed_in(*, requirements: Iterable[RequirementLine], marker_environment: Mapping[str, str]) -> list[RequirementLine]:
    """The requirements a place with this PEP 508 marker environment needs, in the order given: all but those whose marker is false there.

    The check skips a requirement whose marker is false in the environment it judges against, as not needed there, so
    a package-offer factory refusing a method's requirements rests its refusal on these alone, read in the marker
    environment of the place it would run the method in, never on a requirement the place does not need. A requirement
    whose marker reads a variable the marker environment does not state, or cannot be evaluated, is kept: the check
    refuses it there rather than skipping it.
    """
    needed: list[RequirementLine] = []
    for requirement_line in requirements:
        marker = requirement_line.requirement.marker
        if marker is None or not _is_marker_false(marker=marker, marker_environment=marker_environment):
            needed.append(requirement_line)
    return needed


def _is_marker_false(*, marker: Marker, marker_environment: Mapping[str, str]) -> bool:
    """Whether a marker is judged false in the marker environment, as the check judges it: one it cannot judge is not."""
    if marker_variables_of(marker=marker) - set(marker_environment) - {"extra"}:
        return False
    try:
        return not _evaluate_marker(marker=marker, marker_environment=marker_environment, extra="")
    except (UndefinedComparison, UndefinedEnvironmentName, InvalidVersion):
        return False


def _requirement_line_unmet_reason(*, requirement_line: RequirementLine, environment: PythonPackageEnvironment) -> UnmetDistribution | None:
    requirement = requirement_line.requirement
    marker = requirement.marker
    if marker is not None:
        unstated = sorted(marker_variables_of(marker=marker) - set(environment.marker_environment) - {"extra"})
        if unstated:
            return _unjudged_requirement(
                reason=f"its marker reads {', '.join(unstated)}, which {environment.description} does not state",
                requirement=requirement,
                environment=environment,
            )
        try:
            if not _evaluate_marker(marker=marker, marker_environment=environment.marker_environment, extra=""):
                return None
        except (UndefinedComparison, UndefinedEnvironmentName, InvalidVersion) as exc:
            return _unjudged_requirement(reason=f"its marker cannot be evaluated: {exc}", requirement=requirement, environment=environment)
    return _unmet_reason(requirement=requirement, environment=environment, followed_extras=set())


def _unjudged_requirement(*, reason: str, requirement: Requirement, environment: PythonPackageEnvironment) -> UnmetDistribution:
    """A requirement whose marker the environment cannot judge, failed by the distribution it requires.

    The distribution is missing (`not_found`), or held in a form the requirement cannot be shown to accept
    (`no_matching_version`).
    """
    is_installed = environment.version_of(distribution_name=requirement.name) is not None
    missing_reason = MethodDependencyMissingReason.NO_MATCHING_VERSION if is_installed else MethodDependencyMissingReason.NOT_FOUND
    return UnmetDistribution(reason=reason, distribution_name=requirement.name, missing_reason=missing_reason)


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
    """The text of a tree's `requirements.txt`, read against the hash the tree's listing recorded.

    Raises:
        MethodRequirementsFileError: The file is not UTF-8 text.
        MethodTreeChangedError: The file is no longer the one the tree's listing hashed, or can no longer be read.
    """
    source = judged.requirements_source
    data = read_tree_file_as_listed(tree=judged.tree, tree_path=REQUIREMENTS_FILE_NAME)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{judged.method_name} declares its packages in a {REQUIREMENTS_FILE_NAME} that is not UTF-8 text, so they cannot be read."
        raise MethodRequirementsFileError(msg, items=[PipelexBundleBlueprintValidationErrorData(source=source, message=msg)]).with_params(
            **_REQUIREMENTS_INVALID_PARAMS
        ) from exc


def _unmet_requirement_params(*, unmet_requirement: UnmetRequirement) -> dict[str, str]:
    """The parameters of `method.dependency_missing` for a requirement the environment does not meet.

    They name the distribution that fails it: the one required, or one an extra of it needs, which is missing
    (`not_found`) or held at a version the requirement does not accept (`no_matching_version`).
    """
    return {
        "kind": MethodDependencyMissingKind.REQUIREMENT,
        "name": unmet_requirement.distribution_name,
        "reason": unmet_requirement.missing_reason,
    }


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
                params=_unmet_requirement_params(unmet_requirement=unmet_requirement),
            )
        )
    advice = environment.advice(requirement_texts=[unmet_requirement.requirement_line.text for unmet_requirement in unmet])
    msg = (
        f"{judged.method_name} needs Python packages that {environment.description} "
        f"does not have, as its {REQUIREMENTS_FILE_NAME} declares: {'; '.join(line_texts)}. {advice}"
    )
    raise MethodRequirementsNotMetError(msg, items=items).with_params(**_unmet_requirement_params(unmet_requirement=unmet[0]))


def _refused_by_deployment_error(
    *, judged: JudgedMethod, refusal: PipeFuncPackageRefusal, requirements: Sequence[RequirementLine]
) -> MethodRequirementsNotMetError:
    """The refusal of a method whose requirements the deployment cannot hold in any environment, carrying its reason.

    The deployment's reason is about the requirements together, such as a conflict its resolver found among them, so the
    one item it rides on names the file and no line. `method.dependency_missing` names one distribution, as a refusal
    of several unmet requirements names the first of them: the first requirement the file declares, with the `reason`
    `no_matching_version`, since no set of versions the deployment can build satisfies the requirements.
    """
    params = {
        "kind": MethodDependencyMissingKind.REQUIREMENT,
        "name": requirements[0].requirement.name,
        "reason": MethodDependencyMissingReason.NO_MATCHING_VERSION,
    }
    msg = (
        f"{judged.method_name} needs Python packages that {refusal.environment} cannot offer, "
        f"as its {REQUIREMENTS_FILE_NAME} declares: {refusal.reason}"
    )
    item = PipelexBundleBlueprintValidationErrorData(
        source=judged.requirements_source,
        message=f"The requirements are refused by {refusal.environment}: {refusal.reason}",
        params=params,
    )
    return MethodRequirementsNotMetError(msg, items=[item]).with_params(**params)


def _ensure_judged_methods_met(*, judged_methods: Iterable[JudgedMethod], names_host_paths: bool, tree_listing: MethodTreeListing | None) -> None:
    """Refuse the first of the methods whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    Each tree is judged once however often it is given, in the order given, against the environment stated for its own
    requirements: in a sandbox-hosted mode, the plugin providing the mode is asked for each tree declaring requirements,
    so trees judged together never share an environment stated for another's. Methods declaring none never read it. A
    tree `tree_listing` holds as met against the current execution mode and factory, which an earlier check of the run
    judged, is not judged again, each tree found met is kept there for the run's later checks, and a tree two checks
    judge at once is judged by one of them (`MethodTreeListing.judge_requirements_once`).

    Raises:
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or is not UTF-8 text.
        MethodTreeChangedError: A tree's `requirements.txt` is no longer the file its tree's listing hashed.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements, or the deployment refuses
            them with its own reason, no environment of its holding them.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    judged_trees: set[tuple[str, str, bool]] = set()
    environment_source = current_pipe_func_environment_source() if tree_listing is not None else None
    for judged in judged_methods:
        tree_identity = listing_identity(tree=judged.tree)
        if tree_identity in judged_trees:
            continue
        judged_trees.add(tree_identity)
        if tree_listing is None:
            _ensure_judged_method_met(judged=judged, names_host_paths=names_host_paths)
            continue
        tree_listing.judge_requirements_once(
            tree=judged.tree,
            judged_against=environment_source,
            judge=functools.partial(_ensure_judged_method_met, judged=judged, names_host_paths=names_host_paths),
        )


def _ensure_judged_method_met(*, judged: JudgedMethod, names_host_paths: bool) -> None:
    """Refuse a method whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    A tree with nothing to check, holding no requirements or no Python, meets them.

    Raises:
        MethodRequirementsFileError: The tree's `requirements.txt` holds a line the standard refuses, or is not UTF-8 text.
        MethodTreeChangedError: The tree's `requirements.txt` is no longer the file its listing hashed.
        MethodRequirementsNotMetError: The environment does not meet the tree's requirements, or the deployment refuses
            them with its own reason.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    if not holds_requirements_to_check(tree=judged.tree):
        return
    parsed = parse_requirements_text(text=_read_requirements_text(judged=judged))
    if parsed.refused_lines:
        _raise_refused_lines(judged=judged, refused_lines=parsed.refused_lines)
    if not parsed.requirements:
        return
    environment = resolve_pipe_func_package_environment(requirements=parsed.requirements, names_host_paths=names_host_paths)
    if isinstance(environment, PipeFuncPackageRefusal):
        raise _refused_by_deployment_error(judged=judged, refusal=environment, requirements=parsed.requirements)
    unmet = unmet_requirements(requirements=parsed.requirements, environment=environment)
    if unmet:
        _raise_unmet(judged=judged, unmet=unmet, environment=environment)


def ensure_method_requirements_met(*, trees: Iterable[MethodTree], names_host_paths: bool, tree_listing: MethodTreeListing | None = None) -> None:
    """Refuse a method among the trees whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    Each tree is judged once however often it is given, in the order given, and the first refused ends the check.

    Args:
        trees: The method trees a load reads, each checked when it lies on disk, declares requirements and holds Python.
        names_host_paths: Whether a refusal may name the method's root and this interpreter by their paths on this host,
            as a load's may: its refusal is the caller's own disk's, or the host's fault, withheld from the caller.
        tree_listing: The run's listing of its method trees, which keeps each tree a check of the run found met with the
            execution mode and factory it was judged against: such a tree is not judged again against them, so the
            package-offer factory is asked once per tree in a run, whose verdict does not depend on how a refusal names
            the method. None judges every tree given.

    Raises:
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or is not UTF-8 text.
        MethodTreeChangedError: A tree's `requirements.txt` is no longer the file its tree's listing hashed.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements, or the deployment refuses
            them with its own reason.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    _ensure_judged_methods_met(
        judged_methods=(_judged_method(tree=tree, names_host_paths=names_host_paths) for tree in trees),
        names_host_paths=names_host_paths,
        tree_listing=tree_listing,
    )


def ensure_package_requirements_met(*, tree: MethodTree, package_address: str, tree_listing: MethodTreeListing | None = None) -> None:
    """Refuse a dependency package whose `requirements.txt` the standard refuses or its PipeFunc environment does not meet.

    The package is named by its address and its file by `<address>/requirements.txt`, never by the directory it was
    installed or fetched into, as its bundles are, since the package is the caller's dependency wherever it loads. A
    package `tree_listing` holds as met is not judged again, as a method's tree is not (`ensure_method_requirements_met`).

    Raises:
        MethodRequirementsFileError: The package's `requirements.txt` holds a line the standard refuses, or is not UTF-8 text.
        MethodTreeChangedError: The package's `requirements.txt` is no longer the file its tree's listing hashed.
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
    _ensure_judged_methods_met(judged_methods=[judged], names_host_paths=False, tree_listing=tree_listing)


def ensure_served_method_requirements_met(*, library_dirs: Sequence[Path], tree_listing: MethodTreeListing | None = None) -> None:
    """Check the requirements of a caller's method a server holds in directories of its own, as loading them would, without loading them.

    For a server that hands the method to a loader elsewhere, such as a validator whose worker receives the method's
    trees through its own method file store rather than these directories, or that loads them as its own library
    directories, so the refusal is the caller's and comes, before anything loads or is dispatched, from the process that
    holds the method's files. The directories are the server's: a tree of them that cannot be listed is the
    host's fault, as a load of a host's library directories reports it, and a refusal names no path on the host, the
    directories' and this interpreter's included.

    The trees are listed through `tree_listing`, which the server hands to the load of the same request, so the method
    loaded is the one checked here and its files are listed and hashed once (`pipelex.libraries.method_tree_listing`),
    and the listing keeps each tree found met, so the load does not judge it again. None lists them for this check alone.

    Raises:
        HostLibraryTreeError: A tree of the directories could not be listed.
        MethodRequirementsFileError: A tree's `requirements.txt` holds a line the standard refuses, or is not UTF-8 text.
        MethodTreeChangedError: A tree's `requirements.txt` is no longer the file its tree's listing hashed.
        MethodRequirementsNotMetError: The environment does not meet a tree's requirements, or the deployment refuses
            them with its own reason.
        PipeFuncPackageSetUnstatedError: PipeFunc steps run out of this process and the deployment states no package
            set for them.
    """
    listing = tree_listing if tree_listing is not None else MethodTreeListing()
    with reporting_host_library_tree_faults():
        library_trees = listing.library_dir_trees(library_dirs=library_dirs)
    ensure_method_requirements_met(trees=[library_tree.tree for library_tree in library_trees], names_host_paths=False, tree_listing=listing)
