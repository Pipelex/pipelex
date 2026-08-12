# `pipelex.cogt` is the vendor-neutral inference engine: it owns the taxonomies, the worker protocols and
# the model registry, and it is the kernel-layer half you can embed without the MTHDS interpreter. Two
# facts make that neutrality real rather than aspirational, and neither is visible to any other gate:
#
#   1. `cogt` imports no vendor SDK. Its third-party surface is framework and infrastructure only.
#   2. `cogt → pipelex.providers` is a short, deliberate, documented list — the four config classes the main
#      config model needs statically typed, plus one deferred VertexAI factory import.
#
# Both are pinned below as golden sets rather than as rules, because both are *accepted inversions*: the
# engine naming four vendors is a placement wart the M2 review weighed and kept (a plugin-contributed config
# section would trade compile-time typing for a dynamic registry), so there is no predicate that separates
# the sanctioned edges from a new one. A golden set needs none — it turns the sixth edge into a diff a
# reviewer sees, which is exactly what happened by hand three times during the modularity track.
#
# Why nothing else can see this: `pipelex.cogt` and `pipelex.providers` are BOTH kernel-layer, so the
# hub-layering guard and the import-closure test are blind to an edge between them by construction. See
# docs/contribute/hub-layering.md, "Known inversions", which documents the same list in prose.
#
# A repo-wide "no vendor SDK outside `pipelex/providers/`" check is the tempting generalization and it is
# WRONG — it would be red on day one. `tools/pdf/pypdfium2_renderer.py`, `tools/storage/`, `tracing/` and
# `reporting/` all import infrastructure SDKs (pypdfium2, boto3/botocore, google.cloud) on purpose:
# `providers/storage/` is a registration shim whose implementations live under `pipelex/tools/`. The scope
# that is true is this one.

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

#: Anchored on `tests/` by name rather than by a parent count — a depth index resolves silently to the
#: wrong directory when a module moves, and this repo has been bitten by exactly that.
_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_REPO_ROOT = _TESTS_ROOT.parent
_COGT_DIR = _REPO_ROOT / "pipelex" / "cogt"

_PROVIDERS_PREFIX = "pipelex.providers"

#: How an import reaches the interpreter. Recorded in the pinned rows because promoting a deferred import to
#: module level is a real change — it is what puts the target in every closure that touches the module.
MODULE_LEVEL = "module-level"
DEFERRED = "deferred"
TYPE_CHECKING_ONLY = "type-checking"


class ImportSite(NamedTuple):
    """One import statement, addressed by source file and fully-resolved target rather than by line number."""

    source: str
    target: str
    form: str

    def render(self) -> str:
        return f"{self.source} -> {self.target} [{self.form}]"


#: Every third-party import root reachable from `pipelex/cogt/**`, in any form. Framework and infrastructure
#: only — no inference-provider SDK appears here, and that is the point: adding one is how the img-gen
#: coupling F1 removed would grow back. Adding a genuinely new framework dependency is a one-line update to
#: this set; adding a vendor SDK is a defect, and the two must not be told apart by whoever runs the test.
EXPECTED_THIRD_PARTY_ROOTS: frozenset[str] = frozenset(
    {
        "PIL",
        "datamodel_code_generator",
        "httpx",
        "instructor",
        "opentelemetry",
        "polyfactory",
        "pydantic",
        "rich",
        "tenacity",
        "typing_extensions",
    }
)

#: Every `cogt → pipelex.providers` import statement. Documented in prose in docs/contribute/hub-layering.md
#: under "Known inversions" — the four config classes are accepted (D-M2-2), the VertexAI factory import is
#: deferred inside a function and self-resolves when VertexAI support is removed.
EXPECTED_PROVIDER_EDGES: frozenset[str] = frozenset(
    {
        f"pipelex/cogt/config_cogt.py -> {_PROVIDERS_PREFIX}.anthropic.anthropic_config [{MODULE_LEVEL}]",
        f"pipelex/cogt/config_cogt.py -> {_PROVIDERS_PREFIX}.google.google_config [{MODULE_LEVEL}]",
        f"pipelex/cogt/config_cogt.py -> {_PROVIDERS_PREFIX}.mistral.mistral_config [{MODULE_LEVEL}]",
        f"pipelex/cogt/config_cogt.py -> {_PROVIDERS_PREFIX}.openai.openai_config [{MODULE_LEVEL}]",
        f"pipelex/cogt/model_backends/backend_factory.py -> {_PROVIDERS_PREFIX}.openai.vertexai_factory [{DEFERRED}]",
    }
)


