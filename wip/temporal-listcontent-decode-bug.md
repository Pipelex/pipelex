# Tier 9b — Cross-process decode of dynamic-concept `ListContent` returned from a child workflow

> **Status:** Ready to design. Bug is reproducible and root-caused. The companion fix in `template_preprocessor.py` (lookbehind on `@variable`) has already landed on this branch and unblocked the `pipelex run bundle ... generate_invoice_single` case end-to-end. Tier 9b (`generate_invoice_list`) is the remaining failure, and it sits in serialization, not in the parser.
>
> **Workspace note:** `../kajson` (sibling repo `kajson/`) is fair game for changes — modify it if a cleaner abstraction lives there.

## TL;DR

`WorkingMemory.dump_for_temporal` (`pipelex/core/memory/working_memory.py:472-495`) injects raw `__class__` / `__module__` metadata onto each item of a `ListContent` payload. These markers are *meant* to be read by pipelex's own `hydrate_working_memory` after the per-workflow `LibraryCrate` has been loaded — but they are encoded with the **same keys** that `kajson`'s universal decoder uses to eagerly rebuild classes during Temporal's data-converter step, well before pipelex gets a chance to hydrate. When a child workflow returns a `PipeOutput` whose `working_memory_raw` contains those items, the parent workflow (`WfPipeRun`) tries to decode the result through `kajson` first, fails to find the dynamic class (`structured_output_test__Invoice`) in `'builtins'` or the global registry, and crashes with `KajsonDecoderError` → `RuntimeError: Failed decoding arguments`.

The single-output case (`Invoice`) works because `dump_for_temporal` does **not** inject those markers for non-list content; only `ListContent` items get them.

## Reproduction

Prereqs:

- Temporal dev server on `localhost:7233`
- The two scoped workers from `/temporal-e2e-validate` (router + runner) running and pointed at the current code:

```bash
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux kill-session -t temporal-worker-runner 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
tmux new-session -d -c "$PWD" -s temporal-worker-runner \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner'
sleep 5
```

### Failing case (Tier 9b — list)

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds \
  --pipe generate_invoice_list \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

The CLI hangs. In the router tmux session you will see:

```
KajsonDecoderError: Class 'structured_output_test__Invoice' not found
  in module 'builtins' or global registry
RuntimeError: Failed decoding arguments
  ← temporalio/worker/_workflow_instance.py:2101 (_convert_payloads)
  ← _apply_resolve_child_workflow_execution
  ← wf_pipe_run.py:43 (await workflow.execute_child_workflow(WfPipeRouter.run, ...))
```

Clean up after a failed run:

```bash
pkill -f "pipelex run bundle" 2>/dev/null
RUNNING=$(temporal workflow list --address localhost:7233 --namespace default \
  --query 'ExecutionStatus="Running"' 2>&1 | tail -n +2 | awk '{print $2}')
for wid in $RUNNING; do
  [ -n "$wid" ] && temporal workflow terminate --address localhost:7233 --namespace default \
    --workflow-id "$wid" --reason "cleanup"
done
# Restart the workers so they don't keep replaying the terminated workflow's history.
tmux kill-session -t temporal-worker-router; tmux kill-session -t temporal-worker-runner
# (re-create the sessions per the prereqs)
```

### Passing case (Tier 9a — single, for contrast)

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds \
  --pipe generate_invoice_single \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Completes with `✓ Dry run completed successfully`. Same dynamic `Invoice` concept, same crate. The only difference: single output (one Invoice) vs. list output (`Invoice[2]`).

### Passing in-process counterpart (deliberately masks the bug)

```bash
.venv/bin/pytest -x -v tests/integration/pipelex/temporal/tracing/test_split_worker_object_gen.py \
  -m temporal --temporal-server local
```

Both `[single]` and `[list]` parametrizations pass. This is the test that was meant to validate cross-process object generation — but it shares a Python process with the in-process Temporal worker, so kajson's globals lookup succeeds by accident (see "Why this slipped past pytest" below).

## Code path — what actually happens

