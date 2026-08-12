"""The Pipelex kernel: operator-execution semantics as importable functions.

What an operator step actually *does* — deck resolution, prompt or job-params assembly, generation,
memory write-back — used to be reachable only through a fully booted interpreter with a loaded
library. This package holds that semantics once, so it has **one
implementation with multiple callers**: the interpreter's operator classes, and any programmatic
caller invoking the same functions on a ``RuntimeBoot``-only process with zero ``.mthds`` loaded.
Single-sourcing is the point — two callers with two copies drift.

The doctrine below is what keeps that true. Each rule exists because its absence has already cost
this repo something; see ``docs/contribute/hub-layering.md``.

**Layering.** The caller-facing API is hub-free: an explicit :class:`~pipelex.kernel.pipelex_kernel.PipelexKernel`
and explicit arguments, never an ambient lookup. Kernel *internals* may use ``pipelex.runtime_hub``
— never ``pipelex.interpreter_hub``, directly or transitively. ``pipelex.kernel`` is declared in the
guard's ``KERNEL_LAYER_PACKAGES`` and pinned by a test, because **an undeclared package is not
neutral, it is unpoliced**: both the layer rule and the transitive rule filter their candidates
through that declaration, so omitting the entry makes the guard quieter rather than louder.

**Import from definition sites only.** Never from ``pipelex.exceptions`` or any other cross-layer
re-export aggregate, and never let this ``__init__.py`` become one. For most of the tree that is a
style rule (the repo's "direct full-path imports everywhere"); here it is a *layering* property — a
module that re-exports across layers is a layer boundary with the sign filed off, and importing one
symbol from it drags every interpreter package it re-exports into the kernel closure. Five vendor
adapters once loaded interpreter modules apiece through exactly that hole with every gate green.
The mechanical half is bought by the declaration above:
``tests/unit/pipelex/test_kernel_layer_exceptions_aggregate_gate.py`` walks every declared package
and fails on imports and bare strings alike, module-level or function-local.

**Every import stays at module top level.** A function-local import is invisible to the static
import graph and to the import-closure test at the same time, so it hides a breach from both gates
at once. If one ever seems necessary here, the placement is wrong and the type should move instead.

**Concept resolution goes through the pure tiers.** Kernel run paths answer concept compatibility
with :meth:`~pipelex.core.concepts.concept.Concept.are_compatible_by_declaration` (no registry; a
caller without a loaded library supplies its own ``concept_resolver``, or omits it where no
``refines`` crosses a package boundary) and ``are_structure_classes_compatible`` (which takes
resolved types). It never calls ``ConceptLibrary.is_compatible`` or
``ConceptProviderAbstract.get_structure_class`` — that is where resolution, and therefore the
ambient registry read, legitimately lives. Passing the concrete class alongside the concept is the
preferred shape, which is why the object entry point takes ``output_class`` outright.

**Calls are activity-shaped.** Explicit, serializable-leaning inputs and outputs; ``WorkingMemory``
threaded explicitly (taken and returned); no hidden shared state. The memory contract, stated once
so both caller classes read the same thing: **a kernel call may mutate the memory it is passed and
returns it — callers must treat the returned memory as the result and must not rely on aliasing of
the argument**, because inline execution aliases the two today and a serialization boundary will
not. This is a design constraint, not a deliverable: it keeps a future distributed-activity wrapping
a re-decoration rather than a rewrite.

**Functions carry the semantics; the class is a façade.** Module-level functions hold the shared
implementation. ``PipelexKernel`` is a thin ergonomic façade over them, holding the per-run state a
caller would otherwise thread through every call. The interpreter's operators call the functions
directly.

**The API is fully keyword-only — zero subject grants.** Only a first parameter may be positional,
and strictly only when it is obviously the subject. Nothing here clears that bar: ``llm_text`` and
``llm_object`` name what they *produce*, and ``memory`` is threaded state, not the operand. So
``pipelex/kernel/`` records no entries in ``subject_grants.toml`` and every call site names every
argument.

**Boot contract.** Every kernel call must be servable on ``RuntimeBoot.make()``
(``pipelex/runtime_boot.py``) with no interpreter constructed and no library loaded.
``tests/unit/pipelex/kernel/test_kernel_boot_contract.py`` is what proves it: it boots keyless,
**calls every entry point**, and sweeps ``sys.modules`` afterwards. Treat that as the gate rather
than as one of two — ``tests/unit/pipelex/test_kernel_layer_import_closure.py`` covers only what
its ``pipelex.kernel.pipelex_kernel`` entry point imports, and the façade is LLM-only, so most of
this package sits outside its closure. **Every new entry point here gets an arm in that
subprocess.** The rule is not ceremony: the sweep is the only gate that can see a function-local
interpreter import (both static guards read module-level imports, and the blind spot is
*per-function*), and nothing tells you when it has fallen behind — Phase 2 added five ops and every
gate stayed green while covering none of them.

Per the repo-wide rule, this module holds **no re-exports** — import each symbol from the module
that defines it.
"""
