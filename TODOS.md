# Two places where the runtime silently substituted something for what the caller gave it

Branch `refactor/Exec`, off `dev` at v0.41.0. Two independent fixes, batched because they share a shape and nothing else: in both, the runtime accepted a caller's object, quietly replaced it with something almost-equivalent, and never said so. One replaced a Pydantic class with a lossy rebuild of it; the other replaced a registered function with a later one of the same name.

This file is the review guide. It carries the reasoning, the measurements, and — importantly — the two places where doing the work **corrected the plan that motivated it**. Read those first if you are short on time: they are where a reviewer's attention is worth the most.

- **Commit `ba9b0750c`** — `FuncRegistry.register_function` silently overwrote (item 2 below).
- **Commit `bbf06b707`** — the schema→`exec()` round trip was paid in-process, and it was lossy (item 1 below).

Each commit is independently green on `make agent-check`, `make drift-check`, and the full `make agent-test`.

---

## Item 1 — the schema→`exec()` round trip was paid in-process, and it was lossy

### What was wrong

Structured generation handed a concrete Pydantic class to the content generator, which threw the class away, rebuilt an approximation of it from its JSON schema through code generation plus `exec()`, and gave the **rebuild** to the provider as the structured-output schema — while the original class was still sitting in the caller's frame.

The path: `content_generator.make_object` / `make_object_list` received `object_class: type[BaseModelTypeVar]`; `ObjectAssignment.make_for_class` kept only `__name__` + `model_json_schema()` and dropped the class; `llm_generate.py` rebuilt it via `SchemaToModelFactory.make_from_json_schema` and passed the rebuild to `llm_worker.gen_object(schema=...)`; `dry_mock.py` rebuilt it on the dry path too. Then `content_generator` re-validated the result against the class it had never stopped holding.

### What the rebuild drops — verified, not assumed

- custom `@field_validator` / `@model_validator` logic
- `json_schema_extra` format/pattern hints
- **the output structure's own description** — its class docstring lands in `model_json_schema()["description"]`, and `datamodel-code-generator` does not re-emit it, so the rebuilt class has `__doc__ = None` and its schema has no top-level `description`. Field-level descriptions do survive.

That last one the original plan did not name, and it is the most directly user-visible: every in-process structured call was sending the provider a schema stripped of the concept's own description — prompt-relevant signal, silently gone. Reproduce in three lines:

```python
class Line(StructuredContent):
    """A billed line."""
    label: str

rebuilt = SchemaToModelFactory.make_from_json_schema(schema=Line.model_json_schema(), class_name="Line")
assert rebuilt.__doc__ is None  # and "description" is absent from rebuilt.model_json_schema()
```

Read from the user's side: someone who writes a model with a validator got a structured-output schema that had silently lost it, so the provider was constrained by a weaker contract than the one they wrote. The re-validation caught the bad result *afterwards*; it did not stop the weaker schema from being sent.

### The constraint that shaped the fix

`ObjectAssignment` is a serializable DTO **by design**. It is the payload a distributed orchestrator — our Temporal plugin, hooked in via `pipelex/plugins/orchestrator_registry.py` — sends to a worker that has no access to the caller's class object. Across that boundary the class genuinely cannot travel, and rebuilding from schema is the right answer. So the fix is not "remove the reconstruction". It is "stop paying for it when nothing crossed a boundary".

### What changed

- **`ObjectAssignment` is untouched.** No live-class field was added. It is a wire model; a `type[BaseModel]` field makes it unserializable and breaks the boundary path outright. This is the tempting wrong fix — the class is *right there* in `make_for_class` — and it was rejected deliberately, not overlooked.
- **The class is threaded as an explicit keyword-only parameter beside the assignment**, on the in-process path only: `llm_gen_object(object_assignment, *, object_class=None)` and the same on `llm_gen_object_list` and the two dry leaves. `None` means "no class in hand, rebuild from the schema" — which is exactly what a worker entering from the boundary passes, so **the boundary path keeps today's behaviour by construction, with no flag to set**.
- **One resolution helper serves both run modes** — `object_class_resolution.resolve_object_class`, a new leaf module so neither `llm_generate` nor `dry_mock` has to import the other. Live and dry both rebuilt before and both take the fast path now. Had only the live leaf been fixed, the dry mock would be built against a *weaker* class than the one the provider is constrained by — the mock would be more faithful than the thing it mocks, which is worse than the state we started from. `test_dry_leaf_resolves_the_class_the_same_way_as_the_live_leaf` asserts this directly rather than leaving it inferred from two separate passing tests.
- Keyword-only matters mechanically here: every function on this path already carries a subject grant in `subject_grants.toml`, and a grant covers one positional subject. A second bare positional would be a violation with or without it. No grant was added; the grant for the deleted `dry_mock._reconstruct_object_class` was removed.

### The measurement, and the correction it forces