```
CLI submitter (user process — has the crate)
  │
  │  starts top-level workflow
  ▼
WfPipeRun.run(pipe_run_arg)                          (router worker process)
  │  pipelex/temporal/tprl_pipe/wf_pipe_run.py:29
  │
  │  line 43:
  │    pipe_output = await workflow.execute_child_workflow(WfPipeRouter.run, arg=pipe_job, id=...)
  │
  │  ┌────────────────────────────────────────────────────────────────┐
  │  │ When this await resolves, Temporal calls                       │
  │  │ _apply_resolve_child_workflow_execution → data converter      │
  │  │ → kajson.loads(...) on the child's serialized PipeOutput.     │
  │  │                                                                │
  │  │ Kajson walks the JSON, sees __class__ on each list item,      │
  │  │ tries to resolve 'structured_output_test__Invoice':           │
  │  │   1. module 'builtins' — not there                            │
  │  │   2. global KajsonManager registry — not there                │
  │  │      (WfPipeRouter registered it into a per-workflow registry │
  │  │       and tore that down in its `finally` block — see below.) │
  │  │ → KajsonDecoderError → Failed decoding arguments              │
  │  └────────────────────────────────────────────────────────────────┘
  │
  ▼
WfPipeRouter.run(pipe_job)                            (router worker process, child workflow)
  │  pipelex/temporal/tprl_pipe/wf_pipe_router.py:25
  │
  │  lines 51-65:
  │    workflow_registry = ClassRegistry()
  │    workflow_registry.register_classes_dict(global_registry.get_classes_dict())
  │    wf_library_id = f"wf_{workflow.info().workflow_id}"
  │    library_manager.open_library(library_id=wf_library_id)
  │    wf_library.set_class_registry(workflow_registry)
  │    set_current_library(library_id=wf_library_id)
  │    library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)
  │      └─ this registers `structured_output_test__Invoice` into workflow_registry
  │         — but NOT into the global KajsonManager registry.
  │
  │  line 127: pipe_output = await pipe.run_pipe(...)
  │      └─ dispatches act_llm_gen_object_list to the runner; runner returns list[Invoice]
  │      └─ result lands back in workflow_registry, fine here.
  │
  │  line 182: pipe_output = pipe_output.prepare_for_temporal(library_crate=library_crate)
  │      └─ PipeOutput.prepare_for_temporal (core/pipes/pipe_output.py:28-49) dehydrates:
  │           working_memory_raw = self.working_memory.dump_for_temporal()
  │           working_memory     = WorkingMemory()    # empty
  │
  │  finally (lines 172-176):
  │    library_manager.teardown(library_id=wf_library_id)   # ← tears down per-workflow registry
  │    teardown_current_library()
  │
  │  line 185: return pipe_output
  │      └─ Temporal data converter encodes this PipeOutput via kajson.dumps(...)
```

## The actual offender

`pipelex/core/memory/working_memory.py:472-495`:

```python
def dump_for_temporal(self) -> dict[str, Any]:
    raw = self.model_dump(serialize_as_any=True)
    raw_root = raw.get("root", {})
    for stuff_name, stuff in self.root.items():
        content = stuff.content
        if isinstance(content, ListContent) and stuff_name in raw_root:
            list_content = cast("ListContent[StuffContent]", content)
            serialized_items: list[dict[str, Any]] = []
            for item in list_content.items:
                item_dict = item.model_dump(serialize_as_any=True)
                # Preserve type metadata for items under Anything concepts so
                # the hydration side can reconstruct the correct content class.
                item_dict["__class__"] = type(item).__name__         # ← collides with kajson's marker
                item_dict["__module__"] = type(item).__module__      # ← collides with kajson's marker
                serialized_items.append(item_dict)
            raw_root[stuff_name]["content"] = serialized_items
    return raw
```

The intent of `__class__` / `__module__` here is pipelex-internal: a hint for `pipelex/temporal/tprl_pipe/hydration.py:_hydrate_list_item` so the `Anything[]` case can reconstruct the correct subclass. But these keys are also the **exact public protocol** that kajson uses in `kajson/json_decoder.py:113-194` (`universal_decoder`) to recognize encoded class instances. The data converter installed in `pipelex/temporal/temporal_data_converter.py` calls `kajson.loads(...)` on every payload, and kajson walks the whole tree.

```python
# kajson/json_decoder.py:132-170
def universal_decoder(self, the_dict):
    if "__class__" not in the_dict:
        return the_dict                          # ← the only "leave-alone" branch
    class_name = the_dict.pop("__class__")
    module_name = the_dict.pop("__module__")
    # ... registry lookups, module imports, raise KajsonDecoderError on failure ...
```

