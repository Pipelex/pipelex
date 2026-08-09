"""A kernel call is servable on a `RuntimeBoot`-only process with zero `.mthds` loaded.

This is the kernel's *contract*, not a consequence of one — the whole point of extracting operator
semantics out of the interpreter is that a programmatic caller can invoke them without a library, a
router or a pipeline manager. So it is pinned permanently here rather than proven once by hand.

Three layers already guard neighbouring properties and none of them covers this one. The static
hub-layering guard proves no kernel *module* imports `interpreter_hub`.
`test_runtime_layer_import_closure.py` proves `pipelex.kernel.pipelex_kernel` *imports* clean.
`test_runtime_boot_closure.py` proves `RuntimeBoot.make()` *boots* clean. What none of them does is
**call** a kernel op on that boot — and a call is where a runtime-only process would actually break:
by resolving out of a registry the interpreter half fills (`OrchestratorRegistry`,
`BundleValidatorRegistry`, the PipeFunc executor modes are all empty here), or by reaching the
interpreter through a function-local import, which is invisible to the static graph and to the
import-closure test *at once*. The sweep below therefore runs **after** the kernel call, which is
what makes this test strictly stronger than the import-time one it complements.

Run in a **subprocess** for the reason its two siblings state: a suite-level boot already owns the
process singletons, and both hubs are sticky class attributes that `teardown` deliberately does not
clear — so an in-process check would answer from a stale `Pipelex` and pass vacuously.

`needs_inference=False` keeps the boot offline (no gateway terms gate, no model-deck validation), and
`PipeRunMode.DRY` keeps the call offline: the cogt leaf mocks before any worker is looked up, so the
`LLMSetting` names a model the deck never has to resolve.

**On the deferred orchestrator question.** `runtime_boot.py`'s orchestrator-rejection comment defers
the external-interpreter-orchestrator half-application hole to "the first caller of a runtime-only
boot", which is this test. It is settled, not inherited: this boot names no `boot_orchestrator` and
its config sets none, so the gate is never reached and the hole is not on this path. The remedy the
analysis proposes (a `HubSlot.is_interpreter_slot` property plus a `honours_interpreter_slots` class
attribute) remains unbuilt on purpose — it is real machinery for a path that still has no production
caller. Recorded in `wip/boot-split/runtime-boot-external-interpreter-orchestrator.md`.
"""

import subprocess  # noqa: S404
import sys
import textwrap

from tests.unit.pipelex.test_runtime_layer_import_closure import INTERPRETER_PACKAGES

#: Wall-clock bound on the kernel-call subprocess, matching both sibling harnesses: a boot or a call
#: that deadlocks must present as a failure, not as a hung suite
#: (`docs/agents/debugging-hanging-pytest-runs.md`).
SUBPROCESS_TIMEOUT_SECONDS = 300