The plan asserted "a code generation plus an `exec()` per structured call". **That is wrong**, and the number says so: `SchemaToModelFactory.make_from_json_schema` memoizes on a sha256 of the schema, so the cost is per *distinct structure per process*, not per call. Measured on a representative `StructuredContent` (mixed primitives, an optional, a nested `$defs` list):

| | before | after |
|---|---|---|
| first structure in a process (one-time `datamodel-code-generator` warmup + codegen + `exec()`) | ~81 ms | 0 |
| each additional distinct structure | ~6–7 ms | 0 |
| repeat call on an already-seen structure | ~0.01 ms (cache hit) | 0 |

So the throughput win is real but small and front-loaded: ~81 ms + ~7 ms × (N−1) per process for a method with N distinct structured outputs, and effectively nothing per call after warm-up. **The fidelity fix is the reason to do this; the saved `exec()` perimeter and the codegen are the bonus.** Please weigh it that way — this is not a performance change.

`schema_to_model_factory.py`'s module docstring now opens by saying when its perimeter is actually walked: only when no live class is in hand, which is also the only case where the schema is attacker-influenceable. Its Layer 2 restricted builtins are explicitly *not* a sandbox (`().__class__.__base__.__subclasses__()` stays reachable), so not walking it where nothing crossed a boundary is worth having on its own.

### The three "verify rather than assume" items

