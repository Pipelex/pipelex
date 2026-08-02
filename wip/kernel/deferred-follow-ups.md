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

**Why it is deferred rather than fixed here.** Two reasons, and the second is the load-bearing one. First, deleting a method plus re-homing 38 test call sites is a substantial change inside a PR whose contract is *zero behavior change* — it would make the diff much harder to read against exactly the claim reviewers need to check. Second, and more importantly, **Phase 2 decides the question for us**: `LLMPromptBlueprint` is still a live field on `PipeLLM` (`llm_prompt_spec`, which the operator reads through `to_prompt_content()`), and the img-gen blueprint shares its reference-extraction shape, so what remains of the blueprint after every operator is re-pointed is not knowable yet. Deleting now risks deleting the wrong half. Revisit at the end of Phase 2, when the blueprint's surviving role is settled: at that point either the method is genuinely dead and goes (with its tests re-pointed at `LlmPromptContent`), or it has re-acquired a caller and stays.

**Scope note, because this item is about a method and not a class.** What is production-dead is `make_llm_prompt`, the assembly method — *not* `LLMPromptBlueprint` itself, which `PipeLLM` holds as a field and which parse-and-validate still needs. An earlier revision of this paragraph named `PipeStructure` as the blueprint's remaining consumer. That was never true on any branch, including `dev` before this work: `pipe_structure.py` has never referenced `LLMPromptBlueprint`. Whoever picks this up should look at `PipeLLM`, and should be deleting one method, not a model.

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

## KF-6 — `StructuringPath` owns three quarters of the tracer's `structuring_path` vocabulary

**Surfaced by** the PR #1081 arbitration pass, reviewing the re-pointed operators for behavior parity. `StructuringPath`'s docstring calls itself "the tracer's vocabulary, owned here rather than at each caller", but `PipeStructure` writes a bare `"structure"` into the same `execution_data["structuring_path"]` key (`pipelex/pipe_operators/structure/pipe_structure.py:172`), and that value has no enum member. So the key the tracer consumes is fed from an enum on one path and a string literal on another.

**Why it is not a bug today.** The literal is pre-existing — it read `"structure"` on `dev` too, and this branch did not touch it. The consumer chain is `dict[str, Any]` end to end (`_register_execution_data` → `GraphTracerManager.register_execution_data` → `node_data.execution_data`), and `StructuringPath` is a `StrEnum`, so both forms serialize to the same JSON string and nothing downstream can tell them apart. Verified: no test data, snapshot or renderer keys on the value.

**Scheduling note — this has no trigger unless one is added.** An earlier draft said "when Phase 2 re-points `PipeStructure` fully, the answer falls out". Phase 2's task list (2.1–2.5) has no `PipeStructure` task, and the plan's own Deviations argue *against* routing it through `run_llm_object`. So nothing currently schedules this. Fold it into whichever Phase-2 task touches `PipeStructure`'s execution data, or settle it at Phase 3 when the kernel docs page has to describe the vocabulary. Extra evidence for leaving the value alone: our graph UI removed its Structuring row on the grounds that `structuring_path` never carried information, so no renderer branches on it in any repo.