#: Boot the runtime layer in a fresh interpreter, run **both** façade calls through the kernel, assert
#: the typed results, and only then sweep `sys.modules`. The order is the point: a function-local
#: interpreter import inside a kernel op would land in `sys.modules` during the call and nowhere else.
#: Both arms run because they share almost nothing below the façade — `resolve_llm_setting_for_text`
#: vs `_for_object`, and `dry_llm_gen_text` vs `dry_llm_gen_object` — so covering one leaves the
#: other's closure unproven, and the contract is stated over *a kernel call*, not over one of them.
_KERNEL_CALL_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import sys

    from pipelex.cogt.llm.llm_setting import LLMSetting
    from pipelex.core.concepts.concept_factory import ConceptFactory
    from pipelex.core.concepts.native.concept_native import NativeConceptCode
    from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
    from pipelex.core.stuffs.number_content import NumberContent
    from pipelex.core.stuffs.text_content import TextContent
    from pipelex.kernel.llm_results import LlmObjectResult, LlmTextResult
    from pipelex.kernel.pipelex_kernel import PipelexKernel
    from pipelex.runtime_boot import RuntimeBoot
    from pipelex.system.pipe_run_mode import PipeRunMode
    from pipelex.system.runtime import IntegrationMode

    interpreter_packages = frozenset(sys.argv[1:])
    # An empty set would make the sweep flag nothing and the test pass vacuously — the same guard both
    # sibling harnesses carry, for the same reason.
    if not interpreter_packages:
        print("no interpreter packages passed — the sweep would match nothing")
        raise SystemExit(2)

    RuntimeBoot.make(integration_mode=IntegrationMode.PYTEST, needs_inference=False)

    kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="kernel-boot-contract")
    model = LLMSetting(model="kernel-boot-contract-model", temperature=0.5)

    object_result = asyncio.run(
        kernel.llm_object(
            memory=WorkingMemoryFactory.make_empty(),
            output_class=NumberContent,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.NUMBER),
            model=model,
            user="Pick a number.",
            result="answer",
        )
    )

    if not isinstance(object_result, LlmObjectResult):
        print(f"llm_object returned {type(object_result).__name__}, not an LlmObjectResult")
        raise SystemExit(1)
    if not isinstance(object_result.content, NumberContent):
        print(f"llm_object produced {type(object_result.content).__name__}, not the NumberContent it was given")
        raise SystemExit(1)
    if object_result.memory.get_main_stuff().content is not object_result.content:
        print("the memory returned by llm_object does not carry the produced content as its main stuff")
        raise SystemExit(1)

    text_result = asyncio.run(
        kernel.llm_text(
            memory=WorkingMemoryFactory.make_empty(),
            model=model,
            user="Say something.",
            result="reply",
        )
    )

    if not isinstance(text_result, LlmTextResult):
        print(f"llm_text returned {type(text_result).__name__}, not an LlmTextResult")
        raise SystemExit(1)
    main_text_content = text_result.memory.get_main_stuff().content
    if not isinstance(main_text_content, TextContent):
        print(f"llm_text landed {type(main_text_content).__name__} in memory, not a TextContent")
        raise SystemExit(1)
    if main_text_content.text != text_result.text:
        print("the memory returned by llm_text does not carry the text the result reports")
        raise SystemExit(1)

    # Swept last, so a function-local interpreter import taken during either call is caught too.
    offenders = sorted(
        name
        for name in sys.modules
        if name.startswith("pipelex.") and name.split(".")[1] in interpreter_packages
    )
    if offenders:
        print(f"the kernel call loaded {len(offenders)} interpreter module(s): {offenders}")
        raise SystemExit(1)
    if "pipelex.interpreter_hub" in sys.modules:
        print("the kernel call loaded pipelex.interpreter_hub")
        raise SystemExit(1)

    print("kernel boot contract OK")
    """
)

#: The negative control. The sweep lives inside a `textwrap.dedent` string, so nothing type-checks or
#: lints the logic in it — a broken predicate would leave the real case green forever while flagging
#: nothing, and the real case cannot detect its own blindness. `cogt` is the control package because
#: an LLM kernel call loads it by definition, so calling it an "interpreter package" must come back a
#: failure, reported as offending modules. Both sibling harnesses carry the same control.
CONTROL_PACKAGE_THE_KERNEL_ALWAYS_LOADS = "cogt"


def _run_kernel_call(*, interpreter_packages: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Boot the runtime layer in a fresh interpreter, call the kernel, and return the verdict."""
    try:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c", _KERNEL_CALL_SCRIPT, *interpreter_packages],
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        message = f"the kernel boot-contract subprocess did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s"
        raise AssertionError(message) from exc


class TestKernelBootContract:
    def test_the_sweep_still_detects_a_package_the_kernel_call_really_loads(self) -> None:
        """The control: same script, opposite verdict. Without this, the real case below is vacuous."""
        result = _run_kernel_call(interpreter_packages=(CONTROL_PACKAGE_THE_KERNEL_ALWAYS_LOADS,))

        assert result.returncode == 1, (
            f"treating {CONTROL_PACKAGE_THE_KERNEL_ALWAYS_LOADS!r} as an interpreter package must fail — "
            "an LLM kernel call loads it by definition. This passing means the sweep has stopped sweeping, "
            "and the real case below now proves nothing.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "interpreter module(s)" in result.stdout
        assert "kernel boot contract OK" not in result.stdout

    def test_every_kernel_call_runs_on_a_runtime_only_boot_with_no_library(self) -> None:
        result = _run_kernel_call(interpreter_packages=INTERPRETER_PACKAGES)

        assert result.returncode == 0, (
            "every kernel call must be servable on a RuntimeBoot-only process with zero .mthds loaded, and must "
            "load no interpreter module doing it. This is the kernel's contract — see pipelex/kernel/__init__.py "
            "for the doctrine and docs/contribute/hub-layering.md for how to find the shortest import path to an "
            "offender.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "kernel boot contract OK" in result.stdout