def _tests_type_checking(*, test: ast.expr) -> bool:
    """Whether an `if` guards its body on `TYPE_CHECKING`, under either import spelling."""
    match test:
        case ast.Name(id=name):
            return name == "TYPE_CHECKING"
        case ast.Attribute(attr=attr):
            return attr == "TYPE_CHECKING"
        case _:
            return False


def _collect_imports(*, node: ast.AST, form: str, collected: list[tuple[ast.Import | ast.ImportFrom, str]]) -> None:
    """Recurse the tree, carrying how the current statement would execute at import time."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        collected.append((node, form))
        return

    if isinstance(node, ast.If) and _tests_type_checking(test=node.test):
        # Only the guarded branch is type-only; the `else` is the runtime fallback optional deps use.
        for guarded_stmt in node.body:
            _collect_imports(node=guarded_stmt, form=TYPE_CHECKING_ONLY, collected=collected)
        for fallback_stmt in node.orelse:
            _collect_imports(node=fallback_stmt, form=form, collected=collected)
        return

    # A class body executes at import time, so only a function body defers.
    child_form = DEFERRED if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else form
    for child in ast.iter_child_nodes(node):
        _collect_imports(node=child, form=child_form, collected=collected)


def _resolve_imported_name(*, base_module: str, name: str) -> str:
    """`base_module.name` when that names a module of this repo, else `base_module` — the name was a symbol.

    `from pipelex import providers` and `from pipelex.providers.anthropic.anthropic_config import AnthropicConfig`
    are the same syntax carrying two different dependencies: the first is an edge on `pipelex.providers`, the
    second an edge on the module that defines the symbol. Resolving both to `base_module` lets a submodule
    import slip past the edge assertion; resolving both to `base_module.name` would grow every pinned row a
    symbol suffix and make a second import from an already-sanctioned module read as a brand-new edge.
    """
    candidate = _REPO_ROOT.joinpath(*base_module.split("."), name)
    return f"{base_module}.{name}" if candidate.is_dir() or candidate.with_suffix(".py").is_file() else base_module


def _import_targets(*, node: ast.Import | ast.ImportFrom, package_parts: tuple[str, ...]) -> list[str]:
    """The absolute dotted target(s) of an import, resolving relative forms against the importing package."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    if node.level == 0:
        base_module = node.module or ""
    else:
        # `from .x import y` in pipelex/cogt/llm/foo.py resolves against pipelex.cogt.llm; each extra dot climbs one.
        base = package_parts[: len(package_parts) - (node.level - 1)]
        parts = (*base, node.module) if node.module else base
        base_module = ".".join(parts)

    if not base_module:
        return []
    return sorted({_resolve_imported_name(base_module=base_module, name=alias.name) for alias in node.names})


def _import_sites(*, module_path: Path) -> list[ImportSite]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    relative_path = module_path.relative_to(_REPO_ROOT)
    package_parts = relative_path.parts[:-1]

    collected: list[tuple[ast.Import | ast.ImportFrom, str]] = []
    _collect_imports(node=tree, form=MODULE_LEVEL, collected=collected)

    sites: list[ImportSite] = []
    for node, form in collected:
        for target in _import_targets(node=node, package_parts=package_parts):
            sites.append(ImportSite(source=relative_path.as_posix(), target=target, form=form))
    return sites


COGT_MODULE_PATHS: list[Path] = sorted(_COGT_DIR.rglob("*.py"))

IMPORT_SITES: list[ImportSite] = sorted(site for module_path in COGT_MODULE_PATHS for site in _import_sites(module_path=module_path))


