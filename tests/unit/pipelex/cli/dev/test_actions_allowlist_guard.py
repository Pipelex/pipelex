from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.actions_allowlist_exceptions import ActionsAllowlistGuardError
from pipelex.cli.dev_cli.commands.actions_allowlist_guard import (
    ALLOWLIST_FILE,
    ActionsAllowlist,
    collect_violations,
    find_references_in_source,
    iter_workflow_files,
    load_allowlist,
    pattern_matches,
    refusal_reason,
)

#: Anchored on `tests/` by name rather than by a parent count, for the reason `test_hub_layering_guard.py` gives.
_REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

#: The action that stopped a release at startup, refused by the organization's policy.
REFUSED_ACTION = "peter-evans/dockerhub-description@1b9a80c056b620d92cedb9d9b5a223409c68ddfa"

POLICY = ActionsAllowlist(
    github_owned_allowed=True,
    enterprise_owners=frozenset({"Pipelex"}),
    patterns_allowed=("astral-sh/setup-uv@*", "dorny/paths-filter@v3", "octo-org/*", "space-org*/**"),
)

ALLOWLIST_TOML = 'github_owned_allowed = true\nenterprise_owners = ["Pipelex"]\npatterns_allowed = ["astral-sh/setup-uv@*"]\n'

WORKFLOW = """\
name: Sample
on: pull_request
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: A step that names an input called uses
        uses: astral-sh/setup-uv@v7
        with:
          uses: not-a-reference
      - run: echo done
  reuse:
    uses: ./.github/workflows/other.yml
"""

#: The reusable workflow `WORKFLOW` calls with `./.github/workflows/other.yml`.
OTHER_WORKFLOW = "on: workflow_call\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n"

COMPOSITE_ACTION = """\
name: Local action
runs:
  using: composite
  steps:
    - uses: dorny/paths-filter@v3
    - run: echo done
      shell: bash
"""


def _write_tree(*, root: Path, workflows: dict[str, str], allowlist: str | None = ALLOWLIST_TOML) -> None:
    """Lay out a repository holding the given workflows and, unless None, the given allowlist."""
    workflows_dir = root / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    for name, content in workflows.items():
        (workflows_dir / name).write_text(textwrap.dedent(content), encoding="utf-8")
    if allowlist is not None:
        (root / ALLOWLIST_FILE).write_text(allowlist, encoding="utf-8")