So as long as the dehydrated payload contains `__class__` keys, kajson is going to try to bind the class **at the data-converter boundary**, before pipelex's own hydration runs. This works in-process because the dynamic class is still alive in the global registry; it does not work cross-process because `WfPipeRouter` tore down its per-workflow registry as part of returning.

The fact that `PipeOutput.prepare_for_temporal` blanks out `working_memory` and moves the payload to `working_memory_raw` does **not** protect us: `working_memory_raw` is still a `dict[str, Any]`, kajson recurses into it, and finds the `__class__` keys.

## Why single works and list fails

Look at the same function (`working_memory.py:472-495`). The `__class__`/`__module__` injection is gated on `isinstance(content, ListContent)`. For single content (`Invoice`, not `Invoice[2]`), the function falls back to plain `model_dump(serialize_as_any=True)` output — no extra metadata. Kajson sees a plain dict at that position, returns it as-is, and pipelex's `hydrate_content` (`hydration.py:99-102`) takes over with concept-driven typing using `concept.structure_class_name`. No global-registry lookup at the kajson layer.

The list path was added later to support the `Anything[]` case at `hydration.py:58-70`, where the hydrator cannot derive the per-item type from the concept alone. The author manually wrote `__class__` / `__module__` to carry the per-item type — not realizing they were also speaking kajson's language.

## Why this slipped past pytest

`tests/integration/pipelex/temporal/tracing/test_split_worker_object_gen.py` exercises the same `act_llm_gen_object_list` path, including the `[list]` parametrization, and passes. The reason is process topology, not test logic:

- The pytest runs an **in-process** Temporal worker via the SDK's test environment.
- The dynamic `Invoice` class is created in the test's Python process when the crate is loaded (it executes the bundle's structured-concept source code with `exec(...)`, producing a real class object).
- That class object is referenced from the per-workflow registry, but Python's globals (and likely kajson's global `KajsonManager`) also hold a reference because the class was created in this process and has not been GC'd.
- When kajson hits `__class__: 'structured_output_test__Invoice'` at decode time, it looks up the global registry, **finds the class accidentally**, and decodes fine.

In the true 3-process CLI run:

- `WfPipeRouter` runs in the router *worker* process.
- That process loads the crate into a per-workflow registry, runs the pipe, then **explicitly tears the registry down** in the `finally` block (`wf_pipe_router.py:172-176`) before returning.
- The class object becomes unreferenced and the global registry never had it.
- When `WfPipeRun` (still in the router worker process, but in a different workflow scope after the child resolves) goes to decode the child's result, kajson cannot find the class anywhere.

This is also why **`_validate_as_known_class` in `hydration.py:17-36`** doesn't help: it was written specifically to repair instances that kajson *did* rehydrate (using a different exec of the dynamic source). If kajson fails outright, we never reach `_validate_as_known_class`.

## Constraints on any fix

1. **Don't ship the crate twice.** The crate already travels with `PipeJob`. Re-attaching it to every child-workflow return payload would double the wire size.
2. **Don't put dynamic classes into the global registry on the router process.** Per-workflow scoping is intentional — different workflows can define the same concept name with different shapes (Tier C of the concurrent isolation tests).
3. **Don't lose the `Anything[]` use case.** The hydration side legitimately needs per-item type information when the concept does not pin it down.
4. **Don't regress the in-process test path.** `test_split_worker_object_gen.py` and friends must keep passing.
5. **Keep the dehydration symmetric.** `prepare_for_temporal` / `hydrate_working_memory` is a clean pair today; a fix that requires special-casing fields outside this pair is a smell.

## Solution space

### Option A — Use a pipelex-private marker namespace (recommended)

Rename the markers in `dump_for_temporal` from `__class__` / `__module__` to a pipelex-private namespace, e.g. `__pipelex_class__` / `__pipelex_module__`. Kajson's universal decoder explicitly gates on `__class__` (`kajson/json_decoder.py:132`), so any other key set is invisible to it. Pipelex's hydration side already does its own class lookup using these markers (`hydration.py:58-62`), so it is purely a rename on both ends.

Changes (estimated):

