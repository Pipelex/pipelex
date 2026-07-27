"""Importing the Pipelex runtime loads zero interpreter modules — the property, not the rule.

`pipelex-dev check-hub-layering` guards the *rule* (no runtime-layer module imports `pipelex.interpreter_hub`).
This guards the *property* the rule exists to buy: importing the inference layer, or the runtime hub
itself, must pull in zero interpreter modules. The distinction matters because a stray import somewhere
else entirely — a runtime-layer module reaching into `pipe_operators` directly, without touching a hub —
would break the property while the lint stays green.

"Interpreter module" is spelled out twice below, because the interpreter top-level packages alone
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

#: Entry points that must never load the interpreter: the inference layer, the runtime hub itself, the
#: built-in plugin aggregator, and the heaviest module of each runtime-layer `core/` package — the ones
#: that historically reached for a library and now take a `ConceptProviderAbstract` instead. `core/`'s
#: Pipe-touching remainder is deliberately absent; it names the interpreter's own object and belongs to
#: the interpreter layer by construction (see the guard's `RUNTIME_LAYER_PACKAGES` note).
#:
#: `plugins.builtins` earns its place by history: it and three neighbours reached `interpreter_hub`
#: transitively — through `runtime_bridge`, `pipeline` and `pipe_operators` — while both gates stayed
#: green, because the guard was one hop deep and `pipelex.plugins`, the largest declared runtime-layer
#: package, had no entry point here. The guard now follows the import graph, but that is *static*
#: analysis: it cannot see a dynamic import, so the package that bit us gets a runtime-truth check too.
#: It is the aggregator of every built-in runtime-layer plugin, hence the broadest single entry point
#: into the package.
RUNTIME_LAYER_ENTRY_POINTS = [
    "pipelex.cogt.content_generation.content_generator",
    "pipelex.runtime_hub",
    "pipelex.plugins.builtins",
    "pipelex.core.concepts.structure_generation.generator",
    "pipelex.core.memory.input_shaper",
    "pipelex.core.memory.working_memory_factory",
    "pipelex.core.pipes.inputs.input_stuff_specs_factory",
    "pipelex.core.pipes.stuff_spec.stuff_spec_factory",
    "pipelex.core.stuffs.stuff_factory",
]

#: The negative control, and the reason it is needed: the detector below is a `textwrap.dedent`
#: string, so nothing type-checks or lints the names inside it. A typo in `INTERPRETER_PACKAGES` or
#: `is_interpreter` would make every entry point above pass *vacuously*, forever, and the suite would
#: stay green while guarding nothing. This entry point is dirty by definition — the interpreter hub
#: is the interpreter — so it must come back a failure, *reported as offending modules*, whatever
#: else changes. Asserting the offender message and not merely the exit code is what pins the
#: predicate: the `sys.modules` check below would exit 1 for this entry point either way.
DIRTY_ENTRY_POINT = "pipelex.interpreter_hub"

#: Wall-clock bound on one closure subprocess. Each case spawns a fresh interpreter importing heavy
#: modules; without a bound, a deadlock presents as a hung suite rather than a failure, which this
#: repo has a documented history of (`docs/agents/debugging-hanging-pytest-runs.md`).
SUBPROCESS_TIMEOUT_SECONDS = 300

_CLOSURE_SCRIPT = textwrap.dedent(
    """
    import importlib
    import sys

    target = sys.argv[1]
    importlib.import_module(target)

    INTERPRETER_PACKAGES = (
        "libraries",
        "pipe_operators",
        "pipe_controllers",
        "codegen",
        "builder",
        # The built-ins that adapt interpreter-layer ports; they construct interpreter-layer objects.
        "interpreter_plugins",
        # The pipe-kind registration manifest, hoisted out of `core/`.
        "pipe_machinery",
        # Signature resolution: `signature_walk` imports `interpreter_hub` to resolve pipes by code.
        "pipe_signature",
    )

    # Core's Pipe machinery: interpreter-layer by construction, but not under a top-level package of its own.
    INTERPRETER_CORE = (
        "pipelex.core.bundles",
        "pipelex.core.interpreter",
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


def _run_closure(*, entry_point: str) -> subprocess.CompletedProcess[str]:
    """Import one entry point in a fresh interpreter and return the detector's verdict."""
    try:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c", _CLOSURE_SCRIPT, entry_point],
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        message = f"the closure subprocess for {entry_point} did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s"
        raise AssertionError(message) from exc


class TestHubImportClosure:
    @pytest.mark.parametrize(
        ("entry_point", "expected_returncode"),
        [
            *((entry_point, 0) for entry_point in RUNTIME_LAYER_ENTRY_POINTS),
            # The negative control: same detector, opposite verdict. See DIRTY_ENTRY_POINT above.
            (DIRTY_ENTRY_POINT, 1),
        ],
    )
    def test_closure_verdict_for_entry_point(self, entry_point: str, expected_returncode: int) -> None:
        result = _run_closure(entry_point=entry_point)
        assert result.returncode == expected_returncode, (
            f"unexpected hub import-closure verdict for {entry_point} (wanted exit {expected_returncode}).\n"
            "Exit 0 means the entry point loaded no interpreter module; exit 1 means the detector found one. "
            "A runtime-layer entry point failing is a real breach — see docs/contribute/hub-layering.md for how "
            "to find the shortest import path to an offender. The dirty entry point passing instead means the "
            "detector has stopped detecting, and every other case above is now vacuous.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        if expected_returncode == 0:
            assert "closure OK" in result.stdout
        else:
            assert "closure OK" not in result.stdout
            assert "interpreter module(s)" in result.stdout
