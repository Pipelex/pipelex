# `Concept` is a subclass of the MTHDS-protocol wire model `ConceptAbstract` — pure serializable data.
# It used to answer behavioral questions ("are these two compatible?", "what is this concept's class?") by
# reaching into the process-global class registry, which made a standard-owned wire model depend on a
# Pipelex process-global and made the same two values answer differently depending on which async context
# asked. `refactor/Concept-purity` moved every one of those reads out: reading the registry is a
# `ConceptProviderAbstract` implementation's job, and `core/` states that dependency as a parameter.
#
# What is left inside `pipelex/core/concepts/` is the **write side** — materializing generated structure
# classes at library-load time and registering them. That is genuinely the registry's business and stays,
# so the property is not "no module here touches the registry" but "exactly these two do".
#
# Pinned as a golden set rather than as a rule, for the reason the `cogt` boundary test gives: there is no
# predicate separating the sanctioned write-side reads from a new read-side one, and a golden set needs
# none — it turns the third module into a diff a reviewer sees. Nothing else can see this: both the
# accessor and its users are kernel-layer, so the hub-layering guard is blind to the edge by construction.

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Anchored on `tests/` by name rather than by a parent count — a depth index resolves silently to the
#: wrong directory when a module moves, and this repo has been bitten by exactly that.
_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_REPO_ROOT = _TESTS_ROOT.parent
_CONCEPTS_DIR = _REPO_ROOT / "pipelex" / "core" / "concepts"

#: The module that hosts the accessor, below both hubs. Importing it *at all* is registry access —
#: it exports nothing else. `pipelex.runtime_hub` is deliberately NOT listed: it re-exports the
#: accessor among many unrelated ones, so the module is not the signal, the name and the call are.
_ACCESSOR_MODULE = "pipelex.system.registries.class_registry_access"
_ACCESSOR_NAME = "get_class_registry"

#: Reaching the registry without naming the accessor. `KajsonManager.get_class_registry()` returns the
#: process-global registry directly, bypassing library scoping entirely — there is a live precedent for
#: it at `runtime_bridge/primitives/rehydration.py`. `ClassRegistryUtils` calls the accessor internally,
#: so importing it is reaching the registry by proxy. An import-name-only walk misses both, which would
#: make this a check on one import spelling rather than on the property it claims to pin.
_INDIRECT_ACCESS_ROOTS = ("KajsonManager", "ClassRegistryUtils")

#: The materialization write side: the only two modules under `pipelex/core/concepts/` that may touch the
#: class registry. `concept_factory` registers generated structure classes and decides whether one already
#: exists; `structure_generation/generator.py` looks up base classes to generate against. Both run at
#: library-load time, on the way to *producing* a class rather than resolving one for a concept.
#:
#: A new entry here is a read-side leak until proven otherwise — the thing this branch removed. Resolving a
#: concept's declared `structure_class_name` belongs on a `ConceptProviderAbstract` implementation
#: (`ConceptLibrary.get_structure_class`), which is what every reader now calls.
EXPECTED_REGISTRY_USERS: frozenset[str] = frozenset(
    {
        "pipelex/core/concepts/concept_factory.py",
        "pipelex/core/concepts/structure_generation/generator.py",
    }
)

CONCEPT_MODULE_PATHS: list[Path] = sorted(_CONCEPTS_DIR.rglob("*.py"))


def _reaches_the_class_registry(*, module_path: Path) -> bool:
    """Whether a module reaches the class registry at all — by import, by module path, or by proxy.

    Deliberately wider than "imports `get_class_registry` by name". A check that only matched the
    import name would pass a module doing `import pipelex.runtime_hub` followed by
    `pipelex.runtime_hub.get_class_registry()`, or one calling `KajsonManager.get_class_registry()`
    (which skips library scoping outright), and this is the gate that is supposed to catch a read-side
    leak growing back — so it matches the attribute call and the two indirect roots as well.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == _ACCESSOR_MODULE for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == _ACCESSOR_MODULE:
                return True
            if any(alias.name == _ACCESSOR_NAME or alias.name in _INDIRECT_ACCESS_ROOTS for alias in node.names):
                return True
        elif isinstance(node, ast.Attribute) and node.attr == _ACCESSOR_NAME:
            # `pipelex.runtime_hub.get_class_registry()` / `KajsonManager.get_class_registry()` —
            # the call reaches the registry whether or not the name was imported.
            return True
    return False


class TestConceptRegistryBoundary:
    def test_only_the_materialization_write_side_touches_the_class_registry(self) -> None:
        """`pipelex/core/concepts/**` reaches the class registry from exactly the two write-side modules."""
        # Anti-vacuity: an empty walk would make the assertion below pass for free.
        assert CONCEPT_MODULE_PATHS, f"no Python module found under {_CONCEPTS_DIR} — this check measures nothing"

        actual = {
            module_path.relative_to(_REPO_ROOT).as_posix()
            for module_path in CONCEPT_MODULE_PATHS
            if _reaches_the_class_registry(module_path=module_path)
        }

        assert actual == EXPECTED_REGISTRY_USERS, (
            "which modules under `pipelex/core/concepts/` touch the class registry changed.\n"
            f"  added:   {sorted(actual - EXPECTED_REGISTRY_USERS)}\n"
            f"  removed: {sorted(EXPECTED_REGISTRY_USERS - actual)}\n"
            "An added module is a DEFECT unless it materializes classes: resolving a concept's declared "
            "`structure_class_name` belongs on a ConceptProviderAbstract implementation "
            "(`ConceptLibrary.get_structure_class`), not on an ambient registry read — that coupling is what "
            "`refactor/Concept-purity` removed from the protocol-owned `Concept` wire model. "
            "See docs/contribute/hub-layering.md, 'Injected providers, not ambient lookups'."
        )

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("from pipelex.system.registries.class_registry_access import get_class_registry", True),
            ("from pipelex.runtime_hub import get_class_registry", True),
            ("import pipelex.system.registries.class_registry_access", True),
            ("from pipelex.runtime_hub import get_console, get_class_registry", True),
            # The spellings an import-name-only walk would wave through.
            ("def f():\n    return pipelex.runtime_hub.get_class_registry()", True),
            ("from kajson.kajson_manager import KajsonManager", True),
            ("def f():\n    return KajsonManager.get_class_registry()", True),
            ("from pipelex.system.registries.class_registry_utils import ClassRegistryUtils", True),
            ("from pipelex.runtime_hub import get_console", False),
            ("from pipelex.core.stuffs.stuff_content import StuffContent", False),
        ],
    )
    def test_every_way_of_reaching_the_registry_is_detected(self, source: str, expected: bool, tmp_path: Path) -> None:
        """Import name, module path, attribute call, and the two indirect roots all count."""
        module_path = tmp_path / "probe.py"
        module_path.write_text(source, encoding="utf-8")
        assert _reaches_the_class_registry(module_path=module_path) is expected