- **Kajson's `__kajson_class_source__`.** Nothing regresses. The attribute exists so kajson can rebuild the reconstructed class on the far side of a process boundary. In-process, the leaf's return value is immediately converted by `_revalidate_against_object_class` into an instance of the caller's real class and never serialized as the rebuild; in-tree the attribute is read only by `SchemaToModelFactory`'s own tests. The boundary path — the only one that ships the rebuilt class anywhere — is untouched.
- **`_revalidate_against_object_class` on the fast path.** ⚠ **The plan got this one wrong, and both PR review bots caught it.** The plan said to keep the call and framed short-circuiting it as declining a *performance* saving. It is not a performance question: with the live class at the leaf, the provider (instructor's `response_model=`) already constructs **and validates** an instance of the caller's class, so re-validating the dump ran the caller's validators a **second** time, on data they had already normalized. A validator that transforms rather than rejects — `return f"INV-{value}"` — produced `INV-INV-…`; one that asserts its input is not yet normalized would reject valid provider output. Same defect on the list path and on the dry path. That is a regression this branch introduced, and it hit exactly the population the fix exists to serve. The fix is subtractive: `if isinstance(raw_obj, object_class): return raw_obj`. The call is still the boundary-path conversion (a schema-rebuilt class is never a subclass of `object_class`, so it falls through) and still the site that raises the dry fidelity error. The measured cost of the removed round trip is ~0.008 ms/object — nil, which is the point: the reason to short-circuit is semantic, not throughput.
- **`DryRunObjectFidelityError` reachability.** It stops firing on the in-process object path and stays reachable on the boundary path and on the structured-search path, which always rebuilds. Not deleted; its tests were re-scoped rather than removed.

### The behaviour change a reviewer should actually look at

On the in-process path the mock is now built from the real class, so an invariant the schema round-trip used to drop is present at *build* time. The constrained fixture therefore fails earlier and with a different class: `DryRunMockBuildError` out of `build_mock_object`, instead of `DryRunObjectFidelityError` out of the re-validation. Both are `ErrorDomain.INPUT`, both are caller-facing, and both name the same `examples` / `mock_format` remedy — but it is a wire-visible `error_type` change on that path and it should be seen, not skimmed.

`test_dry_run_object_fidelity.py` was rewritten around exactly this split: it asserts the fidelity error against the boundary composition (leaf with no class in hand → re-validate, the same comprehension shape `make_object_list` uses), and asserts the build error in-process.

### Tests

- **Identity, not equality** — `test_object_class_passthrough.py` asserts the provider receives *the same class object* (`schema is HintedName`), never a structurally-equal one. Structural equality is precisely what the round trip already preserved, so an equality assertion would have passed against the bug.
- **A validator that transforms, asserted to run exactly once** (`NormalizedReference`, `INV-` prefix). The original test suite used only a *rejecting* validator, which is idempotent and therefore structurally blind to double execution — which is why the double-validation regression above got past it. Both new tests were confirmed red without the `isinstance` short-circuit and green with it.
- A model carrying a custom validator and `json_schema_extra` hints reaches the provider with both intact, asserted observably (the received class rejects the invalid value; its schema still carries the hint).
- A **control** test proves the loss is real: with no class in hand, the rebuilt class *accepts* data the author's class rejects.
- The list path asserts the wrapper's item annotation is the caller's class, on both arms.
- Both run modes take the same path, asserted directly.

---

## Item 2 — `FuncRegistry.register_function` silently overwrote

### What was wrong

On a key collision, `register_function` logged and then overwrote anyway. `log()` is `self._logger.debug(...)`, so under any normal configuration the collision produced no visible output at all — and the assignment ran on both branches, so the `if` distinguished only the wording.

Three facts made it reachable rather than theoretical: the registry is a flat, process-global `dict[str, Callable]`, so there is one key space for every source that ever registers; registration names are unqualified (the `@pipe_func` custom name if given, otherwise the bare `func.__name__` — no module, no package, no library prefix); and registration is driven by scanning the configured library directories.

**The asymmetry gives it away.** `unregister_function` and `unregister_function_by_name` *raise* `FuncRegistryError` when a name is absent. Removing something that was never there was a hard error; replacing something that is there was a debug line.

### The failure

Two library directories — or a library plus an installed package — each defining a `@pipe_func` named `summarize` produced a registry containing one of them, chosen by scan order. Every `PipeFunc` step naming `summarize` then ran the winner, including steps authored against the loser, with no warning at author time, boot time, or run time. Scan order comes from the filesystem and `pkgutil`, so which one wins could differ between two machines running the same code.

### What changed

A collision now raises `FuncRegistryError` naming the key, both origins, and the remedy (`@pipe_func(name=...)`). The registry already raised on the symmetric case, so this is consistency, not a new posture.

### The two open questions, answered by reading the code

- **Is re-registering the *same* function object a collision?** No — it is a no-op. This is the shape the double-scan actually produces: `import_module_from_file` keys `sys.modules` by a name mangled from the file's **absolute path**, so a folder scanned twice returns the cached module and therefore the *same* function object. Two distinct objects under one key is the only shape that indicates a real clash. Pinned by `test_rescanning_the_same_folder_is_idempotent`.
- **Does any first-party code deliberately overwrite?** No — `pipelex/` defines no `@pipe_func` of its own, so nothing registers a builtin expecting a user function to replace it. **No `replace=True` parameter was added**; with no caller for it, it would have been a speculative surface.

### One reachability check worth recording

The transported PipeFunc path (`DirectPipeFuncExecutor.run_pipe_func_transported`) materializes customer sources into a fresh `mkdtemp` workdir, which *would* yield a different function object under the same name on a second run in one process. It stays safe because that path is one-shot per process: `pipe_func_transported_entrypoint` runs exactly one request and then calls `Pipelex.teardown_if_needed()`, which clears the registry. Recorded here so a reviewer does not have to re-derive it.

### Tests

Two distinct functions under one name raise, and the message names both sources; the same function object registered twice is a no-op; an ineligible function still routes to `register_ineligible_function` and does not participate in collision detection; and end to end, two library directories defining the same function name fail the scan with the typed error instead of silently picking one.

---

## Deliberately not done

Each of these is a plausible-looking scope expansion that was declined on purpose.

- **Not replacing `exec()` with `pydantic.create_model()`.** That is the standing TODO at `schema_to_model_factory.py` and a larger change with its own compatibility surface (`__kajson_class_source__` exists because the generated source is shipped verbatim). Item 1 makes that TODO matter *less* by not walking the path in-process; it does not close it, and the docstring does not imply otherwise.
- **Not namespacing the function registry by module.** Qualified names would remove the collision class entirely, but `function_name` is authored in `.mthds` files, so that is a language decision, not a registry fix.
- **Not changing `ObjectAssignment`'s wire shape.** Anything that alters the payload an orchestrator plugin sends belongs in its own change, argued on its own terms.
- **Not auditing the *boundary* arm of `_revalidate_against_object_class`.** Its `model_dump(serialize_as_any=True)` → `model_validate` round trip is not identity-preserving in general (subclass erasure; dumped-by-field-name data that only revalidates thanks to `populate_by_name=True` and a compensating before-validator elsewhere). Pre-existing, unchanged here, must stay — it *is* the boundary conversion. Deferred to `wip/inputs/boundary-revalidation-round-trip-is-unaudited.md`.

## Cross-repo

Checked, nothing to change:

- The private Temporal plugin's `act_llm_gen_object` / `act_llm_gen_object_list` call `llm_gen_object(object_assignment=...)` with no class, so they take the boundary path unchanged. Its `content_generator_in_workflow.py` comment describing the reconstruction stays accurate for that path.
- `pipelex-transport`'s bridge conftest registers module-level function objects, so its repeated registration is the idempotent case.
- The only `llm_gen_object` mention in `docs/specs/` is the `UnitJobId` string value, which did not change.

## Docs touched

- `docs/building-methods/pipes/pipe-operators/PipeFunc.md` — new "Function names share one flat name space" section.
- `docs/under-the-hood/dry-run-mock-generation.md` — the dry object leaf resolves its class the same way the live leaf does; which typed error you get on which path.
- `docs/under-the-hood/distributed-content-generation.md` — reconstruction is the boundary answer and only that; the type bridge is kept in-process on purpose.
