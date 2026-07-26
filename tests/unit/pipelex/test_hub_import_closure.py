"""The low layer must load without the method interpreter — the property, not the rule.

`pipelex-dev check-hub-layering` guards the *rule* (no low-layer module imports `pipelex.method_hub`).
This guards the *property* the rule exists to buy: importing the inference layer, or the low hub
itself, must pull in zero `libraries` / `pipe_operators` / `pipe_controllers` / `codegen` / `builder`
modules. The distinction matters because a stray import somewhere else entirely — a low-layer module
reaching into `pipe_operators` directly, without touching a hub — would break the property while the
lint stays green.

Run in a subprocess so the closure is exactly what the entry point pulls in: an in-process
`sys.modules` check would see everything the test session already imported.
"""

from __future__ import annotations

import subprocess  # noqa: S404
import sys
import textwrap

import pytest

#: Entry points that must never load the interpreter: the inference layer, the low hub itself, and the
#: heaviest module of each low-layer `core/` package — the ones that historically reached for a library
#: and now take a `ConceptProviderAbstract` instead. `core/`'s Pipe-touching remainder is deliberately
#: absent; it names the interpreter's own object and is high by construction (see the guard's
#: `LOW_LAYER_PACKAGES` note).
LOW_LAYER_ENTRY_POINTS = [
    "pipelex.cogt.content_generation.content_generator",
    "pipelex.service_hub",
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

    INTERPRETER = ("libraries", "pipe_operators", "pipe_controllers", "codegen", "builder")
    offenders = sorted(name for name in sys.modules if name.startswith("pipelex.") and name.split(".")[1] in INTERPRETER)
    if offenders:
        print(f"{target} loaded {len(offenders)} interpreter module(s): {offenders}")
        raise SystemExit(1)

    # The high hub must not be reachable from the low layer at all — the forbidden arrow, measured.
    if "pipelex.method_hub" in sys.modules:
        print(f"{target} loaded pipelex.method_hub")
        raise SystemExit(1)

    print("closure OK")
    """
)


class TestHubImportClosure:
    @pytest.mark.parametrize("entry_point", LOW_LAYER_ENTRY_POINTS)
    def test_entry_point_loads_no_interpreter_module(self, entry_point: str) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _CLOSURE_SCRIPT, entry_point],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"hub import-closure guard failed for {entry_point}.\n"
            "The low layer must load without the method interpreter — see docs/contribute/hub-layering.md "
            "for how to find the shortest import path to an offender.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "closure OK" in result.stdout