**Why it is deferred rather than fixed here.** The right fix depends on a question Phase 2 answers, not this PR: is `"structure"` a *fourth kernel structuring path*, or a pipe-level label that merely shares a dict key? Today it is the latter — `PipeStructure` calls `generate_object_content` directly and builds its own execution data, so the kernel never produces `"structure"` and adding the member now would put a value into a "what the kernel op did" type that no kernel op can return. When Phase 2 re-points `PipeStructure` fully, the answer falls out: either it starts flowing through a kernel entry point that legitimately returns a fourth path (add the member, drop the literal), or it stays a caller-side label (narrow the enum's docstring to say it names the *LLM* paths, not the whole key). Cheap either way; wrong to guess now.

## KF-7 — `PipeCompose`'s construct mode is not kernel-covered, and covering it means relocating an MTHDS blueprint

**Surfaced by** task 2.4 itself. The task read "kernel templating + structured-composition ops"; only the templating half landed.

**Why the construct half did not.** Its semantics are `StructuredContentComposer` over a `ConstructBlueprint`, both under `pipelex/pipe_operators/compose/` — an interpreter package by the closure test's own `INTERPRETER_PACKAGES` predicate, so the kernel cannot import either. There is no adapter shape that avoids this: the composer's *input* is the blueprint. Covering construct mode therefore means moving `construct_blueprint.py` (315 lines of MTHDS field-composition model, with its serializers and validators) and `structured_content_composer.py` (840 lines) into `pipelex/kernel/`, plus the `PipeComposeError` family they raise — which is a `PipelexError` subtree, so it drags `make generate-error-pages` and the `tests/data/errors/error_identity.txt` snapshot with it.

Phase 1's `LLMPromptBlueprint` precedent looks like it points the other way, and does not: there the kernel needed a *small* runtime-layer input model (`LlmPromptContent`) that the blueprint maps down onto. The equivalent here is a near-verbatim second copy of a 315-line blueprint, which is duplication, not layering.

**What the caller loses.** Close to nothing. A programmatic caller holds real Python — it builds its structured object directly rather than describing the construction in a blueprint. The blueprint exists so that `.mthds` can express composition declaratively, which is a language concern with a language-side consumer.

**What was done instead.** The one thing genuinely shared between the two paths — the three-layer context ordering (memory stuffs → run params → step `extra_context`) that both the template path and the construct path's TEMPLATE fields render against — is now single-sourced in `build_compose_context` and called from both. That is the drift this extraction exists to kill; the rest of construct mode was never at risk of forking, because it has exactly one caller.

**When to revisit.** If a second caller of construct-mode composition ever appears, or if `pipelex/kernel/` is packaged as a standalone distribution (a stated non-goal today) and the MTHDS blueprint models get a layer verdict of their own. Note the precedent that would support the move when it comes: `TemplateBlueprint` is also a `.mthds`-parsed artifact and already lives in the runtime layer, under `pipelex/cogt/templating/`.
## KF-16 — The model-derived prompting style is obsolete and should become an explicit choice

**Numbered 16, not 7, deliberately.** This item lands on the *first* PR of a three-PR stack, but the stacked Phase 2 and Phase 3 PRs already add KF-7 through KF-15. Taking the next free number instead of the next sequential one keeps every one of those entries — and the cross-references to them in the plan — exactly as written, so folding this in churns neither of the PRs above it. The gap below is theirs to fill.

**Surfaced by** folding the parity-gaps track's Phase 2 into this stack. That plan listed a gap 2.2 — *"`PipelexKernel.llm_object` renders under the wrong model's prompting style"* — and called it a wrong value. **Re-verified against this branch: that was overstated, and nothing here is broken.**

The façade takes one explicit `model`, which wins `resolve_llm_setting_for_object`'s first rung, so the style is derived from that same setting. That is what an interpreted run derives for a pipe naming only a text model. The two agree for every call this form can express; the divergence needs a pipe naming *both* models, which the façade has no way to say. So 2.2 is the same **narrowness** as the `llm_text` widening that did land here — not a defect.

**Why it is deferred rather than widened.** Giving `llm_object` a second model choice means building the two-setting derivation that the whole mechanism is slated to lose. The owner's call (2026-08-03): deriving the prompting style from the model dates from when models were genuinely sensitive to prompt shape, which no longer holds. The target is an **explicit caller/author-chosen style defaulting to XML**, with the model-derived path removed — which deletes the derivation outright rather than teaching another caller to reproduce it.

**Where the work is written up.** `wip/prompting-style/README.md` — current mechanism, why it goes, target design, open questions (where the choice lives, what happens to `prompting_target`, whether it needs an MTHDS surface and therefore an `mthds/` spec change), and the measured three-case table behind the "not a defect" verdict.

**Recorded in code** as a docstring block on `PipelexKernel.llm_object`, carrying the trap: do *not* "fix" this by deriving the style from an object-only resolution — that would introduce the divergence rather than close it.

## KF-17 — An empty-string model choice falls through to the deck default instead of failing

**Surfaced by** cubic on PR #1081, against `resolve_llm_setting_for_text` / `resolve_llm_setting_for_object` in `pipelex/kernel/llm_ops.py`.

**The gap.** Both resolvers pick the first choice by truthiness — `llm_choice or model_deck.llm_choice_overrides.for_text or model_deck.llm_choice_defaults.for_text`. The parameter is typed `LLMModelChoice | None`, so `is not None` is the check the type describes. The two differ for exactly one value: `""` is falsy, so `llm_text(model="")` runs against the deck default rather than raising.

**Why it is deferred rather than fixed here.** Three reasons, and the first is decisive.

- **It is not this PR's code.** The chain is verbatim what `pipe_llm.py` has on `dev` (`llm_for_text_choice or model_deck.llm_choice_overrides.for_text or …`). The extraction moved it; it did not write it.
- **There is no divergence.** The interpreter now calls these very functions, so both readers resolve identically by construction. Changing the rung would change both together — this is not a parity gap, which is the bar the surrounding track set.
- **Every authored path already rejects it.** `""` reaches a resolver only from a direct Python call. Through pydantic — which is how a `.mthds` model choice, a deck default, and a deck override all arrive — the `parse_model_reference` validator raises `ModelReferenceParseError: Model reference cannot be empty`. The remaining hole is `PipelexKernel.llm_text(model="")` in hand-written code.

**What settling it would take.** Not a one-line swap: the object resolver has three rungs, and a faithful `is not None` version of a mixed None/falsy chain reads considerably worse than the `or` it replaces. Worth doing as part of a deliberate pass over model-choice validation — where the real question is whether `LLMModelChoice` should reject `""` at the type boundary once, instead of every consumer re-checking — rather than as a spot fix in a resolver that is only passing the value along.
