"""Booting the runtime layer loads zero interpreter modules — the boot-time half of the property.

`pipelex-dev check-hub-layering` proves no runtime-layer *module* imports `interpreter_hub`, and
`test_runtime_layer_import_closure.py` proves the declared runtime-layer entry points *import* clean.
Neither says anything about *booting*: until `RuntimeBoot` existed, the only composition root in the
tree built an `InterpreterHub`, a `LibraryManager`, a `PipelineManager`, a `PipeRouter` and a
`PipeRun` whether the caller would ever load a method or not.

This runs in a **subprocess**, and that is not a stylistic choice. Both hubs are sticky
class-attribute singletons (`RuntimeHub._instance` / `InterpreterHub._instance`) that `teardown`
deliberately does not clear — so once anything in this process has booted a `Pipelex`, an in-process
`InterpreterHub.get_optional_instance()` answers with the stale hub forever and the assertion would
pass vacuously. A fresh interpreter is the only place the question is answerable.

It is also strictly stronger than the import-closure entry point it complements: that one *imports*
`pipelex.runtime_boot`, this one *runs* `RuntimeBoot.make()`. A runtime-only boot builds its plugin
registrar from `RUNTIME_BUILTIN_PLUGINS` alone, so `OrchestratorRegistry`, `BundleValidatorRegistry`
and the PipeFunc executor modes are all empty on it — an import-time check cannot notice a boot step
that tries to resolve out of one of them.
"""

import subprocess  # noqa: S404
import sys
import textwrap

from tests.unit.pipelex.test_runtime_layer_import_closure import INTERPRETER_PACKAGES

#: Wall-clock bound on the booted-runtime subprocess, matching the import-closure harness: a boot
#: that deadlocks must present as a failure, not as a hung suite
#: (`docs/agents/debugging-hanging-pytest-runs.md`).
SUBPROCESS_TIMEOUT_SECONDS = 300

#: Boot the runtime layer in a fresh interpreter, then answer the three questions this module exists
#: to ask. `needs_inference=False` keeps it offline: no gateway terms gate, no model-deck validation.
#: The `sys.modules` sweep runs *before* `pipelex.interpreter_hub` is imported for the hub assertion,
#: so importing it to ask the question cannot be what makes the answer wrong.
_BOOTED_RUNTIME_SCRIPT = textwrap.dedent(
    """
    import sys

    from pipelex.runtime_boot import RuntimeBoot
    from pipelex.system.runtime import IntegrationMode

    interpreter_packages = frozenset(sys.argv[1:])
    # An empty set would make the sweep below flag nothing and the test pass vacuously — the same
    # guard the import-closure harness carries, for the same reason.
    if not interpreter_packages:
        print("no interpreter packages passed — the sweep would match nothing")
        raise SystemExit(2)

    RuntimeBoot.make(integration_mode=IntegrationMode.PYTEST, needs_inference=False)

    offenders = sorted(
        name
        for name in sys.modules
        if name.startswith("pipelex.") and name.split(".")[1] in interpreter_packages
    )
    if offenders:
        print(f"booting RuntimeBoot loaded {len(offenders)} interpreter module(s): {offenders}")
        raise SystemExit(1)
    if "pipelex.interpreter_hub" in sys.modules:
        print("booting RuntimeBoot loaded pipelex.interpreter_hub")
        raise SystemExit(1)

    # Now it is safe to import the interpreter hub to ask whether the boot installed one.
    from pipelex.interpreter_hub import InterpreterHub
    from pipelex.runtime_hub import RuntimeHub
    from pipelex.system.registries.class_registry_access import class_registry_scoping

    if RuntimeHub.get_optional_instance() is None:
        print("the runtime boot did not install a RuntimeHub")
        raise SystemExit(1)
    if InterpreterHub.get_optional_instance() is not None:
        print("the runtime boot installed an InterpreterHub")
        raise SystemExit(1)
    # The documented degradation: with no InterpreterHub installed, class-registry scoping stays at
    # its unscoped default rather than raising (docs/contribute/hub-layering.md).
    if class_registry_scoping.resolve() is not None:
        print("class_registry_scoping resolved a scoped registry on a runtime-only boot")
        raise SystemExit(1)

    print("runtime boot OK")
    """
)


#: The negative control, and the reason it is needed: the sweep below lives inside a `textwrap.dedent`
#: string, so nothing type-checks or lints the *logic* in it. A broken predicate would make the real
#: case pass **forever** while flagging nothing — verified, not theorised: changing the sweep's
#: `name.split(".")[1]` to `[0]` leaves the real case green (it matches nothing, so it finds nothing)
#: and this control is the only thing that goes red. That asymmetry is the point — the real case cannot
#: detect its own blindness, so deleting the control would make every other case in this module
#: unfalsifiable. The `interpreter_hub in sys.modules` check is not a backstop either, since a runtime
#: module importing `pipe_operators` directly never touches the hub — which is the whole case this test
#: exists for.
#:
#: `cogt` is the control package: the runtime boot loads it by definition, so calling it an
#: "interpreter package" must come back a failure, *reported as offending modules*. The sibling
#: import-closure module carries the same control for the same reason (its `DIRTY_ENTRY_POINT`).
CONTROL_PACKAGE_THE_RUNTIME_ALWAYS_LOADS = "cogt"


def _run_booted_runtime(*, interpreter_packages: "tuple[str, ...]") -> subprocess.CompletedProcess[str]:
    """Boot the runtime layer in a fresh interpreter and return the sweep's verdict."""
    try:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c", _BOOTED_RUNTIME_SCRIPT, *interpreter_packages],
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        message = f"the booted-runtime subprocess did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s"
        raise AssertionError(message) from exc


class TestBootedRuntimeLayer:
    def test_the_sweep_still_detects_a_package_the_runtime_boot_really_loads(self) -> None:
        """The control: same script, opposite verdict. Without this, every other case is vacuous."""
        result = _run_booted_runtime(interpreter_packages=(CONTROL_PACKAGE_THE_RUNTIME_ALWAYS_LOADS,))

        assert result.returncode == 1, (
            f"treating {CONTROL_PACKAGE_THE_RUNTIME_ALWAYS_LOADS!r} as an interpreter package must fail — "
            "the runtime boot loads it by definition. This passing means the sweep has stopped sweeping, "
            "and the real case below now proves nothing.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "interpreter module(s)" in result.stdout
        assert "runtime boot OK" not in result.stdout

    def test_booting_the_runtime_layer_loads_no_interpreter_module_and_installs_no_interpreter_hub(self) -> None:
        result = _run_booted_runtime(interpreter_packages=INTERPRETER_PACKAGES)
        assert result.returncode == 0, (
            "booting the runtime layer must load zero interpreter modules and install no InterpreterHub.\n"
            "This is the boot-time half of the hub-layering property — see docs/contribute/hub-layering.md "
            "for how to find the shortest import path to an offender.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "runtime boot OK" in result.stdout
