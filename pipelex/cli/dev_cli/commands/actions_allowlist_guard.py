"""Core of the Actions allowlist guard.

GitHub checks every action a workflow uses against the organization's Actions policy when it creates
the run, and a workflow using one the policy refuses does not run at all: GitHub ends it in
``startup_failure`` before any job starts. The release workflows fire only when a release pull request
closes into ``main``, so pull-request CI never loads them, and an action the policy refuses there
surfaces only when a release is cut, as a release that publishes nothing.

This guard reads every workflow directly under ``.github/workflows/``, every local action under
``.github/actions/``, and every local action a ``./…`` reference names wherever it lives in the repository,
and refuses each ``uses:`` reference the policy mirrored in ``.github/actions-allowlist.toml`` would refuse.
A reference is allowed when it is:

1. local (``./…``), an action or reusable workflow of this repository, whose own ``uses:`` references are
   then read in turn, since the policy applies to the actions a local composite action uses as well;
2. created by GitHub (the ``actions`` and ``github`` owners), when the policy allows GitHub's actions;
3. owned by one of the enterprise's organizations listed in ``enterprise_owners``;
4. matched by one of ``patterns_allowed``.

Patterns follow GitHub's syntax. Where that syntax leaves a doubt, the guard takes the stricter reading,
so that a pass here is a pass on GitHub: ``*`` matches any run of characters except ``/`` and ``**`` any
run at all, and every comparison respects case, the owner and repository included, since GitHub does not
document whether its policy check ignores case. A ``docker://`` image is refused too, since no pattern can
name one.

The human-readable specification lives in ``docs/contribute/actions-allowlist.md``. The presentation
layer wired into the ``pipelex-dev`` Typer app lives in ``check_actions_allowlist_cmd.py``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import yaml

from pipelex.cli.dev_cli.commands.actions_allowlist_exceptions import ActionsAllowlistGuardError

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The committed mirror of the organization's Actions policy, relative to the repo root.
ALLOWLIST_FILE = Path(".github/actions-allowlist.toml")

#: Where GitHub reads workflows from: the files directly in this directory, never in a subdirectory.
WORKFLOWS_DIR = Path(".github/workflows")

#: Where this repository would keep its own composite actions, each in an ``action.yml``.
LOCAL_ACTIONS_DIR = Path(".github/actions")

#: The suffixes GitHub reads a workflow or an action definition from.
YAML_SUFFIXES = frozenset({".yml", ".yaml"})

#: The file names of an action definition.
ACTION_FILE_NAMES = frozenset({"action.yml", "action.yaml"})

#: The owners of the actions GitHub creates, which ``github_owned_allowed`` allows.
GITHUB_OWNERS = frozenset({"actions", "github"})

#: The prefix of a reference to an action or reusable workflow of this repository.
LOCAL_PREFIX = "./"

#: The prefix of a step that runs a Docker image rather than an action.
DOCKER_PREFIX = "docker://"

#: The complete set of keys the allowlist file carries; anything else fails the check.
_ALLOWLIST_KEYS = frozenset({"github_owned_allowed", "enterprise_owners", "patterns_allowed"})

REMEDY = (
    "use an action GitHub created, one an organization of the enterprise owns or one a pattern allows, or replace the step "
    "with a `run:` script; when the organization's policy itself changed, mirror it in .github/actions-allowlist.toml"
)


class ActionsAllowlist(NamedTuple):
    """The organization's Actions policy, as mirrored in ``.github/actions-allowlist.toml``.

    Attributes:
        github_owned_allowed: Whether actions created by GitHub are allowed.
        enterprise_owners: The enterprise's organizations, as GitHub spells them, whose actions are allowed.
        patterns_allowed: The policy's patterns, verbatim.
    """

    github_owned_allowed: bool
    enterprise_owners: frozenset[str]
    patterns_allowed: tuple[str, ...]


class ActionReference(NamedTuple):
    """One ``uses:`` value found in a workflow or an action definition, located for a report line."""

    relative_path: str
    lineno: int
    reference: str


class ActionsAllowlistViolation(NamedTuple):
    """One ``uses:`` reference the policy would refuse, with the reason."""

    relative_path: str
    lineno: int
    reference: str
    detail: str

    @property
    def key(self) -> str:
        """Stable sort key: file, then line."""
        return f"{self.relative_path}:{self.lineno:06d}"


def _string_list(*, raw: dict[str, Any], key: str, path: Path) -> list[str]:
    """Return ``raw[key]`` as a list of non-empty strings, or raise naming the file and the key."""
    value = raw.get(key)
    if not isinstance(value, list):
        msg = f"the Actions allowlist '{path}' must set `{key}` to a list of strings"
        raise ActionsAllowlistGuardError(msg)
    items = cast("list[Any]", value)
    strings: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            msg = f"the Actions allowlist '{path}' holds {item!r} in `{key}`, where every entry must be a non-empty string"
            raise ActionsAllowlistGuardError(msg)
        strings.append(item)
    return strings


def load_allowlist(*, path: Path) -> ActionsAllowlist:
    """Load and validate the committed mirror of the organization's Actions policy.

    Args:
        path: The allowlist file.

    Returns:
        The policy.

    Raises:
        ActionsAllowlistGuardError: When the file is missing, is not valid TOML, carries an unknown key, or
            misses or mistypes one of the keys it must carry. A missing allowlist is an error, never an empty
            policy, which would refuse every action in the repository.
    """
    if not path.is_file():
        msg = f"the Actions allowlist was not found at '{path}'. It is committed in the repository; run the check from the repo root."
        raise ActionsAllowlistGuardError(msg)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        msg = f"the Actions allowlist '{path}' is not valid TOML: {exc}"
        raise ActionsAllowlistGuardError(msg) from exc
    unknown_keys = set(raw) - _ALLOWLIST_KEYS
    if unknown_keys:
        msg = f"the Actions allowlist '{path}' has unknown key(s): {sorted(unknown_keys)}"
        raise ActionsAllowlistGuardError(msg)
    github_owned_allowed = raw.get("github_owned_allowed")
    if not isinstance(github_owned_allowed, bool):
        msg = f"the Actions allowlist '{path}' must set `github_owned_allowed` to true or false"
        raise ActionsAllowlistGuardError(msg)
    enterprise_owners = _string_list(raw=raw, key="enterprise_owners", path=path)
    patterns_allowed = _string_list(raw=raw, key="patterns_allowed", path=path)
    return ActionsAllowlist(
        github_owned_allowed=github_owned_allowed,
        enterprise_owners=frozenset(enterprise_owners),
        patterns_allowed=tuple(patterns_allowed),
    )


def _pattern_regex(*, pattern: str) -> re.Pattern[str]:
    """Translate a policy pattern into a regular expression: ``**`` matches anything, ``*`` anything but ``/``."""
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(parts))


def pattern_matches(*, pattern: str, reference: str) -> bool:
    """Whether a policy pattern allows a reference, read the strict way the module docstring describes."""
    return _pattern_regex(pattern=pattern).fullmatch(reference) is not None


def refusal_reason(*, reference: str, allowlist: ActionsAllowlist) -> str | None:
    """Say why the policy would refuse a ``uses:`` reference, or return ``None`` when it allows it.

    Args:
        reference: The ``uses:`` value, as written in the workflow.
        allowlist: The policy to check it against.

    Returns:
        ``None`` for an allowed reference, else a short reason for the report line.
    """
    if reference.startswith(LOCAL_PREFIX):
        return None
    if reference.startswith(DOCKER_PREFIX):
        return "is a Docker image, which no pattern of the policy can name"
    name, separator, ref = reference.partition("@")
    segments = name.split("/")
    if not separator or not ref or len(segments) < 2 or not all(segments):
        return "is not of the form `owner/repository[/path]@ref`"
    owner = segments[0]
    if allowlist.github_owned_allowed and owner in GITHUB_OWNERS:
        return None
    if owner in allowlist.enterprise_owners:
        return None
    for pattern in allowlist.patterns_allowed:
        if pattern_matches(pattern=pattern, reference=reference):
            return None
    return "is not created by GitHub, not owned by the enterprise, and matched by no pattern of the policy"


def _mapping_value(*, node: yaml.Node | None, key: str) -> yaml.Node | None:
    """Return the value under ``key`` when ``node`` is a mapping holding it, else ``None``."""
    if not isinstance(node, yaml.MappingNode):
        return None
    pairs = cast("list[tuple[yaml.Node, yaml.Node]]", node.value)
    for key_node, value_node in pairs:
        if isinstance(key_node, yaml.ScalarNode) and key_node.value == key:
            return value_node
    return None


def _uses_in_steps(*, steps: yaml.Node | None) -> Iterator[yaml.Node]:
    """Yield the ``uses:`` value of every step in a ``steps:`` sequence."""
    if not isinstance(steps, yaml.SequenceNode):
        return
    step_nodes = cast("list[yaml.Node]", steps.value)
    for step in step_nodes:
        uses = _mapping_value(node=step, key="uses")
        if uses is not None:
            yield uses


def _uses_nodes(*, document: yaml.Node) -> Iterator[yaml.Node]:
    """Yield every ``uses:`` value of a workflow or an action definition.

    A workflow names actions in ``jobs.<job>.steps[].uses`` and reusable workflows in ``jobs.<job>.uses``;
    a composite action names actions in ``runs.steps[].uses``. A ``uses`` key anywhere else, under a step's
    ``with:`` for instance, is an input and not a reference, so the walk follows that structure rather than
    every key of the document.
    """
    jobs = _mapping_value(node=document, key="jobs")
    if isinstance(jobs, yaml.MappingNode):
        job_pairs = cast("list[tuple[yaml.Node, yaml.Node]]", jobs.value)
        for _job_key, job in job_pairs:
            job_uses = _mapping_value(node=job, key="uses")
            if job_uses is not None:
                yield job_uses
            yield from _uses_in_steps(steps=_mapping_value(node=job, key="steps"))
    yield from _uses_in_steps(steps=_mapping_value(node=_mapping_value(node=document, key="runs"), key="steps"))


def find_references_in_source(*, source: str, relative_path: str) -> list[ActionReference]:
    """Return every ``uses:`` reference of one workflow or action definition, with its line.

    Args:
        source: The YAML text.
        relative_path: The file's repo-root-relative posix path, for the report.

    Returns:
        The references in document order. A ``uses:`` that is not a string is returned with its YAML text,
        so that the check refuses it rather than skipping it.

    Raises:
        ActionsAllowlistGuardError: When the file is not valid YAML, since an unread file is an unchecked one.
    """
    # The loader's own composer, which is what `yaml.compose_all` drives: it keeps each node's line.
    loader = yaml.SafeLoader(source)
    documents: list[yaml.Node] = []
    try:
        while loader.check_node():
            document = loader.get_node()
            if document is not None:
                documents.append(document)
    except yaml.YAMLError as exc:
        msg = f"'{relative_path}' is not valid YAML, so its actions cannot be checked: {exc}"
        raise ActionsAllowlistGuardError(msg) from exc
    references: list[ActionReference] = []
    for document in documents:
        for node in _uses_nodes(document=document):
            reference = node.value if isinstance(node, yaml.ScalarNode) else f"<{node.tag}>"
            references.append(ActionReference(relative_path=relative_path, lineno=node.start_mark.line + 1, reference=str(reference)))
    return references


def iter_workflow_files(*, root: Path) -> Iterator[Path]:
    """Yield, sorted, every workflow GitHub would read and every local action definition under ``root``."""
    workflows_dir = root / WORKFLOWS_DIR
    if workflows_dir.is_dir():
        for path in sorted(workflows_dir.iterdir()):
            if path.is_file() and path.suffix in YAML_SUFFIXES:
                yield path
    actions_dir = root / LOCAL_ACTIONS_DIR
    if actions_dir.is_dir():
        for path in sorted(actions_dir.rglob("*")):
            if path.is_file() and path.name in ACTION_FILE_NAMES:
                yield path


def _local_definition(*, root: Path, reference: str) -> tuple[Path | None, str | None]:
    """Find the file a ``./…`` reference names, so that its own references can be read in turn.

    A reference to a workflow file names that file; any other names a directory holding ``action.yml`` or
    ``action.yaml``, which is how GitHub finds a local action wherever it lives in the repository.

    Args:
        root: The repo root.
        reference: The ``uses:`` value, starting with ``./``.

    Returns:
        The file to read and no reason, or no file and the reason the guard cannot read the definition, which
        the check reports, since an action it cannot read is an action it has not checked.
    """
    root_resolved = root.resolve()
    target = (root / reference.removeprefix(LOCAL_PREFIX)).resolve()
    if not target.is_relative_to(root_resolved):
        return None, "names a path outside the repository"
    relative_target = target.relative_to(root_resolved)
    if target.is_file() and target.suffix in YAML_SUFFIXES:
        return root / relative_target, None
    if target.is_dir():
        for file_name in sorted(ACTION_FILE_NAMES):
            if (target / file_name).is_file():
                return root / relative_target / file_name, None
        return None, "names a local action with no action.yml or action.yaml, which the guard cannot read"
    return None, "names a local action or workflow that does not exist"


def collect_violations(*, root: Path) -> list[ActionsAllowlistViolation]:
    """Check every ``uses:`` reference under ``root`` against the committed allowlist, and return the refusals sorted.

    The scan starts from the workflows and the ``.github/actions/`` definitions, and reads every local action or
    reusable workflow a ``./…`` reference names as well, once each, wherever it lives in the repository.

    Args:
        root: The repo root, which holds ``.github/``.

    Raises:
        ActionsAllowlistGuardError: When the allowlist cannot be loaded, a workflow is not valid YAML, or the scan
            finds no workflow or no reference at all. The last two mean the root is not the repo root or the walk
            no longer reads GitHub's structure, and the guard would otherwise report a pass having checked nothing.
    """
    allowlist = load_allowlist(path=root / ALLOWLIST_FILE)
    violations: list[ActionsAllowlistViolation] = []
    pending = list(iter_workflow_files(root=root))
    seen = {path.resolve() for path in pending}
    nb_files = 0
    nb_references = 0
    while pending:
        path = pending.pop(0)
        nb_files += 1
        relative_path = path.relative_to(root).as_posix()
        for found in find_references_in_source(source=path.read_text(encoding="utf-8"), relative_path=relative_path):
            nb_references += 1
            reason: str | None
            if found.reference.startswith(LOCAL_PREFIX):
                definition, reason = _local_definition(root=root, reference=found.reference)
                if definition is not None and definition.resolve() not in seen:
                    seen.add(definition.resolve())
                    pending.append(definition)
            else:
                reason = refusal_reason(reference=found.reference, allowlist=allowlist)
            if reason is not None:
                violations.append(
                    ActionsAllowlistViolation(relative_path=found.relative_path, lineno=found.lineno, reference=found.reference, detail=reason)
                )
    if nb_files == 0 or nb_references == 0:
        msg = (
            f"the Actions allowlist guard read {nb_files} workflow file(s) under `{root / WORKFLOWS_DIR}` and found "
            f"{nb_references} `uses:` reference(s), so it checked nothing. Run it from the repo root."
        )
        raise ActionsAllowlistGuardError(msg)
    return sorted(violations, key=lambda violation: violation.key)
