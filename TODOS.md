# TODOS — two places where the runtime silently substitutes something for what the caller gave it

Branch `refactor/Exec` in this worktree (`_exec/`), off `dev` at v0.41.0. Two independent fixes, batched because they share a shape and nothing else: in both, the runtime accepts a caller's object, quietly replaces it with something almost-equivalent, and never says so. One replaces a Pydantic class with a lossy rebuild of it; the other replaces a registered function with a later one of the same name. Each ships as its own PR.

**Ship order: item 2 first.** It is self-contained, has no interaction with item 1, and its only open question is answerable by a grep. Item 1 is the more valuable fix and the more delicate one.

---

## Item 1 — the schema→`exec()` round trip is paid in-process, and it is lossy

### The finding

Structured generation hands a concrete Pydantic class to the content generator, which throws the class away, rebuilds an approximation of it from its JSON schema through code generation plus `exec()`, and gives the rebuild to the provider as the structured-output schema — while the original class is still sitting in the caller's frame.

The path, in order:

- `pipelex/cogt/content_generation/content_generator.py:128` and `:154` — `make_object` / `make_object_list` receive a concrete `object_class: type[BaseModelTypeVar]`.
- `pipelex/cogt/content_generation/assignment_models.py:87` — `ObjectAssignment.make_for_class` keeps `object_class.__name__` and `object_class.model_json_schema()`. The class itself is dropped here.
- `pipelex/cogt/content_generation/llm_generate.py:44` — the live path rebuilds it: `SchemaToModelFactory.make_from_json_schema(...)`, then `llm_worker.gen_object(llm_job=..., schema=content_class)`. `llm_gen_object_list` does the same at `:69`.
- `pipelex/cogt/content_generation/dry_mock.py:199` — `_reconstruct_object_class` rebuilds it on the dry path too, via the same factory. Both run modes pay it.
- `pipelex/cogt/content_generation/content_generator.py:134` — the caller then re-validates the result against the class it never stopped holding.

### Why it matters

**It is lossy, and the tree already documents the loss.** `_revalidate_against_object_class` (`content_generator.py:44`) states that the rebuilt class "can drop invariants the original class enforces (custom validators, `json_schema_extra` format/pattern hints datamodel-code-generator omits on round-trip)", and there is a dedicated `DryRunObjectFidelityError` for when a mock built from the rebuild fails to re-validate against the original. Read that from the user's side: a user who writes a model with a custom validator gets a structured-output schema that has silently lost it, so the provider is constrained by a weaker contract than the one they wrote. The re-validation catches the bad result afterwards; it does not stop the weaker schema from being sent.

**It runs an `exec()` perimeter where nothing is crossing a boundary.** `schema_to_model_factory.py`'s module docstring is explicit about both the threat and its scope: it `exec()`s code generated from an attacker-influenceable JSON schema "when schemas cross a process boundary", and its Layer 2 restricted builtins "narrow the surface but do NOT contain a determined attacker" — `__build_class__`, `getattr`, `type` and `object` stay reachable, so `().__class__.__base__.__subclasses__()` enumerates every loaded class from inside the `exec()`'d namespace. That defense is correctly designed for the boundary. The code applies it on every structured generation, including the in-process ones where no schema was ever serialized and the class never left the interpreter.

**It costs a code generation plus an `exec()` per structured call.** Measure this rather than asserting it; a number belongs in the PR description, not an adjective.

### The constraint that shapes the fix

`ObjectAssignment` is a serializable DTO **by design**. It is the payload a distributed orchestrator — our Temporal plugin, hooked in via `pipelex/plugins/orchestrator_registry.py` — sends to a worker that has no access to the caller's class object. Across that boundary the class genuinely cannot travel, and rebuilding from schema is the right answer. So the fix is not "remove the reconstruction". It is "stop paying for it when nothing crossed a boundary".

### The change

- **Leave `ObjectAssignment` exactly as it is.** Do not add a live-class field to it. It is a wire model; a `type[BaseModel]` field makes it unserializable and breaks the boundary path outright. This is the tempting wrong fix — the class is *right there* in `make_for_class` — and it must be rejected explicitly rather than rediscovered in review.
- **Thread the class as an explicit optional parameter beside the assignment**, on the in-process path only: `llm_gen_object(object_assignment, *, object_class: type[BaseModel] | None = None)` and the same on `llm_gen_object_list`. `None` means "no class in hand, rebuild from the schema" — which is exactly what a worker entering from the boundary passes, so the boundary path keeps today's behaviour by construction, without a flag to set.
- **One resolution helper, used by both run modes.** Given the assignment and the optional class, return the class to use. Live (`llm_generate.py`) and dry (`dry_mock.py`) both rebuild today and both must take the fast path, or the dry-run fidelity gap becomes asymmetric with live — which would be worse than the current state, because the mock would then be *more* faithful than the thing it mocks.
- `content_generator.make_object` / `make_object_list` pass `object_class=object_class`.

⚠ Every function on this path already carries a subject grant in `subject_grants.toml` (`ObjectAssignment.make_for_class`, `llm_gen_object`, `llm_gen_object_list`, `dry_llm_gen_object`, `dry_llm_gen_object_list`, `_revalidate_against_object_class`). A grant covers one positional subject, so **the new parameter must be keyword-only** — a second bare positional is a violation with or without the grant. Record nothing new; just add after the `*`.

### What to verify rather than assume