class TestActionsAllowlistGuard:
    @pytest.mark.parametrize(
        ("topic", "pattern", "reference", "expected"),
        [
            ("any ref of one action", "astral-sh/setup-uv@*", "astral-sh/setup-uv@v7", True),
            ("any ref, a commit SHA", "pypa/gh-action-pypi-publish@*", "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33", True),
            ("one exact tag", "dorny/paths-filter@v3", "dorny/paths-filter@v3", True),
            ("another tag than the pinned one", "dorny/paths-filter@v3", "dorny/paths-filter@v4", False),
            ("a ref merely starting like the pinned one", "dorny/paths-filter@v3", "dorny/paths-filter@v3.1", False),
            ("owner and repository compare with case", "PyO3/maturin-action@*", "pyo3/maturin-action@v1", False),
            ("the ref compares with case", "dorny/paths-filter@v3", "dorny/paths-filter@V3", False),
            ("one star stops at a slash", "octo-org/*", "octo-org/repo/sub/path@v1", False),
            ("one star crosses the ref", "octo-org/*", "octo-org/repo@v1", True),
            ("two stars cross slashes", "space-org*/**", "space-org-x/repo/sub@v1", True),
            ("another owner", "astral-sh/setup-uv@*", "evil-sh/setup-uv@v7", False),
        ],
    )
    def test_patterns_read_strictly(self, topic: str, pattern: str, reference: str, expected: bool) -> None:
        """Where GitHub's pattern syntax leaves a doubt the guard takes the stricter reading."""
        assert pattern_matches(pattern=pattern, reference=reference) is expected, topic

    @pytest.mark.parametrize(
        ("topic", "reference", "allowed"),
        [
            ("a local action", "./.github/actions/setup", True),
            ("a local reusable workflow", "./.github/workflows/publish-docker-hub.yml", True),
            ("an action GitHub created", "actions/checkout@v4", True),
            ("another action GitHub created", "github/codeql-action/init@v3", True),
            ("an enterprise-owned action", "Pipelex/some-action@v1", True),
            ("an enterprise owner spelled with another case", "pipelex/some-action@v1", False),
            ("an action a pattern allows", "astral-sh/setup-uv@v7", True),
            ("the action that stopped a release", REFUSED_ACTION, False),
            ("a Docker image", "docker://alpine:3.20", False),
            ("a reference without a ref", "astral-sh/setup-uv", False),
            ("a reference without a repository", "astral-sh@v7", False),
        ],
    )
    def test_refusal_reason(self, topic: str, reference: str, allowed: bool) -> None:
        """Local, GitHub-created, enterprise-owned and pattern-matched references pass; anything else is refused with a reason."""
        reason = refusal_reason(reference=reference, allowlist=POLICY)
        assert (reason is None) is allowed, f"{topic}: {reason}"

    def test_github_owned_actions_need_the_policy_to_allow_them(self) -> None:
        """`github_owned_allowed = false` withdraws the allowance the owner alone gave."""
        policy = POLICY._replace(github_owned_allowed=False)
        assert refusal_reason(reference="actions/checkout@v4", allowlist=policy) is not None

    def test_reads_references_where_github_reads_them(self) -> None:
        """Steps and job-level reusable workflows count, with their lines; a `uses` key under `with:` is an input, not a reference."""
        references = find_references_in_source(source=WORKFLOW, relative_path=".github/workflows/sample.yml")
        assert [(found.lineno, found.reference) for found in references] == [
            (7, "actions/checkout@v4"),
            (9, "astral-sh/setup-uv@v7"),
            (14, "./.github/workflows/other.yml"),
        ]

    def test_reads_the_steps_of_a_composite_action(self) -> None:
        references = find_references_in_source(source=COMPOSITE_ACTION, relative_path=".github/actions/local/action.yml")
        assert [found.reference for found in references] == ["dorny/paths-filter@v3"]

    def test_a_non_string_uses_is_reported_rather_than_skipped(self) -> None:
        source = "jobs:\n  build:\n    steps:\n      - uses: {owner: someone}\n"
        references = find_references_in_source(source=source, relative_path=".github/workflows/odd.yml")
        assert len(references) == 1
        assert refusal_reason(reference=references[0].reference, allowlist=POLICY) is not None

    def test_invalid_yaml_is_an_error(self) -> None:
        with pytest.raises(ActionsAllowlistGuardError, match="not valid YAML"):
            find_references_in_source(source="jobs: [unclosed\n", relative_path=".github/workflows/broken.yml")

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            pytest.param(ALLOWLIST_TOML + "verified_allowed = false\n", "unknown key", id="an unknown key"),
            pytest.param('github_owned_allowed = true\nenterprise_owners = ["Pipelex"]\n', "patterns_allowed", id="a missing key"),
            pytest.param(
                'github_owned_allowed = "yes"\nenterprise_owners = []\npatterns_allowed = []\n', "github_owned_allowed", id="a mistyped flag"
            ),
            pytest.param('github_owned_allowed = true\nenterprise_owners = []\npatterns_allowed = [""]\n', "non-empty string", id="an empty pattern"),
            pytest.param("github_owned_allowed = \n", "not valid TOML", id="invalid TOML"),
        ],
    )
    def test_a_malformed_allowlist_is_an_error(self, tmp_path: Path, content: str, message: str) -> None:
        path = tmp_path / "actions-allowlist.toml"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ActionsAllowlistGuardError, match=message):
            load_allowlist(path=path)

    def test_a_missing_allowlist_is_an_error_not_an_empty_policy(self, tmp_path: Path) -> None:
        _write_tree(root=tmp_path, workflows={"ci.yml": WORKFLOW}, allowlist=None)
        with pytest.raises(ActionsAllowlistGuardError, match="not found"):
            collect_violations(root=tmp_path)

    def test_collects_the_refused_references_of_a_tree(self, tmp_path: Path) -> None:
        """A refused action is reported at its file and line, and the allowed ones beside it are not."""
        release = f"jobs:\n  publish:\n    steps:\n      - uses: Pipelex/some-action@v1\n      - uses: {REFUSED_ACTION}\n"
        _write_tree(root=tmp_path, workflows={"ci.yml": WORKFLOW, "other.yml": OTHER_WORKFLOW, "release.yml": release})
        violations = collect_violations(root=tmp_path)
        assert [(violation.relative_path, violation.lineno, violation.reference) for violation in violations] == [
            (".github/workflows/release.yml", 5, REFUSED_ACTION),
        ]

    @pytest.mark.parametrize(
        ("reference", "action_files", "expected"),
        [
            pytest.param(
                "./ci/my-action",
                {"ci/my-action/action.yml": f"runs:\n  using: composite\n  steps:\n    - uses: {REFUSED_ACTION}\n"},
                [("ci/my-action/action.yml", 4, REFUSED_ACTION, "matched by no pattern")],
                id="a refused action inside a local action outside .github/actions",
            ),
            pytest.param(
                "./ci/my-action",
                {"ci/my-action/action.yaml": "runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@v4\n"},
                [],
                id="an allowed action inside a local action named action.yaml",
            ),
            pytest.param(
                "./ci/loop",
                {"ci/loop/action.yml": "runs:\n  using: composite\n  steps:\n    - uses: ./ci/loop\n"},
                [],
                id="a local action naming itself is read once",
            ),
            pytest.param(
                "./ci/missing",
                {},
                [(".github/workflows/ci.yml", 5, "./ci/missing", "does not exist")],
                id="a local action that does not exist",
            ),
            pytest.param(
                "./ci/empty",
                {"ci/empty/README.md": "no definition here"},
                [(".github/workflows/ci.yml", 5, "./ci/empty", "no action.yml or action.yaml")],
                id="a local directory with no action definition",
            ),
            pytest.param(
                "./../outside",
                {},
                [(".github/workflows/ci.yml", 5, "./../outside", "outside the repository")],
                id="a local reference leaving the repository",
            ),
        ],
    )
    def test_follows_local_references_to_their_definitions(
        self, tmp_path: Path, reference: str, action_files: dict[str, str], expected: list[tuple[str, int, str, str]]
    ) -> None:
        """GitHub runs a `./` action from anywhere in the repository and applies the policy to the actions it uses, so the guard reads it too."""
        workflow = f"jobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n      - uses: {reference}\n"
        root = tmp_path / "repo"
        _write_tree(root=root, workflows={"ci.yml": workflow})
        for relative_path, content in action_files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        violations = collect_violations(root=root)
        assert [(violation.relative_path, violation.lineno, violation.reference) for violation in violations] == [
            (relative_path, lineno, found) for relative_path, lineno, found, _detail in expected
        ]
        for violation, (_relative_path, _lineno, _found, detail) in zip(violations, expected, strict=True):
            assert detail in violation.detail

    def test_reads_only_the_files_github_reads(self, tmp_path: Path) -> None:
        """Workflows directly under `.github/workflows/` and action definitions under `.github/actions/`; nothing else."""
        _write_tree(root=tmp_path, workflows={"ci.yml": WORKFLOW, "notes.md": "not a workflow"})
        (tmp_path / ".github" / "workflows" / "nested").mkdir()
        (tmp_path / ".github" / "workflows" / "nested" / "ignored.yml").write_text(WORKFLOW, encoding="utf-8")
        (tmp_path / ".github" / "actions" / "local").mkdir(parents=True)
        (tmp_path / ".github" / "actions" / "local" / "action.yml").write_text(COMPOSITE_ACTION, encoding="utf-8")
        scanned = [path.relative_to(tmp_path).as_posix() for path in iter_workflow_files(root=tmp_path)]
        assert scanned == [".github/workflows/ci.yml", ".github/actions/local/action.yml"]

    def test_refuses_to_pass_having_checked_nothing(self, tmp_path: Path) -> None:
        _write_tree(root=tmp_path, workflows={"empty.yml": "name: Empty\non: push\njobs: {}\n"})
        with pytest.raises(ActionsAllowlistGuardError, match="checked nothing"):
            collect_violations(root=tmp_path)

    def test_the_committed_allowlist_refuses_the_action_that_stopped_a_release(self) -> None:
        allowlist = load_allowlist(path=_REPO_ROOT / ALLOWLIST_FILE)
        assert refusal_reason(reference=REFUSED_ACTION, allowlist=allowlist) is not None

    def test_the_repository_reads_its_release_workflows_and_passes(self) -> None:
        """The release workflows, which pull-request CI never runs, are among the files read, and every workflow passes."""
        scanned = {path.relative_to(_REPO_ROOT).as_posix() for path in iter_workflow_files(root=_REPO_ROOT)}
        assert {".github/workflows/publish-pypi.yml", ".github/workflows/publish-docker-hub.yml"} <= scanned
        assert collect_violations(root=_REPO_ROOT) == []
