"""Unit tests for the filesystem surface of the hub-layering guard.

`find_violations_in_source` is exercised from inline snippets in `test_hub_layering_guard.py`, where
every path is a synthetic string. These pin the layer that actually walks a tree: which files get
picked up, which get skipped, and how a path becomes the module qname that decides layer membership.
A mistake here is invisible to a snippet test and silently shrinks what the guard covers — a skipped
directory, a stale `__pycache__` copy scanned as if it were source, or an `__init__.py` resolving to
the wrong package and so falling out of its own layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    HubLayeringViolationKind,
    collect_all_violations,
    iter_source_files,
    module_qname_for,
)

#: The deleted single hub. This line *declares* the dead path as test data rather than referencing
#: it, so it carries the guard's own escape hatch — without it, the guard flags its own test suite.
DEAD_HUB = "pipelex.hub"  # hub-layering: ignore

INTERPRETER_HUB_IMPORT = "from pipelex.interpreter_hub import get_pipe_router\n"
RUNTIME_HUB_IMPORT = "from pipelex.runtime_hub import get_console\n"
DEAD_HUB_PATCH = f'mocker.patch("{DEAD_HUB}.get_console")\n'


def _make_tree(root: Path) -> None:
    """A miniature repo covering every branch the walk has to get right.

    `cogt/` is a declared kernel-layer package, so its breach is a violation; `pipeline/` is not, so
    the identical import there is legal and must stay unreported; `__pycache__` holds a stale copy of
    the offender; and `tests/` is scanned for the dead-module rule only.
    """
    sample = root / "pipelex" / "cogt" / "sample"
    sample.mkdir(parents=True)
    (sample / "__init__.py").write_text("", encoding="utf-8")
    (sample / "clean.py").write_text(RUNTIME_HUB_IMPORT, encoding="utf-8")
    (sample / "worker.py").write_text(INTERPRETER_HUB_IMPORT, encoding="utf-8")
    cache = sample / "__pycache__"
    cache.mkdir()
    (cache / "worker.py").write_text(INTERPRETER_HUB_IMPORT, encoding="utf-8")

    pipeline = root / "pipelex" / "pipeline"
    pipeline.mkdir(parents=True)
    (pipeline / "runner.py").write_text(INTERPRETER_HUB_IMPORT, encoding="utf-8")

    tests_root = root / "tests"
    tests_root.mkdir()
    (tests_root / "helper.py").write_text(DEAD_HUB_PATCH, encoding="utf-8")


class TestHubLayeringGuardFilesystem:
    def test_full_scan_reports_exactly_the_real_offenders(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both roots are walked, both rules applied, and layer membership decided per file.

        Mirrors production, where the scan runs against the *relative* `SCAN_ROOTS`, so reported
        paths are repo-root-relative.
        """
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)

        violations = collect_all_violations(roots=(Path("pipelex"), Path("tests")))

        assert [(violation.relative_path, violation.kind) for violation in violations] == [
            ("pipelex/cogt/sample/worker.py", HubLayeringViolationKind.INTERPRETER_HUB_IMPORT),
            ("tests/helper.py", HubLayeringViolationKind.DEAD_HUB_REFERENCE),
        ]

    def test_pycache_is_never_walked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stale compiled-source copy is not source: scanning it would report a phantom file."""
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)

        paths = [path.as_posix() for path in iter_source_files(root=Path("pipelex"))]

        assert paths == [
            "pipelex/cogt/sample/__init__.py",
            "pipelex/cogt/sample/clean.py",
            "pipelex/cogt/sample/worker.py",
            "pipelex/pipeline/runner.py",
        ]

    def test_a_kernel_layer_package_init_is_inside_its_own_layer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`__init__`-stripping is load-bearing: without it `pipelex/cogt/__init__.py` would resolve to
        `pipelex.cogt.__init__`, still match the layer by prefix — but a top-level `pipelex/__init__.py`
        would resolve to `pipelex.__init__` and land in no layer at all. Pin the package form end to end.
        """
        cogt = tmp_path / "pipelex" / "cogt"
        cogt.mkdir(parents=True)
        (cogt / "__init__.py").write_text(INTERPRETER_HUB_IMPORT, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        violations = collect_all_violations(roots=(Path("pipelex"),))

        assert [violation.kind for violation in violations] == [HubLayeringViolationKind.INTERPRETER_HUB_IMPORT]
        assert violations[0].relative_path == "pipelex/cogt/__init__.py"

    @pytest.mark.parametrize(
        ("relative_path", "expected_qname"),
        [
            ("pipelex/cogt/sample/worker.py", "pipelex.cogt.sample.worker"),
            ("pipelex/cogt/sample/__init__.py", "pipelex.cogt.sample"),
            ("pipelex/__init__.py", "pipelex"),
            ("tests/helper.py", "tests.helper"),
        ],
    )
    def test_module_qname_for(self, relative_path: str, expected_qname: str) -> None:
        """A package's `__init__.py` is the package itself, not a submodule named `__init__`."""
        assert module_qname_for(path=Path(relative_path)) == expected_qname
