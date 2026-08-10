"""Unit tests for the hub-layering guard's transitive rule — the one that follows the import graph.

The other two rules are per-file and see one hop, which is exactly how the breach that motivated this
rule stayed invisible: four modules of the declared kernel-layer `pipelex.plugins` package reached
`interpreter_hub` through `runtime_bridge`, `pipeline` and `pipe_operators`, and both gates stayed
green. So the tests here are about the *graph*: which edges exist, which do not, and which of the
modules that reach the hub are the guard's business.

Each case is a miniature repo on disk rather than a snippet, because the rule is inherently
cross-file — a snippet has no second module to reach through.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    HubLayeringGuardError,
    HubLayeringViolationKind,
    build_import_graph,
    collect_transitive_violations,
    shortest_import_path,
)

INTERPRETER_HUB = "pipelex.interpreter_hub"

#: One hop short of the hub: a legal module, in no declared layer, that does import it.
INTERMEDIARY_SOURCE = "from pipelex.interpreter_hub import get_pipe_router\n\n\nclass DirectOrchestrator:\n    pass\n"


def _write(*, path: Path, source: str) -> None:
    """Write one module, creating its directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _make_tree(root: Path) -> None:
    """A miniature repo holding one instance of every case the rule must get right.

    `cogt/` is a declared kernel-layer package; `runtime_bridge/` and `pipeline/` are in no declared
    layer, so they may reach the hub freely — which is precisely what makes them usable as
    intermediaries.
    """
    _write(path=root / "pipelex" / "interpreter_hub.py", source="def get_pipe_router():\n    return None\n")
    _write(path=root / "pipelex" / "runtime_hub.py", source="def get_console():\n    return None\n")
    _write(path=root / "pipelex" / "runtime_bridge" / "orchestrator.py", source=INTERMEDIARY_SOURCE)

    # The canonical breach: kernel-layer module -> legal intermediary -> the hub.
    _write(
        path=root / "pipelex" / "cogt" / "breach.py",
        source="from pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n",
    )
    # An aggregator: carries no edge to the hub of its own, breaches only by importing the breacher.
    _write(path=root / "pipelex" / "cogt" / "aggregator.py", source="from pipelex.cogt.breach import DirectOrchestrator\n")
    # Clean: the runtime hub is the whole point, and it leads nowhere near the interpreter.
    _write(path=root / "pipelex" / "cogt" / "clean.py", source="from pipelex.runtime_hub import get_console\n")
    # Legal: `pipeline` is in no declared layer, so reaching the hub is not this rule's business.
    _write(path=root / "pipelex" / "pipeline" / "runner.py", source="from pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n")


