"""A kernel-only boot never imports an interpreter-group plugin's module — proven against a real
installed distribution.

`test_plugin_group_split.py` asks the same question with `importlib.metadata.entry_points` patched.
That is the right tool for the *branching* (which groups get queried, which menu calls are refused),
but a patched metadata API cannot answer the question this module exists for: the claim is about
what the real discovery machinery does with real installed metadata, and every interesting part of
that path — `entry_points(group=…)` reading `entry_points.txt`, `EntryPoint.load()` importing a
module by name — is exactly the part the patch replaces. A green test there is compatible with a
`build_registrar` that mishandles real metadata.

So this one synthesizes an actual distribution on disk (`*.dist-info/` with `entry_points.txt`),
puts it on `sys.path`, and observes whether the plugin's module body ran. It runs in a
**subprocess** because the observable is a *first* import: once anything in the pytest process has
imported the module, the body never runs again and the assertion would pass vacuously forever after.

The kernel-only arm is the property. The both-groups arm is the vacuity guard, and it is not
optional: a fixture that no boot can discover — a typo in the group, an unreadable `dist-info`, a
`sys.path` that never took — makes the kernel-only arm pass for the wrong reason and look identical
to success.
"""

from __future__ import annotations

import os
import subprocess  # noqa: S404
import sys
import textwrap
from typing import TYPE_CHECKING

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.plugin_group import PluginGroup

if TYPE_CHECKING:
    from pathlib import Path

#: Wall-clock bound on the discovery subprocess, matching the other subprocess harnesses: a boot that
#: deadlocks must present as a failure, not as a hung suite
#: (`docs/agents/debugging-hanging-pytest-runs.md`).
SUBPROCESS_TIMEOUT_SECONDS = 300

#: The synthetic distribution's import name, entry-point name, and dist name. Distinct from each
#: other on purpose: discovery denylists by entry-point name *before* `load()` and by plugin `.name`
#: after, so a fixture that spelled all three the same could hide a mix-up between them.
_MODULE_NAME = "synthetic_interpreter_plugin"
_ENTRY_POINT_NAME = "synthetic-interpreter"
_DIST_NAME = "synthetic-interpreter-plugin"

#: Importing this module writes the sentinel. A file rather than an in-process flag because the
#: question is asked across a process boundary, and it records *module-body execution* — the thing
#: that actually drags an interpreter-layer dependency chain into the process — rather than the
#: weaker "the name appeared in `sys.modules`".
_PLUGIN_SOURCE = textwrap.dedent(
    f"""
    import os
    import pathlib

    pathlib.Path(os.environ["PLUGIN_IMPORT_SENTINEL"]).write_text("imported", encoding="utf-8")


    class SyntheticInterpreterPlugin:
        name = "{_ENTRY_POINT_NAME}"
        targets_api = {PLUGIN_API_VERSION}

        def register(self, registrar):
            # Contributes nothing: this fixture exists to be imported or not imported, and a real
            # contribution would drag the menu-tier cross-check into an unrelated assertion.
            pass
    """
)

_DISCOVERY_SCRIPT = textwrap.dedent(
    """
    import pathlib
    import sys
    from types import SimpleNamespace

    site_dir, sentinel_path, entry_point_name = sys.argv[1:4]
    sys.path.insert(0, site_dir)
    sentinel = pathlib.Path(sentinel_path)

    from pipelex.plugins.discovery import build_registrar
    from pipelex.plugins.plugin_group import PluginGroup

    def discover(groups):
        return build_registrar(
            config=SimpleNamespace(plugins=SimpleNamespace(disabled=[])),
            builtin_plugins=[],
            core_unconditional_plugin_names=frozenset(),
            entry_point_groups=groups,
        )

    kernel_only = discover((PluginGroup.KERNEL,))
    if sentinel.exists():
        print("a kernel-only boot imported the interpreter-group plugin's module")
        raise SystemExit(2)
    if [discovery.name for discovery in kernel_only.discoveries]:
        print(f"a kernel-only boot discovered: {kernel_only.discoveries}")
        raise SystemExit(3)

    both = discover((PluginGroup.KERNEL, PluginGroup.INTERPRETER))
    if not sentinel.exists():
        print("the fixture is inert: a both-groups boot did not import it either")
        raise SystemExit(4)
    if [discovery.name for discovery in both.discoveries] != [entry_point_name]:
        print(f"a both-groups boot did not register the plugin: {both.discoveries}")
        raise SystemExit(5)

    print("group isolation OK")
    """
)


class TestInstalledPluginGroupIsolation:
    def test_a_kernel_only_boot_never_imports_an_installed_interpreter_group_plugin(self, tmp_path: Path) -> None:
        """Not discovered, not loaded, module body never run — against real installed metadata."""
        site_dir = tmp_path / "site"
        site_dir.mkdir()
        (site_dir / f"{_MODULE_NAME}.py").write_text(_PLUGIN_SOURCE, encoding="utf-8")

        dist_info = site_dir / f"{_DIST_NAME.replace('-', '_')}-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {_DIST_NAME}\nVersion: 1.0\n",
            encoding="utf-8",
        )
        (dist_info / "entry_points.txt").write_text(
            f"[{PluginGroup.INTERPRETER}]\n{_ENTRY_POINT_NAME} = {_MODULE_NAME}:SyntheticInterpreterPlugin\n",
            encoding="utf-8",
        )

        sentinel = tmp_path / "imported.sentinel"
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _DISCOVERY_SCRIPT, str(site_dir), str(sentinel), _ENTRY_POINT_NAME],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PLUGIN_IMPORT_SENTINEL": str(sentinel)},
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )

        assert result.returncode == 0, f"group isolation failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "group isolation OK" in result.stdout
