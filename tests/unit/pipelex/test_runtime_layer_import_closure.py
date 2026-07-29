"""Importing the Pipelex runtime loads zero interpreter modules — the property, not the rule.

`pipelex-dev check-hub-layering` guards the *rule* (no runtime-layer module imports `pipelex.interpreter_hub`).
This guards the *property* the rule exists to buy: importing the inference layer, or the runtime hub
itself, must pull in zero interpreter modules. The distinction matters because a stray import somewhere
else entirely — a runtime-layer module reaching into `pipe_operators` directly, without touching a hub —
would break the property while the lint stays green.

"Interpreter module" used to need spelling out twice, because core's Pipe-machinery modules were
interpreter-layer while living under a runtime-named package — so the predicate carried a second tuple
naming them one by one, plus an exclusion for the one leaf model that landed in every runtime closure.
It does not any more: every one of those modules now lives under `pipe_machinery` or `mthds_parsing`,
so the top-level package set says exactly what it means, with no per-module list and no exclusion. A
package-granular predicate is only honest once the packages match the layers, which is what M1 bought.

The set below now names every interpreter package, with no exclusion and no qualification. `pipeline`
and `pipe_run` were the last two absent, and their absence was a *placement* problem rather than a
broken hub arrow: four leaf models of theirs landed in every runtime closure, so naming them here
would have failed every entry point over an address. The remedy was the one `mthds_parsing` used —
move the leaves to a runtime-layer home, then widen the predicate. `SpecialPipelineId` is now in
`system.job_metadata` beside the `pipeline_run_id` it names, `PipeRunMode` and `PipeRunParamKey` are
`system.pipe_run_mode` / `system.pipe_run_param_key`, and `PipeRunError` sits in
`core.pipes.exceptions` with the runtime-layer subclasses that derive from it. Moving the leaf is
what buys the clean predicate; excluding it would only have recorded the problem.

Run in a subprocess so the closure is exactly what the entry point pulls in: an in-process
`sys.modules` check would see everything the test session already imported.
"""

from __future__ import annotations

import ast
import re
import subprocess  # noqa: S404
import sys
import textwrap
from pathlib import Path

import pytest

#: Entry points that must never load the interpreter: the inference layer, the runtime hub itself, the
#: built-in plugin aggregator, and the heaviest module of each runtime-layer `core/` package — the ones
#: that historically reached for a library and now take a `ConceptProviderAbstract` instead. There is no
#: longer a Pipe-touching remainder of `core/` to leave out: all of it moved to `pipe_machinery` and
#: `mthds_parsing`, which is what let `pipelex.core` be declared wholesale (see the guard's
#: `RUNTIME_LAYER_PACKAGES` note).
#:
#: `providers.builtins` earns its place by history, under its former name `plugins.builtins`: it and
#: three neighbours reached `interpreter_hub` transitively — through `runtime_bridge`, `pipeline` and
#: `pipe_operators` — while both gates stayed green, because the guard was one hop deep and
#: `pipelex.plugins`, the largest declared runtime-layer package, had no entry point here. The guard
#: now follows the import graph, but that is *static* analysis: it cannot see a dynamic import, so the
#: package that bit us gets a runtime-truth check too. It instantiates every built-in vendor adapter,
#: so importing it pulls in every one of them — the broadest single entry point into `pipelex.providers`,
#: which is where those adapters now live. The plugin *mechanism* it registers through stayed behind
#: in `pipelex.plugins` and is reached from here, so one entry point still covers both halves.
RUNTIME_LAYER_ENTRY_POINTS = [
    "pipelex.cogt.content_generation.content_generator",
    "pipelex.runtime_hub",
    "pipelex.providers.builtins",
    "pipelex.core.concepts.structure_generation.generator",
    "pipelex.core.memory.input_shaper",
    "pipelex.core.memory.working_memory_factory",
    "pipelex.core.pipes.inputs.input_stuff_specs_factory",
    "pipelex.core.pipes.stuff_spec.stuff_spec_factory",
    "pipelex.core.stuffs.stuff_factory",
]

#: The negative control, and the reason it is needed: the detector below is a `textwrap.dedent`
#: string, so nothing type-checks or lints the *logic* inside it. The package names are no longer at
#: risk — they are a real module-level constant, passed in as argv — but a broken predicate or a
#: mis-built offenders comprehension would still make every entry point above pass *vacuously*,
#: forever, while the suite stayed green. This entry point is dirty by definition — the interpreter
#: hub is the interpreter — so it must come back a failure, *reported as offending modules*, whatever
#: else changes. Asserting the offender message and not merely the exit code is what pins the
#: predicate: the `sys.modules` check below would exit 1 for this entry point either way.
DIRTY_ENTRY_POINT = "pipelex.interpreter_hub"