- `pipelex/core/memory/working_memory.py:472-495` — write `__pipelex_class__` / `__pipelex_module__` instead.
- `pipelex/temporal/tprl_pipe/hydration.py:58-62` — read `__pipelex_class__` instead of `__class__`; update the `{"__class__", "__module__"}` filter.
- `pipelex/temporal/tprl_pipe/hydration.py:17-36` (`_validate_as_known_class`) — most of this function exists to repair kajson's eager-rehydrate artifacts. Once kajson is bypassed, the `isinstance(raw_item, StuffContent)` branch becomes unreachable for ListContent items; the function simplifies to dict-only handling. (Keep a cautious code path for now and add a regression test that asserts list items arrive as `dict` at hydration time.)

Why this is elegant:

- It recognizes that pipelex's "preserve type metadata for later hydration" was conceptually a *different protocol* from kajson's "auto-rebuild this class instance now". Today they collide because they share a key name; renaming makes them orthogonal.
- Zero kajson changes. The protocol is documented by use: pipelex's dehydration format becomes self-contained and explicitly does not delegate class binding to the data-converter layer.
- The `Anything[]` flow stays exactly the same — pipelex's hydration code still has the metadata it needs, just under different keys.
- Per-workflow scoping is preserved end-to-end. Dynamic classes never need to escape into the global registry.

Risk: external code that reads pipelex's dehydrated payloads and expects `__class__` would break. Grep shows zero such consumers; the only readers are `hydration.py` and the tests under `tests/integration/pipelex/temporal/library_crate/`. Worth a sweep before landing.

### Option B — Make kajson skip unresolvable classes instead of raising

Add a flag (or a registry option) so the decoder, when it cannot resolve a `__class__`, returns the raw dict instead of raising. Pipelex's hydration then does the binding using the per-workflow registry.

Pros:

- Generalizable. Other apps that ship deferred-binding payloads get the same benefit.
- No marker rename; existing dehydrated payloads keep working.

Cons:

- Loses safety: typos and renamed classes silently become raw dicts. Recovering the "loud failure for unknown classes" behavior requires a second signal (a marker prefix? a registry override?).
- The encoder still walks the tree and tries to resolve; we're paying the lookup cost for keys that we *intend* to defer.
- This option *combines well* with A: pipelex uses Option A's private markers, and we additionally harden kajson so accidental `__class__` collisions are not fatal. But Option B alone is the wrong shape.

### Option C — Walk the encoded `PipeOutput` and attach `kajson_class_source` for every nested dynamic class

`BaseModelPayloadConverter` already has a mechanism (`temporal_data_converter.py:65-67`, `:75-77`, `:89-118`) where the encoder attaches `__kajson_class_source__` metadata on the top-level value, and the decoder rebuilds a scoped registry per payload from that source. Today it only fires when `type(value)` itself has `__kajson_class_source__` set. We could extend it to recursively scan the payload, collect every nested dynamic class's source, and ship the union.

Pros:

- Uses an existing kajson-aware mechanism.

Cons:

- O(payload-size) walk at every encode/decode boundary.
- Multi-source payload metadata needs a new shape (today it's a single `bytes` field).
- We are using a heavy hammer for what is structurally a naming collision; Option A is one rename away.
- Doesn't actually need the source if the pipelex marker namespace is private — there is nothing for kajson to bind anymore.

### Option D — Have `WfPipeRun` load the crate before awaiting the child result

Add the crate to `PipeRunArg`, load it into a per-workflow registry inside `WfPipeRun` before line 43, so that when the data converter decodes the child workflow result, the class is in scope.

Pros:

- Conceptually consistent: every workflow that *might* see dynamic-concept payloads has the crate.

Cons:

- `WfPipeRun` becomes registry-aware purely to deserialize its child's return — leaks pipelex semantics into the orchestration layer.
- Doubles the work: both `WfPipeRun` and `WfPipeRouter` would load and tear down the same crate, for the same workflow.
- Doesn't help if a future workflow chain dispatches a child whose return contains dynamic concepts and the parent didn't expect them — Option A solves this structurally; Option D solves it case-by-case.

## Recommended path

Implement **Option A**. Keep Option B in the back pocket as a follow-up kajson hardening once we see the first user-defined collision (it has no value as a fix on its own but is good defense in depth). C and D should be discarded.

### Concrete plan

1. **Rename markers in pipelex.**
   - `pipelex/core/memory/working_memory.py:dump_for_temporal` — write `__pipelex_class__` / `__pipelex_module__`.
   - `pipelex/temporal/tprl_pipe/hydration.py:_hydrate_list_item` and the field-strip filter in `hydrate_content` — read the renamed keys.
2. **Simplify `hydration.py:_validate_as_known_class`.** After the rename, kajson never rehydrates these dicts, so the `isinstance(raw_item, StuffContent)` branch in `_validate_as_known_class` becomes dead for the dehydrated-payload path. Keep it for any direct (non-Temporal) callers but add a code comment explaining the two execution modes.
3. **Add a regression test.** Mirror `tests/integration/pipelex/temporal/tracing/test_split_worker_object_gen.py` but force a true cross-process topology via the test fixture (or assert at hydration time that `raw_item` is a `dict`, not a `StuffContent` instance — which is observable in-process and would have caught this).
4. **Sweep for accidental external consumers.** `grep -rn '"__class__"\|"__module__"' pipelex/ tests/` to make sure no external test or tool reads pipelex's dehydrated format expecting kajson-compatible keys.
5. **Update the Tier 9b expectations in `.claude/skills/temporal-e2e-validate/SKILL.md`.** Today the skill notes that this tier is "covered by the in-process pytest counterpart"; once the fix lands, the CLI form should pass too — drop the disclaimer.

## Verification

After the fix:

1. **Unit-test:** new tests asserting that `WorkingMemory.dump_for_temporal` does not emit `__class__` and that `hydrate_working_memory` reads the renamed keys.
2. **In-process integration test (must still pass):**
   ```bash
   .venv/bin/pytest -x -v tests/integration/pipelex/temporal/tracing/test_split_worker_object_gen.py \
     -m temporal --temporal-server local
   ```
3. **Cross-process e2e (the original failure — must now pass):**
   ```bash
   .venv/bin/pipelex run bundle \
     tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds \
     --pipe generate_invoice_list \
     --temporal --dry-run --mock-inputs --no-logo --graph
   ```
   Expect `✓ Dry run completed successfully` and a `results/generate_invoice_list_output_NN/` directory.
4. **Regression sweep on the broader Temporal suite** (no behavior change expected):
   ```bash
   .venv/bin/pytest -x -v tests/integration/pipelex/temporal/library_crate/ \
     -m temporal --temporal-server local
   ```
   Expect the same 63 passed + 2 xpassed baseline.
5. **Full agent suite:**
   ```bash
   make agent-check
   make agent-test
   ```

## Critical files (reference)

| File | Role |
|------|------|
| `pipelex/core/memory/working_memory.py:472-495` | `dump_for_temporal` — emits the colliding `__class__` markers. The offender. |
| `pipelex/temporal/tprl_pipe/hydration.py` | Pipelex-side hydration; reads the markers. Symmetric counterpart to `dump_for_temporal`. |
| `pipelex/core/pipes/pipe_output.py:28-49` | `PipeOutput.prepare_for_temporal` — moves `working_memory` into `working_memory_raw`. Already correct; not part of the fix. |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py:25-185` | Child workflow that loads the crate, runs the pipe, dehydrates, returns. The crate registry is torn down in `finally`. |
| `pipelex/temporal/tprl_pipe/wf_pipe_run.py:43` | Parent workflow's `await execute_child_workflow(WfPipeRouter.run, ...)` — the exact decode site that fails today. |
| `pipelex/temporal/temporal_data_converter.py` | Pipelex's payload converter; wraps `kajson.dumps` / `kajson.loads` for Temporal. Notice the existing `__kajson_class_source__` mechanism on lines 65-77 / 89-118 — separate from this bug but worth understanding. |
| `kajson/kajson/json_decoder.py:113-194` | `universal_decoder` — the function that eagerly resolves `__class__` and raises `KajsonDecoderError`. |
| `kajson/kajson/json_decoder.py:132` | The exact line that gates "do nothing" vs "resolve class": `if "__class__" not in the_dict: return the_dict`. This is the contract Option A leans on. |
| `tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds` | The repro bundle. Defines a custom `Invoice` concept with nested `Customer` + `LineItem` list. |
| `tests/integration/pipelex/temporal/tracing/test_split_worker_object_gen.py` | In-process pytest counterpart; passes today because of accidental globals reachability. Useful baseline for the regression test. |

## Open question for the implementer

The `__pipelex_class__` / `__pipelex_module__` names are placeholders chosen to make this proposal concrete. A more domain-specific name (`__listcontent_item_class__`, `__concept_item_type__`, …) might be worth a moment of consideration if pipelex plans to use this mechanism in more places. The key requirement is just: **not `__class__`** (or any name kajson reserves now or in the future).
