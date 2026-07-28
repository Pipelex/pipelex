# The img-gen taxonomy mapping modules are the neutral home the vendor img-gen factories moved into,
# and neutrality is the whole reason the move happened: their dispatch key is `AspectRatioTaxonomy`, a
# `cogt`-owned enum that names model families and no providers, and no family is served by a single
# adapter (the `openai` and `azure_openai` decks both ship GPT Image models; the gateway worker
# resolves Gemini geometry through the same mapping the native Google worker uses).
# Nothing else in the repo can catch a regression here: `pipelex.cogt` and
# `pipelex.providers` are BOTH runtime-layer, so the hub-layering guard and the import-closure test are
# blind to an edge between them by construction — see docs/contribute/hub-layering.md, "Known inversions".
#
# Two complementary checks, because the coupling can come back by two routes. The direct one is a fresh
# `from openai import omit` in the module's own source (which is what the GPT mapping carried before the
# move); the transitive one is an innocuous-looking `pipelex.cogt.*` import that drags an adapter in
# behind it. The first check reads the source, the second measures the import closure.

from __future__ import annotations

import ast
import subprocess  # noqa: S404
import sys
import textwrap
from pathlib import Path

import pytest

#: Anchored on `tests/` by name rather than by a parent count — a depth index resolves silently to the
#: wrong directory when a module moves, and this repo has been bitten by exactly that.
_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_MAPPING_DIR = _TESTS_ROOT.parent / "pipelex" / "cogt" / "img_gen"

#: Derived from disk rather than listed, so a third taxonomy family is covered the day it lands.
#:
#: A glob that stops matching is the failure mode that buys, and it is guarded in exactly one place —
#: the non-parametrized test below. It cannot be guarded in the parametrized one: pytest never calls a
#: test body for an empty parameter set, it reports `SKIPPED [1] got empty parameter set` and exits 0,
#: so an assertion at the top of that body is unreachable by construction. Both lists derive from this
#: one glob, so the single reachable check covers the module.
MAPPING_MODULE_PATHS: list[Path] = sorted(_MAPPING_DIR.glob("img_gen_*_mapping.py"))

MAPPING_MODULE_QNAMES: list[str] = [f"pipelex.cogt.img_gen.{path.stem}" for path in MAPPING_MODULE_PATHS]

#: Wall-clock bound on the closure subprocess, so a deadlock presents as a failure rather than a hung suite.
SUBPROCESS_TIMEOUT_SECONDS = 300

_CLOSURE_SCRIPT = textwrap.dedent(
    """
    import importlib
    import sys

    for target in sys.argv[1:]:
        importlib.import_module(target)

    offenders = sorted(name for name in sys.modules if name.startswith("pipelex.providers"))
    if offenders:
        print(f"the img-gen mapping modules loaded {len(offenders)} provider adapter module(s): {offenders}")
        raise SystemExit(1)

    print("closure OK")
    """
)


def _import_roots(*, module_path: Path) -> set[str]:
    """The top-level package of every import statement in a module, module-level and deferred alike."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class TestImgGenMappingNeutrality:
    @pytest.mark.parametrize("module_path", MAPPING_MODULE_PATHS, ids=lambda path: path.stem)
    def test_mapping_module_imports_only_pipelex_and_stdlib(self, module_path: Path) -> None:
        """A mapping table has no business importing a vendor SDK: every import root is stdlib or `pipelex`."""
        offenders = sorted(root for root in _import_roots(module_path=module_path) if root != "pipelex" and root not in sys.stdlib_module_names)

        assert not offenders, (
            f"{module_path.name} imports third-party package(s) {offenders}. These modules map a `cogt`-owned "
            "taxonomy enum onto provider wire values and are consumed by several adapters at once, so they must "
            "stay free of any provider SDK — that is what the F1 move bought. If a mapping genuinely needs a "
            "third-party type, the value belongs on the adapter side of the boundary, not here."
        )

    def test_mapping_modules_load_no_provider_adapter(self) -> None:
        """Importing every mapping module in a fresh interpreter pulls in zero `pipelex.providers` modules."""
        # The module's one reachable anti-vacuity guard — see the note on MAPPING_MODULE_PATHS. Both this
        # check and its parametrized sibling would otherwise measure nothing if the glob stopped matching.
        assert MAPPING_MODULE_QNAMES, f"no img_gen_*_mapping.py found under {_MAPPING_DIR} — this check measures nothing"

        try:
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-c", _CLOSURE_SCRIPT, *MAPPING_MODULE_QNAMES],
                capture_output=True,
                text=True,
                check=False,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            message = f"the closure subprocess did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s"
            raise AssertionError(message) from exc

        assert result.returncode == 0, (
            "an img-gen mapping module reached a provider adapter. The dependency runs the other way: adapters "
            "import inward to these mappings, never the reverse. Neither the hub-layering guard nor the "
            "import-closure test can see this edge — both packages are runtime-layer.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