#: Wall-clock bound on one closure subprocess. Each case spawns a fresh interpreter importing heavy
#: modules; without a bound, a deadlock presents as a hung suite rather than a failure, which this
#: repo has a documented history of (`docs/agents/debugging-hanging-pytest-runs.md`).
SUBPROCESS_TIMEOUT_SECONDS = 300

#: The interpreter layer's top-level packages — the set the detector treats as "interpreter module".
#:
#: A real module-level constant, handed to the subprocess as argv rather than baked into the script
#: string below. That is deliberate: while these names lived *inside* the `textwrap.dedent` string,
#: nothing type-checked, linted or grepped them, and reading them back out took a regex. The set is
#: complete — every interpreter package is named — which is what makes the property unqualified;
#: see this module's docstring for the two that were absent longest and why.
INTERPRETER_PACKAGES: tuple[str, ...] = (
    "libraries",
    "pipe_operators",
    "pipe_controllers",
    "codegen",
    "builder",
    # The built-ins that adapt interpreter-layer ports; they construct interpreter-layer objects.
    "interpreter_plugins",
    # Core's Pipe machinery and the pipe-kind registration manifest, hoisted out of `core/`.
    "pipe_machinery",
    # Signature resolution: `signature_walk` imports `interpreter_hub` to resolve pipes by code.
    "pipe_signature",
    # The MTHDS parser and its blueprint, hoisted out of `core/`.
    "mthds_parsing",
    # The two interpreter homes the predicate could not name until their leaf models moved out.
    "pipeline",
    "pipe_run",
)

_CLOSURE_SCRIPT = textwrap.dedent(
    """
    import importlib
    import sys

    target = sys.argv[1]
    interpreter_packages = frozenset(sys.argv[2:])
    # An empty set would make every entry point pass while flagging nothing — the exact vacuity this
    # module exists to prevent. Fail loudly instead, so a caller that drops the argv splat is caught.
    if not interpreter_packages:
        print("no interpreter packages passed — the detector would match nothing")
        raise SystemExit(2)
    importlib.import_module(target)

    def is_interpreter(name):
        return name.split(".")[1] in interpreter_packages

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


#: Anchored on `tests/` by name rather than by a parent count — a depth index resolves silently to the
#: wrong directory when a module moves, which is exactly the failure this whole track kept hitting.
_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_REPO_ROOT = _TESTS_ROOT.parent
_HUB_LAYERING_PAGE = _REPO_ROOT / "docs" / "contribute" / "hub-layering.md"


def _run_closure(*, entry_point: str) -> subprocess.CompletedProcess[str]:
    """Import one entry point in a fresh interpreter and return the detector's verdict."""
    try:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c", _CLOSURE_SCRIPT, entry_point, *INTERPRETER_PACKAGES],
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

    def test_every_configured_interpreter_package_is_real(self) -> None:
        """Each name in `INTERPRETER_PACKAGES` is a real top-level package under `pipelex/`.

        `DIRTY_ENTRY_POINT` proves that *at least one* configured name matches — it imports the
        interpreter hub, whose closure contains several of them. It cannot prove that each one does.
        A typo'd or retired name matches nothing and guards nothing, forever, while the suite stays
        green; and since the predicate is a membership test, a dead name is invisible rather than loud.
        Being a real constant makes the names lint-visible, but no tool checks a string against disk.
        """
        source_root = _REPO_ROOT / "pipelex"
        for package in INTERPRETER_PACKAGES:
            assert (source_root / package).is_dir(), (
                f"INTERPRETER_PACKAGES names {package!r}, which is not a package directory under "
                f"{source_root}. The predicate is a membership test, so this name silently matches "
                f"nothing rather than failing — every module it was meant to flag now passes."
            )

    def test_the_interpreter_package_set_matches_the_documented_one(self) -> None:
        """The closure predicate and `hub-layering.md`'s verification snippet name the same packages.

        The page publishes a runnable snippet with its own copy of this set, and a reader who runs it
        with a stale copy measures zero interpreter modules and believes it. The two copies had in fact
        silently disagreed on `pipe_signature` before anyone compared them by machine.
        """
        page = _HUB_LAYERING_PAGE.read_text(encoding="utf-8")
        match = re.search(r"^INTERPRETER = (\{.*\})$", page, re.MULTILINE)
        assert match is not None, f"could not locate the INTERPRETER set in {_HUB_LAYERING_PAGE}"
        documented = set(ast.literal_eval(match.group(1)))
        configured = set(INTERPRETER_PACKAGES)
        assert configured == documented, (
            f"the closure predicate and {_HUB_LAYERING_PAGE.name} disagree on the interpreter packages.\n"
            f"  only in the closure test: {sorted(configured - documented)}\n"
            f"  only in the doc snippet:  {sorted(documented - configured)}\n"
            "Both must gain a new interpreter package together, or one of the two checks passes vacuously."
        )