- **Kajson's `__kajson_class_source__`.** The rebuilt class carries its own source so kajson can deserialize it across processes without a class registry; the user's real class does not. Today's in-process callers already receive an instance of the *original* class (the re-validation converts it), so the observable surface should not move — but this is the one place a regression can hide. Check what reads that attribute before assuming the fast path is transparent.
- **`_revalidate_against_object_class` on the fast path.** It becomes a conversion between identical types. Keep the call: it is still the boundary-path conversion and the site that raises the dry fidelity error. Check whether re-validating an instance of the correct class short-circuits or runs a full validation — if the latter, that is a second saving, but do not remove the call to collect it.
- **`DryRunObjectFidelityError` reachability.** On the fast path the mock is now built from the real class, so the invariants it used to drop are present and the error should stop firing there. It stays reachable on the boundary path. Do not delete it; find the tests that assert it and scope them to the path that still produces it.

### Tests

- **Identity, not equality.** Assert the provider receives *the same class object* the caller passed (`schema is TheClass`), not a structurally-equal one. Structural equality is precisely what the round trip already preserves, so an equality assertion would pass against the bug.
- A model carrying a custom validator and `json_schema_extra` hints reaches the provider with them intact.
- The boundary path — assignment only, no class — still rebuilds from schema, unchanged.
- Dry run: the fixture that currently triggers `DryRunObjectFidelityError` stops triggering it when the class is in hand, and still triggers it when it is not.
- Both run modes take the same path, asserted directly rather than inferred from two separate tests passing.

**CHECKPOINT A** — item 1 landed: gates green (`make agent-check` + full `make agent-test`), a before/after measurement of a representative structured call in the PR description, and the `schema_to_model_factory.py` docstring updated to say when the perimeter is actually walked.

---

## Item 2 — `FuncRegistry.register_function` silently overwrites

### The finding

`pipelex/system/registries/func_registry.py:99` — on a key collision, `register_function` logs and then overwrites anyway:

```python
key = name or func.__name__
if key in self.root:
    self.log(f"Function '{key}' already exists in registry")
else:
    self.log(f"Registered new single function '{key}' in registry")
self.root[key] = func
```

`log()` at `:88` is `self._logger.debug(...)`, so under any normal configuration the collision produces no visible output at all. The assignment runs on both branches — the `if` distinguishes only the wording.

Three facts make this reachable rather than theoretical:

- The registry is a flat, process-global `dict[str, Callable]`. There is one key space for every source that ever registers.
- Registration names are unqualified. `func_registry_utils.py:266` returns the `@pipe_func` custom name if one was given, otherwise the bare `func.__name__` — no module, no package, no library prefix.
- Registration is driven by scanning the configured library directories (`libraries/library_manager.py:365`), through both the module scan (`func_registry_utils.py:57`) and the folder scan (`:190`).

**The asymmetry gives it away.** `unregister_function` and `unregister_function_by_name` raise `FuncRegistryError` when a name is *absent*. Removing something that was never there is a hard error; replacing something that is there is a debug line.

### The failure

Two library directories — or a library plus an installed package — each defining a `@pipe_func` named `summarize` produce a registry containing one of them, chosen by scan order. Every `PipeFunc` step naming `summarize` then runs the winner, including steps authored against the loser, with no warning at author time, boot time, or run time. Scan order comes from the filesystem and `pkgutil`, so which one wins can differ between two machines running the same code.

### The change

- **Make a collision loud.** Raise `FuncRegistryError` naming the key, both source modules, and the remedy (`@pipe_func(name=...)`). The registry already raises on the symmetric case, so this is consistency, not a new posture — and per the project's no-backward-compatibility rule there is no deprecation ramp to build.
- **Settle the one real design question honestly: is re-registering the *same* function object a collision?** A module imported twice under different names, or a folder scanned twice, would hit it. Same object under the same key should be idempotent; a *different* object under the same key is the error. Verify whether the double-scan actually occurs before choosing — if it does and the check is unconditional, a working setup turns into a boot failure, which is a worse bug than the one being fixed.
- **Grep for deliberate overwrite before changing anything.** If any first-party code registers a builtin and expects a user's function to replace it, that is a legitimate override and it needs an explicit opt-in (`replace=True`) rather than silence. If no such caller exists, do not add the parameter — it would be a speculative surface.

### Tests

- Two distinct functions under one name → raises, and the message names both sources.
- The same function object registered twice → no-op, no raise.
- The eligible/ineligible split is untouched: an ineligible function still routes to `register_ineligible_function` and does not participate in collision detection.
- End to end: two library directories defining the same function name fail boot with the typed error instead of silently picking one.

### Docs

- A `docs/` note on naming `@pipe_func` functions and what the flat name space implies.
- If a new error class is introduced rather than reusing `FuncRegistryError`, regenerate the error reference (`make gep`) and the identity snapshot (`make gei`).

**CHECKPOINT B** — item 2 landed: gates green, changelog entry, docs updated.

---

## Non-goals

Stating these because each is a plausible-looking scope expansion that this plan deliberately declines.

- **Not replacing `exec()` with `pydantic.create_model()`.** That is the standing TODO at `schema_to_model_factory.py:248` and a larger change with its own compatibility surface (`__kajson_class_source__` exists because the generated source is shipped verbatim). Item 1 makes that TODO *matter less* by not walking the path in-process; it does not close it, and the docstring should not imply otherwise.
- **Not namespacing the function registry by module.** Qualified names would remove the collision class entirely, but `function_name` is authored in `.mthds` files, so that is a language decision, not a registry fix.
- **Not changing `ObjectAssignment`'s wire shape.** Anything that alters the payload an orchestrator plugin sends belongs in its own change, argued on its own terms.

## Gates

Per item, before opening the PR:

- `make agent-check`
- full `make agent-test` — both items touch code that framework and scan paths call, where the type checker is blind
- `make drift-check`, with `make drift-plan` → review → `make drift-ack` if a contract opens
- `CHANGELOG.md` under `[Unreleased]`, marked breaking where it is
