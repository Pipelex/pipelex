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
# accessor and its users are runtime-layer, so the hub-layering guard is blind to the edge by construction.

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Anchored on `tests/` by name rather than by a parent count — a depth index resolves silently to the
#: wrong directory when a module moves, and this repo has been bitten by exactly that.
_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_REPO_ROOT = _TESTS_ROOT.parent
_CONCEPTS_DIR = _REPO_ROOT / "pipelex" / "core" / "concepts"

#: The module that hosts the accessor, below both hubs. Matched alongside the accessor *name* so the
#: `pipelex.runtime_hub` re-export (the public spelling everywhere else) is caught by the same check.
_ACCESSOR_MODULE = "pipelex.system.registries.class_registry_access"
_ACCESSOR_NAME = "get_class_registry"

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
    """Whether a module names the class-registry accessor in any import, under either spelling.

    Both `from pipelex.system.registries.class_registry_access import get_class_registry` (the form used
    inside `runtime_hub`'s own import closure) and `from pipelex.runtime_hub import get_class_registry`
    (the public accessor) count: they are the same dependency reached two ways.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == _ACCESSOR_MODULE for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == _ACCESSOR_MODULE:
                return True
            if any(alias.name == _ACCESSOR_NAME for alias in node.names):
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
            (f"from {_ACCESSOR_MODULE} import {_ACCESSOR_NAME}", True),
            (f"from pipelex.runtime_hub import {_ACCESSOR_NAME}", True),
            (f"import {_ACCESSOR_MODULE}", True),
            (f"from pipelex.runtime_hub import get_console, {_ACCESSOR_NAME}", True),
            ("from pipelex.runtime_hub import get_console", False),
            ("from pipelex.core.stuffs.stuff_content import StuffContent", False),
        ],
    )
    def test_both_accessor_spellings_are_detected(self, source: str, expected: bool, tmp_path: Path) -> None:
        """The public `runtime_hub` re-export is the same dependency as the below-both-hubs module."""
        module_path = tmp_path / "probe.py"
        module_path.write_text(source, encoding="utf-8")
        assert _reaches_the_class_registry(module_path=module_path) is expected