class TestCogtDependencyBoundaries:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            # The form the edge assertion used to miss entirely: the dependency is on the submodule,
            # but `from X import Y` records only `X`, so a `cogt -> providers` edge could land unseen.
            ("from pipelex import providers", ["pipelex.providers"]),
            ("from pipelex import providers as vendors", ["pipelex.providers"]),
            ("from .. import providers", ["pipelex.providers"]),
            # A symbol keeps its module as the target — resolving it would grow every pinned row a suffix,
            # and make a second import from an already-sanctioned module read as a brand-new edge.
            ("from pipelex.providers.anthropic.anthropic_config import AnthropicConfig", ["pipelex.providers.anthropic.anthropic_config"]),
            ("from pipelex import log", ["pipelex"]),
            ("from pydantic import BaseModel", ["pydantic"]),
            ("import pipelex.providers.openai.openai_config", ["pipelex.providers.openai.openai_config"]),
        ],
    )
    def test_import_target_resolves_a_submodule_but_not_a_symbol(self, source: str, expected: list[str]) -> None:
        """`from X import Y` names a submodule as often as a symbol, and only the first is a real edge."""
        node = ast.parse(source).body[0]
        assert isinstance(node, (ast.Import, ast.ImportFrom))
        assert _import_targets(node=node, package_parts=("pipelex", "cogt")) == expected

    def test_cogt_imports_no_vendor_sdk(self) -> None:
        """`pipelex/cogt/**` reaches exactly the pinned framework/infrastructure packages, and no vendor SDK."""
        # Anti-vacuity: both checks read one walk, and an empty walk would make both pass for free. This test
        # and its sibling are non-parametrized precisely so this line runs — pytest never calls the body of a
        # parametrized test with an empty parameter set, it reports `SKIPPED [1]` and exits 0.
        assert COGT_MODULE_PATHS, f"no Python module found under {_COGT_DIR} — this check measures nothing"

        actual_roots = {site.target.split(".")[0] for site in IMPORT_SITES}
        third_party_roots = {root for root in actual_roots if root != "pipelex" and root not in sys.stdlib_module_names}

        assert third_party_roots == EXPECTED_THIRD_PARTY_ROOTS, (
            "the third-party surface of `pipelex.cogt` changed.\n"
            f"  added:   {sorted(third_party_roots - EXPECTED_THIRD_PARTY_ROOTS)}\n"
            f"  removed: {sorted(EXPECTED_THIRD_PARTY_ROOTS - third_party_roots)}\n"
            "If the added root is an inference-provider SDK (openai, anthropic, google, mistralai, fal_client, "
            "portkey_ai, huggingface_hub, transformers, azure, vertexai, …), this is a DEFECT, not a golden-set "
            "update: `cogt` is the vendor-neutral engine, and the vendor-facing code belongs under "
            "`pipelex/providers/`, importing inward to `cogt`. That direction is what the F1 img-gen move bought. "
            "If it is a genuinely new framework or infrastructure dependency, update EXPECTED_THIRD_PARTY_ROOTS."
        )

    def test_cogt_to_providers_edges_are_the_documented_set(self) -> None:
        """The `cogt → pipelex.providers` edges are exactly the ones "Known inversions" documents."""
        assert COGT_MODULE_PATHS, f"no Python module found under {_COGT_DIR} — this check measures nothing"

        actual_edges = {site.render() for site in IMPORT_SITES if site.target == _PROVIDERS_PREFIX or site.target.startswith(f"{_PROVIDERS_PREFIX}.")}

        assert actual_edges == EXPECTED_PROVIDER_EDGES, (
            "the set of `cogt -> pipelex.providers` import statements changed.\n"
            f"  added:   {sorted(actual_edges - EXPECTED_PROVIDER_EDGES)}\n"
            f"  removed: {sorted(EXPECTED_PROVIDER_EDGES - actual_edges)}\n"
            "No other gate in this repo can see this: both packages are kernel-layer, so the hub-layering guard "
            "and the import-closure test are blind to an edge between them by construction. A NEW edge means the "
            "vendor-neutral engine grew a sixth reason to name a specific vendor — route it through "
            "`inference_backend_registry`, or move the code to the provider side and import inward, before "
            'pinning it here. A REMOVED edge is good news: drop the row, and update the "Known inversions" '
            "section of docs/contribute/hub-layering.md in the same change."
        )
