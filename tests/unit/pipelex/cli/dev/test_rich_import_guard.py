from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipelex.cli.dev_cli.commands.rich_import_guard import (
    SOURCE_ROOT,
    RichImportGuardError,
    collect_violations,
    find_violations_in_source,
)

#: Anchored on `tests/` by name rather than by a parent count, for the reason `test_hub_layering_guard.py` gives.
_REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

SERVER_PATH = "pipelex/core/stuffs/sample_content.py"
CLI_PATH = "pipelex/cli/commands/sample_cmd.py"


def _lines(source: str, *, relative_path: str = SERVER_PATH) -> list[int]:
    """The lines the guard flags in an inline snippet."""
    return [violation.lineno for violation in find_violations_in_source(source=textwrap.dedent(source), relative_path=relative_path)]


class TestRichImportGuard:
    @pytest.mark.parametrize(
        ("topic", "source", "expected_lines"),
        [
            ("from-import at the top", "from rich.console import Console\n", [1]),
            ("plain import", "import rich\n", [1]),
            ("submodule import with alias", "import rich.table as table\n", [1]),
            ("package-level from-import", "from rich import box\n", [1]),
            ("module-level try block", "try:\n    from rich.text import Text\nexcept ImportError:\n    Text = None\n", [2]),
            ("class body", "class Renderer:\n    from rich.panel import Panel\n", [2]),
            ("else branch of TYPE_CHECKING", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\nelse:\n    import rich\n", [5]),
            ("negated TYPE_CHECKING", "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    import rich\n", [3]),
            ("guarded function body", "def render():\n    require_rich_for_rendering()\n    from rich.text import Text\n    return Text()\n", []),
            ("guarded coroutine body", "async def render():\n    require_rich_for_rendering()\n    import rich\n", []),
            (
                "guarded method body",
                (
                    "class Content:\n"
                    "    def rendered_pretty(self):\n"
                    "        require_rich_for_rendering()\n"
                    "        from rich.json import JSON\n"
                    "        return JSON('{}')\n"
                ),
                [],
            ),
            ("TYPE_CHECKING block", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from rich.console import Console\n", []),
            ("typing.TYPE_CHECKING block", "import typing\nif typing.TYPE_CHECKING:\n    from rich.console import Console\n", []),
            ("a package merely named like Rich", "import richer\nfrom rich_extra import thing\n", []),
            ("a relative import", "from .rich import thing\n", []),
            ("pipelex's own rich_extra module", "from pipelex.tools.misc.rich_extra import require_rich\n", []),
        ],
    )
    def test_flags_exactly_the_imports_that_run_at_module_import(self, topic: str, source: str, expected_lines: list[int]) -> None:
        """What counts is whether importing the module executes the import, wherever the statement sits."""
        assert _lines(source) == expected_lines, topic

    def test_the_cli_package_may_import_rich_at_module_level(self) -> None:
        """The CLI installs the `cli` extra, so a CLI module's module-level Rich import is not a violation."""
        assert _lines("from rich.console import Console\n", relative_path=CLI_PATH) == []
        # The allowlist is a package prefix, not a name fragment.
        assert _lines("from rich.console import Console\n", relative_path="pipelex/client/sample.py") == [1]

    def test_the_real_tree_is_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The source tree as committed: no module outside `pipelex/cli/` imports Rich at module level."""
        monkeypatch.chdir(_REPO_ROOT)
        assert collect_violations(root=SOURCE_ROOT) == []

    def test_a_module_reaching_rich_through_a_cli_module_is_refused_with_its_chain(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The transitive rule: importing a CLI module that imports Rich loads Rich, however many hops away."""
        tree = {
            "pipelex/__init__.py": "",
            "pipelex/cli/__init__.py": "",
            "pipelex/cli/panels.py": "from rich.panel import Panel\n",
            "pipelex/cli/uses_panels.py": "from pipelex.cli.panels import Panel\n",
            "pipelex/cli/plain.py": "PLAIN = 1\n",
            "pipelex/core/__init__.py": "",
            "pipelex/core/direct.py": '"""Reaches a CLI module that imports Rich."""\n\nfrom pipelex.cli.panels import Panel\n',
            "pipelex/core/indirect.py": "import pipelex.core.direct\n",
            "pipelex/core/via_cli.py": "from pipelex.cli import uses_panels\n",
            "pipelex/core/plain_cli.py": "from pipelex.cli.plain import PLAIN\n",
            "pipelex/core/deferred.py": "def render():\n    from pipelex.cli.panels import Panel\n    return Panel\n",
            "pipelex/core/type_only.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pipelex.cli.panels import Panel\n",
            "pipelex/core/own_rich.py": "import rich\n",
            "pipelex/core/imports_own_rich.py": "from pipelex.core.own_rich import rich\n",
        }
        for relative_path, source in tree.items():
            path = tmp_path / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        found = {(violation.relative_path, violation.lineno, violation.detail) for violation in collect_violations(root=SOURCE_ROOT)}

        assert found == {
            ("pipelex/core/direct.py", 3, "reaches Rich via pipelex.cli.panels, which imports it at module level"),
            ("pipelex/core/indirect.py", 1, "reaches Rich via pipelex.core.direct → pipelex.cli.panels, which imports it at module level"),
            ("pipelex/core/via_cli.py", 1, "reaches Rich via pipelex.cli.uses_panels → pipelex.cli.panels, which imports it at module level"),
            # A module outside the CLI that imports Rich itself is the direct rule's finding, and only that.
            ("pipelex/core/own_rich.py", 1, "imports `rich` at module level"),
        }

    def test_a_root_the_allowlist_cannot_match_fails_loudly(self, tmp_path: Path) -> None:
        """An absolute or empty root would make the allowlist match nothing and the verdict meaningless."""
        (tmp_path / "module.py").write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(RichImportGuardError, match="allowlist matched nothing"):
            collect_violations(root=tmp_path)


class TestDeferredRichImportGuard:
    """The ordering rule: a deferred Rich import is reached only after something established Rich is installed.

    Deferring the import is what keeps Rich off a server's import path; calling the guard first is what turns a
    bare `ModuleNotFoundError` into the `MissingDependencyError` that names the extra. The direct rule checks
    the first and cannot see the second, so this is a rule of its own.
    """

    @pytest.mark.parametrize(
        ("topic", "source", "expected_lines"),
        [
            ("no guard at all", "def render():\n    from rich.text import Text\n    return Text()\n", [2]),
            ("guard on the line before", "def render():\n    require_rich(message='x')\n    from rich.text import Text\n", []),
            ("the rendering guard", "def render():\n    require_rich_for_rendering()\n    from rich.text import Text\n", []),
            ("a console hands out a guarded object", "def render():\n    console = get_console()\n    from rich.table import Table\n", []),
            ("guard after the import does not reach it", "def render():\n    from rich.text import Text\n    require_rich(message='x')\n", [2]),
            (
                "a guard inside a branch does not cover the function",
                "def render(flat):\n    from rich.markup import escape\n    if flat:\n        console = get_console()\n",
                [2],
            ),
            (
                "a top-level guard covers an import inside a branch",
                "def render(flat):\n    require_rich(message='x')\n    if flat:\n        from rich.text import Text\n",
                [],
            ),
            (
                "a guard beside the import in the same branch covers it",
                "def render(missing):\n    if missing:\n        console = get_console()\n        from rich.panel import Panel\n",
                [],
            ),
            (
                "a guard in one branch does not cover the other",
                "def render(missing):\n    if missing:\n        require_rich(message='x')\n    else:\n        from rich.panel import Panel\n",
                [5],
            ),
            (
                "a fallback asks sys.modules rather than raising",
                "def render(content):\n    if 'rich' not in sys.modules:\n        return None\n    from rich.text import Text\n",
                [],
            ),
            (
                "a nested function is its own scope",
                "def outer():\n    require_rich(message='x')\n\n    def inner():\n        from rich.text import Text\n",
                [5],
            ),
            ("a coroutine is checked the same way", "async def render():\n    import rich.box\n", [2]),
            (
                "a method is checked the same way",
                "class Content:\n    def rendered_pretty(self):\n        from rich.json import JSON\n",
                [3],
            ),
            ("a type-only import inside a function needs no guard", "def render():\n    if TYPE_CHECKING:\n        from rich.text import Text\n", []),
        ],
    )
    def test_a_deferred_import_is_flagged_unless_a_guard_precedes_it(self, topic: str, source: str, expected_lines: list[int]) -> None:
        assert _lines(source) == expected_lines, topic

    def test_the_cli_package_needs_no_guard_before_a_deferred_import(self) -> None:
        """A CLI module may import Rich at the top of the file, so deferring one inside a function asks nothing of it."""
        assert _lines("def render():\n    from rich.text import Text\n", relative_path=CLI_PATH) == []

    def test_the_remedy_names_the_guard_a_reader_has_to_call(self) -> None:
        """The report is what a developer acts on, so it names the call rather than describing the problem."""
        violations = find_violations_in_source(source="def render():\n    from rich.text import Text\n", relative_path=SERVER_PATH)
        assert len(violations) == 1
        assert "require_rich" in violations[0].detail
