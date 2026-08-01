# Kernel extraction — deferred follow-ups

Items surfaced during the plan's engineering review that are deliberately **not** in this branch's scope. Each carries enough context to pick up cold, and stays here once resolved elsewhere — marked done, rewritten to say what actually landed and what it changes for the plan.

## ✅ KF-1 — Tree-wide mechanical ban on importing from `pipelex.exceptions` in runtime-layer packages — DONE

**What landed.** Done on `dev` (#1080) and merged into this branch — and it went in *tree-wide first* rather than kernel-first, which inverts the dependency this item recorded. `tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py` AST-walks every package declared in `RUNTIME_LAYER_PACKAGES` and fails on any reference to the aggregate: module-level or function-local, absolute or relative, plus any bare string naming it — the `import_module` / `__import__` / `mocker.patch` shape, which no import node records and which this item had not asked for. The feared sweep was empty (the vendor-adapter cleanup had already fixed the only violators), so the gate hard-blocks from day one; the scoping decision came out as predicted — the aggregate stays a legitimate public surface *outside* the runtime layer, and only the layer whose closure it would silently widen is banned. `docs/contribute/hub-layering.md`'s aggregate section now states the rule as mechanical rather than prose.

**What it changes for this branch.** The gate's domain *is* `RUNTIME_LAYER_PACKAGES`, so task 0.1a's declaration of `pipelex.kernel` puts the kernel under it with no kernel-specific test to write — which is why task 0.1c shrank to its prose half. Its negative control survives with a different job: the gate resolves each declared entry to files and silently yields nothing when the path does not resolve, so a mis-declared package is covered by *zero* modules without complaining. That is the "an undeclared package is unpoliced" hazard in a new shape, and the control is what proves the declaration actually bought coverage.

## KF-2 — A library-free caller has no way to mint a `Concept` for its own class

**Surfaced by** writing task 1.7's tests. `llm_object` takes a `concept: Concept` alongside `output_class`, which is the right shape — the kernel must not do a registry hop. But on a process with zero `.mthds` loaded, the only concept a caller can build through a public factory is a native one (`ConceptFactory.make_native_concept`), because everything else resolves through a loaded library. So a caller handing over its own `StuffContent` subclass pairs it with `Native.Anything`, which is what both the unit tests and the boot-contract test do.

**Why it is not a bug today.** For a kernel-only caller the concept is metadata on the produced `Stuff`; nothing in the LLM kernel ops reads it, and nothing answers a compatibility question about it (see the 0.1e vacuity deviation in the plan). The pairing is *loose*, not wrong.

**Why it is deferred rather than fixed here.** The fix is a caller-facing memory-boundary concern, and Phase 3 is where that boundary gets shaped for real (3.1 `shape_inputs`, 3.2 result extraction). Adding a concept-minting factory in Phase 1 would be designing that surface from one test's convenience rather than from the caller experience Phase 3 defines. Revisit at 3.2: if result extraction stays typed on the class, this may need nothing at all; if it keys on concepts, a library-free minting path becomes load-bearing and should be designed then.

## KF-3 — `LLMPromptBlueprint.make_llm_prompt` is now production-dead, held up entirely by its tests

**Surfaced by** the Checkpoint-A cold review, which reported the narrower symptom: the `log.verbose(f"User text with {output_concept_ref=}:\n {user_text}")` diagnostic inside it no longer fires on a live run. That is true, but it is a consequence, not the finding. Verified the real shape: `make_llm_prompt` is defined at `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:63` and called from **tests only** — 38 call sites across `tests/integration/pipelex/pipes/llm_prompt_inputs/` and `tests/unit/pipelex/pipe_operators/pipe_llm/`, and zero in `pipelex/`. The re-point is what killed it: `PipeLLM._live_run_operator_pipe` now calls `to_prompt_content()` and hands that to the kernel, so the blueprint's own assembly method is bypassed.

**Why it is not a bug today.** The method still works and its tests still pass — they are simply testing a path production no longer takes. The equivalent production path is `LlmPromptContent` in the kernel, which those same behaviors are exercised through by the re-pointed interpreter suite. So there is no coverage cliff, only a duplicate.

**Why it is deferred rather than fixed here.** Two reasons, and the second is the load-bearing one. First, deleting a method plus re-homing 38 test call sites is a substantial change inside a PR whose contract is *zero behavior change* — it would make the diff much harder to read against exactly the claim reviewers need to check. Second, and more importantly, **Phase 2 decides the question for us**: `LLMPromptBlueprint` still serves `PipeStructure` and the img-gen blueprint shares its reference-extraction shape, so what remains of the blueprint after every operator is re-pointed is not knowable yet. Deleting now risks deleting the wrong half. Revisit at the end of Phase 2, when the blueprint's surviving role is settled: at that point either the method is genuinely dead and goes (with its tests re-pointed at `LlmPromptContent`), or it has re-acquired a caller and stays.

**If the diagnostic itself is wanted back sooner** — independent of the above — it is a one-line addition in `run_llm_text`/`run_llm_object` in `pipelex/kernel/llm_ops.py`. It was dropped deliberately (recorded under the plan's Deviations: moving it meant either duplicating it or carrying a log-only parameter across the layer boundary), and no one has asked for it; the kernel would log without the `output_concept_ref` the old line carried, since the text arm has no concept ref to name.

## KF-4 — Two `TestClass`es per module in the moved reference-type tests

**Surfaced by** the Checkpoint-A cold review. `tests/unit/pipelex/kernel/test_document_reference.py` holds both `TestDocumentReference` and `TestDocumentReferenceKind`; `test_image_reference.py` has the analogous split. The repo's pytest standards say, twice and in caps, never to put more than one `TestClass` in a module.

**Why it is deferred rather than fixed here.** It is pre-existing — both files moved at 97% similarity with only the import line changed, so the violation was inherited, not introduced. And fixing it *now* has a specific cost that will not apply later: splitting each file into two destroys git's rename detection, turning a reviewable "this moved verbatim" into a delete-plus-add in a PR whose entire claim is that the move is behavior-preserving. That is a bad trade in this PR and a free change in any later one. Do it as a standalone tidy after this series lands — it is mechanical, and `.test_durations` will need the same node-id sweep the plan already records for Phase 2 moves.

## KF-5 — What kernel results do at a serialization boundary is a Phase-3 question

**Surfaced by** Codex on PR #1081, as a P1 against `LlmObjectResult.content`: the field is annotated with the base `StuffContent`, so pydantic v2 serializes it by the annotation and a `NumberContent(number=3)` dumps as `{}`.

**The behavior is real; the framing as a new defect is not.** Verified empirically, and the decisive comparison is `Stuff.content` — the codebase's canonical polymorphic content holder, annotated identically, and the one that genuinely crosses Temporal boundaries today:

```
Stuff.content plain model_dump  : {}
Stuff.content serialize_as_any  : {'number': 3}
Stuff kajson round-trip type    : NumberContent 3
```

So the kernel result is behaving exactly like the type it mirrors, and the project's answer at both sites is already in place: `kajson` (which records the class and reconstructs it) is what actually crosses process boundaries, and `model_dump(serialize_as_any=True)` covers a one-off dump. There are **zero** `SerializeAsAny` annotations in the tree — adding one here alone would introduce a pattern that exists nowhere else and would make the kernel result inconsistent with `Stuff`.

**Why nothing is changed beyond a docstring.** Nothing serializes `LlmObjectResult` or `LlmTextResult` today: they are built in `llm_ops.py` and unwrapped inline by `PipeLLM`/`PipeStructure`, and there is no `model_dump`/`kajson` call anywhere in `pipelex/kernel/`. Fixing a corruption on a path no caller takes is guarding an impossible scenario. What *was* added is a note in the module docstring, because the kernel is aimed at programmatic callers and "call `model_dump()` on the result you were handed" is a plausible caller mistake in a way it is not for an internal type.

**When it becomes real.** Phase 3 shapes the caller-facing boundary (3.1 `shape_inputs`, 3.2 result extraction). If kernel results are ever handed across a process, API or cache boundary there, this is the moment to decide deliberately — and the answer should almost certainly be "serialize with `kajson`, like everything else that crosses", not a bespoke annotation on one field. Revisit at 3.2 alongside KF-2, which is the same boundary seen from the input side.