class TestHubLayeringTransitiveRule:
    def test_reports_exactly_the_kernel_layer_modules_that_reach_the_hub(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The breacher and its aggregator, with the chain that explains each — and nothing else.

        `pipeline/runner.py` reaches the hub by the same edge and is correctly silent: it sits in no
        declared layer. `cogt/clean.py` is the negative control for the walk itself.
        """
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        assert [(violation.relative_path, violation.kind, violation.detail) for violation in violations] == [
            (
                "pipelex/cogt/aggregator.py",
                HubLayeringViolationKind.INTERPRETER_HUB_TRANSITIVE,
                f"reaches `{INTERPRETER_HUB}` via pipelex.cogt.breach → pipelex.runtime_bridge.orchestrator → {INTERPRETER_HUB}",
            ),
            (
                "pipelex/cogt/breach.py",
                HubLayeringViolationKind.INTERPRETER_HUB_TRANSITIVE,
                f"reaches `{INTERPRETER_HUB}` via pipelex.runtime_bridge.orchestrator → {INTERPRETER_HUB}",
            ),
        ]

    def test_the_reported_line_is_the_first_hop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A violation must point at the import the author can act on, not at the file's first line."""
        _make_tree(tmp_path)
        _write(
            path=tmp_path / "pipelex" / "cogt" / "breach.py",
            source="from pipelex.runtime_hub import get_console\n\nfrom pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n",
        )
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))
        breach = next(violation for violation in violations if violation.relative_path == "pipelex/cogt/breach.py")

        assert breach.lineno == 3

    def test_a_direct_import_is_left_to_the_one_hop_rule(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Double-reporting the same import under two remedies would be noise, not coverage."""
        _make_tree(tmp_path)
        _write(path=tmp_path / "pipelex" / "cogt" / "direct.py", source="from pipelex.interpreter_hub import get_pipe_router\n")
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        assert "pipelex/cogt/direct.py" not in [violation.relative_path for violation in violations]

    @pytest.mark.parametrize(
        ("case", "source"),
        [
            (
                "type_checking",
                "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n",
            ),
            (
                "function_body",
                "def make():\n    from pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n\n    return DirectOrchestrator\n",
            ),
            (
                "async_function_body",
                "async def make():\n    from pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n\n    return DirectOrchestrator\n",
            ),
        ],
    )
    def test_an_edge_that_does_not_load_is_not_an_edge(self, case: str, source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The rule measures the import *closure*, so a type-only or deferred import creates no path.

        This is the same carve-out the one-hop layer rule grants a `TYPE_CHECKING` block, applied to
        the graph — and it is what keeps the sanctioned deferral pattern (`pipe_func_executor_registry`)
        from reading as a breach.
        """
        _make_tree(tmp_path)
        _write(path=tmp_path / "pipelex" / "cogt" / f"{case}.py", source=source)
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        assert f"pipelex/cogt/{case}.py" not in [violation.relative_path for violation in violations]

    def test_a_relative_import_is_the_same_edge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Relative spellings resolve against the importing package, so the chain cannot be spelled around."""
        _make_tree(tmp_path)
        _write(path=tmp_path / "pipelex" / "cogt" / "relative.py", source="from ..runtime_bridge.orchestrator import DirectOrchestrator\n")
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        assert "pipelex/cogt/relative.py" in [violation.relative_path for violation in violations]

    def test_an_imported_symbol_resolves_to_the_module_that_holds_it(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`from pkg.mod import Symbol` is an edge to `pkg.mod`: the candidate walks up until it names a real module."""
        _make_tree(tmp_path)
        monkeypatch.chdir(tmp_path)

        graph = build_import_graph(root=Path("pipelex"))

        assert set(graph.edges["pipelex.cogt.breach"]) == {"pipelex.runtime_bridge.orchestrator"}

    def test_the_reported_chain_is_the_shortest_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With two routes to the hub, the short one explains the breach; the scenic one buries it."""
        _make_tree(tmp_path)
        _write(path=tmp_path / "pipelex" / "cogt" / "detour.py", source="from pipelex.cogt.breach import DirectOrchestrator\n")
        _write(
            path=tmp_path / "pipelex" / "cogt" / "aggregator.py",
            source="from pipelex.cogt.breach import DirectOrchestrator\nfrom pipelex.cogt.detour import DirectOrchestrator as Detoured\n",
        )
        monkeypatch.chdir(tmp_path)

        graph = build_import_graph(root=Path("pipelex"))

        assert shortest_import_path(graph=graph, start="pipelex.cogt.aggregator", target=INTERPRETER_HUB) == [
            "pipelex.cogt.aggregator",
            "pipelex.cogt.breach",
            "pipelex.runtime_bridge.orchestrator",
            INTERPRETER_HUB,
        ]

    def test_a_clean_tree_reports_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The shape production is in — worth pinning, since a rule that never fires must still be able to."""
        _make_tree(tmp_path)
        _write(path=tmp_path / "pipelex" / "cogt" / "breach.py", source="from pipelex.runtime_hub import get_console\n")
        _write(path=tmp_path / "pipelex" / "cogt" / "aggregator.py", source="from pipelex.cogt.breach import get_console\n")
        monkeypatch.chdir(tmp_path)

        assert collect_transitive_violations(root=Path("pipelex")) == []

    def test_a_package_init_on_the_way_is_an_edge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Importing `pkg.mod` runs `pkg/__init__.py` first, so a breach in the init is reached through it.

        Modelling only the literal import target would make this whole class of breach invisible: the
        importer names a clean leaf module and never mentions the package that actually loads the hub.
        """
        _make_tree(tmp_path)
        _write(path=tmp_path / "pipelex" / "pipeline" / "__init__.py", source=INTERMEDIARY_SOURCE)
        _write(path=tmp_path / "pipelex" / "pipeline" / "runner.py", source="def run():\n    return None\n")
        _write(path=tmp_path / "pipelex" / "cogt" / "sneaky.py", source="from pipelex.pipeline.runner import run\n")
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        sneaky = next(violation for violation in violations if violation.relative_path == "pipelex/cogt/sneaky.py")
        assert sneaky.detail == f"reaches `{INTERPRETER_HUB}` via pipelex.pipeline → {INTERPRETER_HUB}"

    def test_a_suppressed_import_is_not_an_edge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The escape hatch marks one reviewed import, and rule 3 must read it the same way rule 1 does.

        Ignoring it here would keep the edge while the finding it explains disappears — silently
        exempting the suppressing module from this rule, and flagging its importers in its place.
        """
        _make_tree(tmp_path)
        _write(
            path=tmp_path / "pipelex" / "cogt" / "suppressed.py",
            source="from pipelex.interpreter_hub import get_pipe_router  # hub-layering: ignore\n",
        )
        _write(path=tmp_path / "pipelex" / "cogt" / "importer.py", source="from pipelex.cogt.suppressed import get_pipe_router\n")
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        assert "pipelex/cogt/importer.py" not in [violation.relative_path for violation in violations]

    def test_a_suppressed_direct_import_does_not_hide_a_longer_chain(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Suppressing one import must not exempt the module from the rest of the graph.

        The module below carries a sanctioned direct import *and* a real transitive route. Leaving the
        suppressed edge in the graph would make the shortest chain one hop, which this rule skips as
        rule 1's business — so the genuine longer route would go unreported.
        """
        _make_tree(tmp_path)
        _write(
            path=tmp_path / "pipelex" / "cogt" / "both.py",
            source=(
                "from pipelex.interpreter_hub import get_pipe_router  # hub-layering: ignore\n"
                "from pipelex.runtime_bridge.orchestrator import DirectOrchestrator\n"
            ),
        )
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        both = next(violation for violation in violations if violation.relative_path == "pipelex/cogt/both.py")
        assert both.lineno == 2
        assert both.detail == f"reaches `{INTERPRETER_HUB}` via pipelex.runtime_bridge.orchestrator → {INTERPRETER_HUB}"

    def test_a_dynamic_import_in_an_intermediary_is_an_edge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A module-level `import_module("pipelex.interpreter_hub")` loads the hub, so it is an edge.

        Rule 1 catches that string in a kernel-layer module; the gap this closes is the same string
        in an intermediary, which sits in no declared layer. Both hub references that actually
        occurred in this repo were strings, not imports.
        """
        _make_tree(tmp_path)
        _write(
            path=tmp_path / "pipelex" / "runtime_bridge" / "dynamic.py",
            source='import importlib\n\nhub = importlib.import_module("pipelex.interpreter_hub")\n',
        )
        _write(path=tmp_path / "pipelex" / "cogt" / "via_dynamic.py", source="from pipelex.runtime_bridge.dynamic import hub\n")
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        breach = next(violation for violation in violations if violation.relative_path == "pipelex/cogt/via_dynamic.py")
        assert breach.detail == f"reaches `{INTERPRETER_HUB}` via pipelex.runtime_bridge.dynamic → {INTERPRETER_HUB}"

    def test_a_deferred_dynamic_import_is_not_an_edge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inside a function it loads nothing at import time — the same carve-out a deferred `import` gets."""
        _make_tree(tmp_path)
        _write(
            path=tmp_path / "pipelex" / "runtime_bridge" / "deferred.py",
            source='import importlib\n\n\ndef get_hub():\n    return importlib.import_module("pipelex.interpreter_hub")\n',
        )
        _write(path=tmp_path / "pipelex" / "cogt" / "via_deferred.py", source="from pipelex.runtime_bridge.deferred import get_hub\n")
        monkeypatch.chdir(tmp_path)

        violations = collect_transitive_violations(root=Path("pipelex"))

        assert "pipelex/cogt/via_deferred.py" not in [violation.relative_path for violation in violations]

    def test_a_scan_that_cannot_see_the_hub_fails_instead_of_passing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A detector that has stopped detecting must fail, not report zero.

        Reverse reachability from a module the graph does not contain is empty by construction, so a
        renamed hub — or a scan root the module names cannot be derived from — would otherwise turn
        the whole rule into a no-op while the gate stayed green.
        """
        _make_tree(tmp_path)
        (tmp_path / "pipelex" / "interpreter_hub.py").rename(tmp_path / "pipelex" / "interpreter_hub_renamed.py")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(HubLayeringGuardError, match=re.escape("found no `pipelex.interpreter_hub`")):
            collect_transitive_violations(root=Path("pipelex"))

    def test_an_absolute_scan_root_fails_instead_of_checking_nothing(self, tmp_path: Path) -> None:
        """Module names are derived from the scanned path verbatim, so only a repo-relative root works.

        An absolute root yields qnames like `tmp.…\u200b.pipelex.cogt.breach`, which match no `pipelex`
        candidate: the graph comes back with no edges and the rule would pass having checked nothing.
        """
        _make_tree(tmp_path)

        with pytest.raises(HubLayeringGuardError, match="scan root"):
            collect_transitive_violations(root=tmp_path / "pipelex")
