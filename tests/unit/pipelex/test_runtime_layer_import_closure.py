"""Importing the Pipelex runtime loads zero interpreter modules — the property, not the rule.

`pipelex-dev check-hub-layering` guards the *rule* (no runtime-layer module imports `pipelex.interpreter_hub`).
This guards the *property* the rule exists to buy: importing the inference layer, or the runtime hub
itself, must pull in zero interpreter modules. The distinction matters because a stray import somewhere
else entirely — a runtime-layer module reaching into `pipe_operators` directly, without touching a hub —
would break the property while the lint stays green.

"Interpreter module" is spelled out twice below, because the five interpreter top-level packages alone
under-state it: core's Pipe-machinery modules are interpreter-layer too, and most of them only get
caught *transitively*, through the `pipe_operators` / `libraries` they happen to pull in.
`core.pipes.pipe_blueprint` pulls in none of it, so a runtime-layer import of it would pass a
package-only predicate. Naming them makes the predicate state the boundary instead of approximating it.

Two documented interpreter homes are deliberately absent, and their absence is a known wart rather than
an oversight: `pipeline` and `pipe_run` (plus `core.bundles.exceptions`) already leak leaf models into
every runtime closure — `SpecialPipelineId`, `PipeRunMode`, the bundle validation-error data. Naming
them here would fail the test over a *placement* problem, not a broken hub arrow. See
`wip/pr-1062-review-notes.md`.

Run in a subprocess so the closure is exactly what the entry point pulls in: an in-process
`sys.modules` check would see everything the test session already imported.
"""

from __future__ import annotations

import subprocess  # noqa: S404
import sys
import textwrap

import pytest

#: Entry points that must never load the interpreter: the inference layer, the runtime hub itself, and the
#: heaviest module of each runtime-layer `core/` package — the ones that historically reached for a library
#: and now take a `ConceptProviderAbstract` instead. `core/`'s Pipe-touching remainder is deliberately
#: absent; it names the interpreter's own object and belongs to the interpreter layer by construction (see
#: the guard's `RUNTIME_LAYER_PACKAGES` note).
RUNTIME_LAYER_ENTRY_POINTS = [
    "pipelex.cogt.content_generation.content_generator",
    "pipelex.runtime_hub",
    "pipelex.core.concepts.structure_generation.generator",
    "pipelex.core.memory.input_shaper",
    "pipelex.core.memory.working_memory_factory",
    "pipelex.core.pipes.inputs.input_stuff_specs_factory",
    "pipelex.core.pipes.stuff_spec.stuff_spec_factory",
    "pipelex.core.stuffs.stuff_factory",
]

_CLOSURE_SCRIPT = textwrap.dedent(
    """
    import importlib
    import sys

    target = sys.argv[1]
    importlib.import_module(target)

    INTERPRETER_PACKAGES = ("libraries", "pipe_operators", "pipe_controllers", "codegen", "builder")

    # Core's Pipe machinery: interpreter-layer by construction, but not under a top-level package of its own.
    INTERPRETER_CORE = (
        "pipelex.core.bundles",
        "pipelex.core.interpreter",
        "pipelex.core.registry_models",
        "pipelex.core.pipes.pipe_abstract",
        "pipelex.core.pipes.pipe_blueprint",
        "pipelex.core.pipes.pipe_factory",
        "pipelex.core.pipes.rendering",
    )
    # The one straddler: structured bundle validation-error data that `pipeline/` imports, so it lands in
    # every runtime closure -- dragging the empty `core.bundles` package placeholder in with it. A placement
    # wart, not a hub violation -- see wip/pr-1062-review-notes.md. Matched exactly, never as a prefix, so
    # the rest of `core.bundles` stays flagged.
    INTERPRETER_CORE_EXCLUDED = ("pipelex.core.bundles", "pipelex.core.bundles.exceptions")

    def is_interpreter(name):
        if name.split(".")[1] in INTERPRETER_PACKAGES:
            return True
        if name in INTERPRETER_CORE_EXCLUDED:
            return False
        return any(name == module or name.startswith(module + ".") for module in INTERPRETER_CORE)

    offenders = sorted(name for name in sys.modules if name.startswith("pipelex.") and is_interpreter(name))
    if offenders:
        print(f"{target} loaded {len(offenders)} interpreter module(s): {offenders}")
        raise SystemExit(1)

    # The interpreter hub must not be reachable from the runtime layer at all — the forbidden arrow, measured.
    if "pipelex.interpreter_hub" in sys.modules:
        print(f"{target} loaded pipelex.interpreter_hub")
        raise SystemExit(1)

    print("closure OK")
    """
)


class TestHubImportClosure:
    @pytest.mark.parametrize("entry_point", RUNTIME_LAYER_ENTRY_POINTS)
    def test_entry_point_loads_no_interpreter_module(self, entry_point: str) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _CLOSURE_SCRIPT, entry_point],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"hub import-closure guard failed for {entry_point}.\n"
            "The runtime layer must load without the method interpreter — see docs/contribute/hub-layering.md "
            "for how to find the shortest import path to an offender.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "closure OK" in result.stdout
