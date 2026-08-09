# Kernel extraction — deferred follow-ups

Items surfaced during the plan's engineering review that are deliberately **not** in this branch's scope. Each carries enough context to pick up cold, and stays here once resolved elsewhere — marked done, rewritten to say what actually landed and what it changes for the plan.

## ✅ KF-1 — Tree-wide mechanical ban on importing from `pipelex.exceptions` in runtime-layer packages — DONE

**What landed.** Done on `dev` (#1080) and merged into this branch — and it went in *tree-wide first* rather than kernel-first, which inverts the dependency this item recorded. `tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py` AST-walks every package declared in `RUNTIME_LAYER_PACKAGES` and fails on any reference to the aggregate: module-level or function-local, absolute or relative, plus any bare string naming it — the `import_module` / `__import__` / `mocker.patch` shape, which no import node records and which this item had not asked for. The feared sweep was empty (the vendor-adapter cleanup had already fixed the only violators), so the gate hard-blocks from day one; the scoping decision came out as predicted — the aggregate stays a legitimate public surface *outside* the runtime layer, and only the layer whose closure it would silently widen is banned. `docs/contribute/hub-layering.md`'s aggregate section now states the rule as mechanical rather than prose.

**What it changes for this branch.** The gate's domain *is* `RUNTIME_LAYER_PACKAGES`, so task 0.1a's declaration of `pipelex.kernel` puts the kernel under it with no kernel-specific test to write — which is why task 0.1c shrank to its prose half. Its negative control survives with a different job: the gate resolves each declared entry to files and silently yields nothing when the path does not resolve, so a mis-declared package is covered by *zero* modules without complaining. That is the "an undeclared package is unpoliced" hazard in a new shape, and the control is what proves the declaration actually bought coverage.

## KF-2 — A library-free caller has no way to mint a `Concept` for its own class

**Surfaced by** writing task 1.7's tests. `llm_object` takes a `concept: Concept` alongside `output_class`, which is the right shape — the kernel must not do a registry hop. But on a process with zero `.mthds` loaded, the only concept a caller can build through a public factory is a native one (`ConceptFactory.make_native_concept`), because everything else resolves through a loaded library. So a caller handing over its own `StuffContent` subclass pairs it with `Native.Anything`, which is what both the unit tests and the boot-contract test do.

**Why it is not a bug today.** For a kernel-only caller the concept is metadata on the produced `Stuff`; nothing in the LLM kernel ops reads it, and nothing answers a compatibility question about it (see the 0.1e vacuity deviation in the plan). The pairing is *loose*, not wrong.

**Why it is deferred rather than fixed here.** The fix is a caller-facing memory-boundary concern, and Phase 3 is where that boundary gets shaped for real (3.1 `shape_inputs`, 3.2 result extraction). Adding a concept-minting factory in Phase 1 would be designing that surface from one test's convenience rather than from the caller experience Phase 3 defines. Revisit at 3.2: if result extraction stays typed on the class, this may need nothing at all; if it keys on concepts, a library-free minting path becomes load-bearing and should be designed then.

**Phase-3 verdict: nothing is owed, and the deferral was right.** Result extraction stayed typed on the class — `extract_main_content` / `extract_named_content` take a `content_type`, never a concept — so no kernel *read* path asks a concept question, and the branch KF-2 was watching for ("if it keys on concepts") did not happen. The input side turned out to have a shape the item did not anticipate: `shape_inputs` takes a `ConceptProviderAbstract` explicitly, so a library-free caller supplies its own, and `test_kernel_boot_contract.py` now carries the smallest one that works (native concepts from `ConceptFactory`, compatibility from `Concept.are_compatible_by_declaration`, structure classes from the class registry a boot fills). That is a *provider*, not a concept-minting factory — a caller wanting a genuinely non-native concept for its own class still has to declare one, which is what an author writing `.mthds` does. Nothing in the kernel needs it, so nothing is built. Revisit only if a kernel path ever answers a compatibility question about a caller's own concept, which the 0.1e routing rule would then govern.

## KF-3 — `LLMPromptBlueprint.make_llm_prompt` is now production-dead, held up entirely by its tests

**Surfaced by** the Checkpoint-A cold review, which reported the narrower symptom: the `log.verbose(f"User text with {output_concept_ref=}:\n {user_text}")` diagnostic inside it no longer fires on a live run. That is true, but it is a consequence, not the finding. Verified the real shape: `make_llm_prompt` is defined at `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:63` and called from **tests only** — 38 call sites across `tests/integration/pipelex/pipes/llm_prompt_inputs/` and `tests/unit/pipelex/pipe_operators/pipe_llm/`, and zero in `pipelex/`. The re-point is what killed it: `PipeLLM._live_run_operator_pipe` now calls `to_prompt_content()` and hands that to the kernel, so the blueprint's own assembly method is bypassed.

**Why it is not a bug today.** The method still works and its tests still pass — they are simply testing a path production no longer takes. The equivalent production path is `LlmPromptContent` in the kernel, which those same behaviors are exercised through by the re-pointed interpreter suite. So there is no coverage cliff, only a duplicate.

**Why it is deferred rather than fixed here.** Two reasons, and the second is the load-bearing one. First, deleting a method plus re-homing 38 test call sites is a substantial change inside a PR whose contract is *zero behavior change* — it would make the diff much harder to read against exactly the claim reviewers need to check. Second, and more importantly, **Phase 2 decides the question for us**: `LLMPromptBlueprint` is still a live field on `PipeLLM` (`llm_prompt_spec`, which the operator reads through `to_prompt_content()`), and the img-gen blueprint shares its reference-extraction shape, so what remains of the blueprint after every operator is re-pointed is not knowable yet. Deleting now risks deleting the wrong half. Revisit at the end of Phase 2, when the blueprint's surviving role is settled: at that point either the method is genuinely dead and goes (with its tests re-pointed at `LlmPromptContent`), or it has re-acquired a caller and stays.

**Scope note, because this item is about a method and not a class.** What is production-dead is `make_llm_prompt`, the assembly method — *not* `LLMPromptBlueprint` itself, which `PipeLLM` holds as a field and which parse-and-validate still needs. An earlier revision of this paragraph named `PipeStructure` as the blueprint's remaining consumer. That was never true on any branch, including `dev` before this work: `pipe_structure.py` has never referenced `LLMPromptBlueprint`. Whoever picks this up should look at `PipeLLM`, and should be deleting one method, not a model.

**Scheduling note after Phase 3.** Its trigger — "the end of Phase 2, when the blueprint's surviving role is settled" — passed unexercised, and Phase 3 touches neither the blueprint nor its tests, so nothing schedules this now. The blueprint's role *is* settled (Phase 2 moved no prompt assembly onto it, and `PipeLLM` still holds it as `llm_prompt_spec`), so the question is answerable: `make_llm_prompt` is genuinely dead in production and its tests belong on `LlmPromptContent`, while the blueprint model itself stays. Do it in the same standalone tidy as KF-4, after this series lands — both are mechanical, both are cheaper once no PR is claiming a verbatim move.

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

**Phase-3 verdict: unchanged, because 3.2 read the results in-process.** `extract_main_content` / `extract_named_content` narrow a result's content by type on the caller's own stack; nothing in Phase 3 dumps or transports a kernel result, so the path this describes still has no caller. The docstring note stays as the caller-facing warning it was. The trigger is now genuinely external — the first time a host hands a kernel result across a process, API or cache boundary — rather than a phase of this plan.

## ✅ KF-6 — `StructuringPath` owns three quarters of the tracer's `structuring_path` vocabulary — SETTLED IN PHASE 3

**Surfaced by** the PR #1081 arbitration pass, reviewing the re-pointed operators for behavior parity. `StructuringPath`'s docstring calls itself "the tracer's vocabulary, owned here rather than at each caller", but `PipeStructure` writes a bare `"structure"` into the same `execution_data["structuring_path"]` key (`pipelex/pipe_operators/structure/pipe_structure.py:172`), and that value has no enum member. So the key the tracer consumes is fed from an enum on one path and a string literal on another.

**Why it is not a bug today.** The literal is pre-existing — it read `"structure"` on `dev` too, and this branch did not touch it. The consumer chain is `dict[str, Any]` end to end (`_register_execution_data` → `GraphTracerManager.register_execution_data` → `node_data.execution_data`), and `StructuringPath` is a `StrEnum`, so both forms serialize to the same JSON string and nothing downstream can tell them apart. Verified: no test data, snapshot or renderer keys on the value.

**Scheduling note — this has no trigger unless one is added.** An earlier draft said "when Phase 2 re-points `PipeStructure` fully, the answer falls out". Phase 2's task list (2.1–2.5) has no `PipeStructure` task, and the plan's own Deviations argue *against* routing it through `run_llm_object`. So nothing currently schedules this. Fold it into whichever Phase-2 task touches `PipeStructure`'s execution data, or settle it at Phase 3 when the kernel docs page has to describe the vocabulary. Extra evidence for leaving the value alone: our graph UI removed its Structuring row on the grounds that `structuring_path` never carried information, so no renderer branches on it in any repo.

**Why it was deferred rather than fixed then.** The right fix depended on a question Phase 2 answers: is `"structure"` a *fourth kernel structuring path*, or a pipe-level label that merely shares a dict key? Either it starts flowing through a kernel entry point that legitimately returns a fourth path (add the member, drop the literal), or it stays a caller-side label (narrow the enum's docstring to say it names the *LLM* paths, not the whole key). Cheap either way; wrong to guess before the answer was in.

**What landed (Phase 3).** The second arm, because Phase 2 settled the premise: its Deviations record `PipeStructure` riding the kernel's *pieces* rather than `run_llm_object`, so it calls `generate_object_content` and builds its own execution data — no kernel op can return `"structure"`, and adding the member would put a value into a "what the kernel op did" type that nothing here produces. `StructuringPath`'s docstring now says it names the LLM paths and states why the sibling literal has no member. The literal in `pipe_structure.py` is untouched: the key is `dict[str, Any]` end to end, `StructuringPath` is a `StrEnum`, and nothing downstream can tell the two forms apart — our graph UI removed its Structuring row precisely because the value never carried information.

## KF-7 — `PipeCompose`'s construct mode is not kernel-covered, and covering it means relocating an MTHDS blueprint

**Surfaced by** task 2.4 itself. The task read "kernel templating + structured-composition ops"; only the templating half landed.

**Why the construct half did not.** Its semantics are `StructuredContentComposer` over a `ConstructBlueprint`, both under `pipelex/pipe_operators/compose/` — an interpreter package by the closure test's own `INTERPRETER_PACKAGES` predicate, so the kernel cannot import either. There is no adapter shape that avoids this: the composer's *input* is the blueprint. Covering construct mode therefore means moving `construct_blueprint.py` (315 lines of MTHDS field-composition model, with its serializers and validators) and `structured_content_composer.py` (840 lines) into `pipelex/kernel/`, plus the `PipeComposeError` family they raise — which is a `PipelexError` subtree, so it drags `make generate-error-pages` and the `tests/data/errors/error_identity.txt` snapshot with it.

Phase 1's `LLMPromptBlueprint` precedent looks like it points the other way, and does not: there the kernel needed a *small* runtime-layer input model (`LlmPromptContent`) that the blueprint maps down onto. The equivalent here is a near-verbatim second copy of a 315-line blueprint, which is duplication, not layering.

**What the caller loses.** Close to nothing. A programmatic caller holds real Python — it builds its structured object directly rather than describing the construction in a blueprint. The blueprint exists so that `.mthds` can express composition declaratively, which is a language concern with a language-side consumer.

**What was done instead.** The one thing genuinely shared between the two paths — the three-layer context ordering (memory stuffs → run params → step `extra_context`) that both the template path and the construct path's TEMPLATE fields render against — is now single-sourced in `build_compose_context` and called from both. That is the drift this extraction exists to kill; the rest of construct mode was never at risk of forking, because it has exactly one caller.

**When to revisit.** If a second caller of construct-mode composition ever appears, or if `pipelex/kernel/` is packaged as a standalone distribution (a stated non-goal today) and the MTHDS blueprint models get a layer verdict of their own. Note the precedent that would support the move when it comes: `TemplateBlueprint` is also a `.mthds`-parsed artifact and already lives in the runtime layer, under `pipelex/cogt/templating/`.

## KF-8 — `PipeFunc`'s executor seam is not kernel-carried, so a kernel `run_func` always runs in this process

**Surfaced by** task 2.5 itself. The task read "kernel function-call op over the `PipeFuncExecutorProtocol` seam ... the kernel op must carry **both arms**"; the call and the write-back landed, the seam did not.

**Why the seam did not.** Neither arm's type survives the layer boundary. `PipeFuncExecutorProtocol.run_pipe_func` declares `pipe_run_params: PipeRunParams` and `run_pipe_func_transported` is typed on `PipeFuncExecutionRequest`, which carries a `LibraryCrate`. `pipe_run` and `libraries` are both interpreter packages, and the task's own analysis rules out moving those two models as far outside Phase 2. So the kernel cannot name the protocol it was told to take as an argument.

**The two ways to satisfy the letter, and why neither was taken.**

- *Re-type the protocol off `PipeRunParams`.* Cheap in this tree — nothing in it reads the parameter, including `DirectPipeFuncExecutor` — but it is not a cleanup, it is a wire-format change: both out-of-tree implementers (our Daytona sandbox plugin and our Temporal plugin) thread `pipe_run_params` straight onto `PipeFuncExecutionRequest`, which crosses a process boundary. Two repos this tree's CI cannot see would break at the same time, and the honest first question — *does anything downstream ever read it?* — is not answerable from here.
- *A kernel-side narrow protocol plus an interpreter-side adapter.* Buys a second protocol for one seam, an adapter class binding `pipe_run_params`, and a result-model conversion at the boundary — to compose two calls. Against a "no over-engineering" bar that is the more expensive of the two, not the safer one.

**What was done instead.** The split follows what is actually shared. `call_registered_function` holds what running a function *means* — registry lookup, async-vs-sync dispatch, the str/list→`StuffContent` coercion — and both the in-process executor and the kernel's own `run_func` ride it, so the executor and a programmatic caller cannot fork on it. `store_result` holds the write-back, which `PipeFunc` now rides too. What stays interpreter-side is *where the function runs*, which is configured deployment machinery rather than operator semantics.

**What the caller loses, stated plainly.** A programmatic caller cannot ask the kernel to run its function in a sandbox: `run_func` is the in-process path, full stop. And `run_func` has no in-tree caller — `PipeFunc` rides the pieces, not the composition — which is why it carries its own kernel unit tests rather than leaning on the zero-behavior-change suite.

**When to revisit.** Whenever `pipe_run_params` on the executor seam is settled on its own merits — the question is whether a serialized PipeFunc request needs the run params at all, and it wants an answer coordinated across the three repos, not a drive-by narrowing here. Phase 3's `JobMetadata` task (3.3) is the natural moment: it is already the task that asks what run-scoped state a kernel call carries, and this is the same question asked at the one seam that serializes it.

**Phase-3 verdict: still deferred, and 3.3 sharpened the argument rather than answering it.** 3.3 settled what run-scoped state a kernel call carries — a per-step `JobMetadata` (identity plus an optional `TraceContext`) and a `CogtRunParams`, and *not* a `PipeRunParams`. That is a point in favour of narrowing the executor protocol, since the pipe-tier params on it are the one thing the kernel could never supply — but it does not answer the question the narrowing rests on ("does anything downstream read them?"), which is only answerable from the two out-of-tree implementers. Unchanged: this is a cross-repo wire-format decision, not a kernel one. The trigger is a coordinated pass over pipelex + our Daytona and Temporal plugins.

## KF-9 — Two constructors build `ImgGenJobParams` from the same config defaults with different derivation rules

**Surfaced by** cubic on PR #1082, against `build_img_gen_job_params` in `pipelex/kernel/img_gen_ops.py`: a transparent background with no step-level `output_format` builds params that fail `ImgGenJobParams.validate_background_vs_output_format`.

**The asymmetry is real.** `ImgGenJobParamsDefaults.make_img_gen_job_params` (`pipelex/cogt/img_gen/img_gen_job_components.py`) derives `output_format = ImageFormat.PNG` when `self.background.is_certainly_transparent`; the kernel's `build_img_gen_job_params` passes `output_format` straight through. Both read the same `img_gen_param_defaults`, and both are live — the defaults constructor is the fallback in `content_generator.py` and `img_gen_job_factory.py`.

**Why it is not a regression.** The pre-refactor `PipeImgGen._live_run_operator_pipe` constructed `ImgGenJobParams(...)` inline with the identical `output_format=self.output_format`; the operator path never went through `make_img_gen_job_params`. Verified against `git show refactor/Kernel:pipelex/pipe_operators/img_gen/pipe_img_gen.py`. The behavior moved unchanged.

**Reachability.** The shipped default is `background = "auto"`, so it does not fire out of the box. It fires under a `.pipelex/pipelex.toml` override of `[cogt.img_gen_config.img_gen_param_defaults] background = "transparent"`, which would then break every `PipeImgGen` that omits `output_format`. Note the same failure is already reachable today with no config override at all, via a step-level `background = "transparent"` with no `output_format` — so a fix confined to the config path would not close the case.

**Why it is deferred rather than fixed here.** Re-deriving PNG inside `build_img_gen_job_params` would make a currently-failing configuration start working — a behavior change inside a zero-behavior-change PR — and it is the wrong-shaped fix. The defect is that *two* constructors of the same type read the same defaults with divergent rules, which is precisely the duplication this extraction exists to kill. Single-source them; do not patch one side. Failure today is loud and well-worded, not silent corruption, so nothing is at risk in the meantime.

## KF-10 — `max_results` reaches a provider unvalidated because the constraint sits on the wrong model

**Surfaced by** cubic on PR #1082, against `resolve_search_setting` in `pipelex/kernel/search_ops.py`: `search_setting.model_copy(update={"max_results": max_results_override})` skips validation, because pydantic v2's `model_copy` does no validation by design.

**The chain is genuinely unconstrained end to end.** `PipeSearchBlueprint.max_results` is `int | None = None` with no `ge`; `PipeSearchFactory.make` passes it through to `PipeSearch.max_results_override`, also unconstrained; only `SearchSetting.max_results` carries `Field(default=None, ge=1)`, and the `model_copy` is what bypasses it. So `max_results = 0` in a `.mthds` reaches a search provider.

**Why it is not a regression.** Identical on the base branch, step 4 of `PipeSearch._live_run_operator_pipe`. Verified against `git show refactor/Kernel:pipelex/pipe_operators/search/pipe_search.py`.

**Why it is deferred rather than fixed here, and why the obvious fix is the wrong one.** Revalidating the copy (the bot's suggestion) would raise a pydantic `ValidationError` deep inside the search run path, with no `.mthds` locator to tell the author which step is wrong — trading an unvalidated value for a bad diagnostic. The constraint belongs on `PipeSearchBlueprint.max_results` as `Field(default=None, ge=1)`, where it is caught at validation time with a proper error. That changes the MTHDS JSON Schema and drags the committed downstream copies (`mthds/`, `vscode-pipelex/`, `mthds-ui/`) with it, which is unambiguously outside a zero-behavior-change refactor. Do it as a standalone language-surface change with the schema regeneration and the cross-repo sweep in the same PR.

**Phase-3 verdict (shared with KF-12): the conclusion holds, and 3.1 did not turn out to be its home.** Both items were scheduled onto task 3.1 as "the task that decides what a kernel entry point does with a malformed argument". 3.1 answered that for what it actually governs — the *memory* boundary — and the answer is: reject at the boundary with a typed error that names the variable and renders the expected shape, which is what `InputShaper` already does and what `shape_inputs` now hands both callers. Neither `max_results` nor `nb_images` passes through that boundary: they are operator arguments, not memory inputs, so 3.1 has no reach over them. The conclusion both items had already reached is unchanged, and nothing in this plan blocks it any longer — the constraint belongs upstream on the blueprint, caught at validation time with a locator, in one standalone language-surface PR that carries the schema regeneration and the cross-repo sweep.

## KF-11 — `PipeImgGen`'s `seed` is documented language surface that no image-generation provider reads

**Surfaced by** verifying cubic's P2 against `build_img_gen_job_params`, which reported that `seed or img_gen_param_defaults.seed` discarded an explicit `0`. That part was true and is **fixed in PR #1082** — the line now reads `seed if seed is not None else …`, matching the `is_raw` line below it. The larger fact came out of checking the claimed impact.

**The seed is inert.** `seed` is a declared `PipeImgGen` blueprint field (therefore in the published MTHDS JSON Schema), it is validated (`ImgGenJobParams.seed`, `ge=0`), and it is composed into `ImgGenJobParams` on every image-generation run — and no img-gen worker reads it. Grepping `job_params.seed` across every worker under `pipelex/providers/*/` finds exactly one image-generation reference, and it is commented out: `pipelex/providers/google/google_img_gen_worker.py`. (The live hits are all `LLMJobParams.seed`, a different field on a different job type.) Which is why the `0` fix is observationally a no-op and does not dent the PR's zero-behavior-change claim.

**The failure a user hits.** They write `seed = 12345` in a `PipeImgGen` step to reproduce an image, run it twice, and get two different images — no error, no warning, nothing indicating the parameter was discarded.

**Why it is deferred rather than fixed here.** It is pre-existing, entirely outside the kernel extraction, and the fix is per-provider plumbing (each SDK spells the seed differently, and not all of them accept one) plus a decision about what to do for backends that cannot honor it — reject at validation, or document the field as best-effort. Both are product calls. Recorded here because this is where it was found; it belongs in the img-gen backlog rather than the kernel one.

## KF-12 — `run_img_gen` treats a non-positive `nb_images` as one image, and what it *should* do is a Phase-3 question

**Surfaced by** Codex on PR #1082 (P2): `nb_images=0` or a negative count falls through the `if nb_images > 1:` fork to `make_single_image`, so an invalid request generates one billable image instead of being rejected.

**Why it is not a regression.** The fork is byte-identical to the base branch — `git show refactor/Kernel:pipelex/pipe_operators/img_gen/pipe_img_gen.py` has the same `if nb_images > 1:` at line 268, with the same `make_image_list` / `make_single_image` arms. The multiplicity derivation above it also moved unchanged: `nb_images = applied_output_multiplicity` whenever that is an `int`, with no lower bound anywhere on the way in.

**Why it is deferred rather than fixed here, and this one is genuine doubt rather than scope.** There is no zero-behavior-change fix available. Unlike the `run_search` signature narrowing in this PR — where the ignorable fields could simply be removed from the signature — `nb_images` is an `int` and plain Python cannot express `int >= 1` at the boundary, so any fix *adds an error path* to a PR whose contract is that it adds none. And the fix's shape is not obvious: `nb_images=0` could defensibly mean "reject this request" or "produce an empty `ListContent`", and picking between them from a bot comment rather than from the caller experience is exactly the mistake KF-2 records. Phase 3's task 3.1 (`shape_inputs`) is the task that decides what a kernel entry point does with a malformed argument; settle it there, for all the ops at once, rather than one `int` at a time.

**Worth noting on the way.** The interpreter path can reach it too — nothing between a `.mthds` `nb_output` and `nb_images` constrains the value — so if the answer turns out to be "reject", the constraint most likely belongs upstream on the blueprint, the same conclusion KF-10 reaches about `max_results`. The two should be settled together.

**Phase-3 verdict: see KF-10.** 3.1 settled the malformed-argument question for the memory boundary only, which `nb_images` does not cross. Both items stay together, and their shared home is the standalone blueprint-constraint PR described there.

## KF-13 — a DRY run's usage records carry no `pipe_code`, so a `--mock-usage` cost report has no pipe attribution

**Surfaced by** writing task 3.3's parity test, which expected `pipe_code` to be the one field an interpreter run fills and a kernel run cannot. It is not filled on either side, and the reason is on the interpreter's side.

**The gap.** `pipe_code` reaches a usage record through `JobMetadata`, and the only place it is stamped is `PipeAbstract.live_run_pipe`, which mints the child metadata with `pipe_code=self.code`. A `run_mode=DRY` run never reaches it — `_run_pipe_traced` matches on the run mode and routes to `dry_run_pipe`, which passes the metadata down untouched. So every usage record a dry run produces has `pipe_code=None`, and a `--dry-run --mock-usage` cost report attributes nothing to a pipe.

**Why it is not urgent.** It bites only the mock-usage cost report, which exists to validate cross-worker cost-report *rendering* cheaply — the numbers are synthetic either way. A LIVE run, where attribution matters and money is real, stamps it correctly. Nothing silently misattributes; the field is simply absent.

**Why it is deferred rather than fixed here.** It is pre-existing, entirely interpreter-side, and untouched by the kernel extraction — verified on the base branch, where `dry_run_pipe` has the same shape. Fixing it means moving (or duplicating) the child-metadata mint above the LIVE/DRY fork in `_run_pipe_traced`, which changes what every dry run's metadata carries: a behavior change inside a zero-behavior-change PR, on a path the graph tracer also reads. It belongs with whoever next works on the dry-run observability surface. The parity test pins the current reality on both sides so the fix will show up there as a diff rather than as a silent divergence.

## KF-14 — `UsageReportEvent.node_id` has no readers, which is why a kernel run's flat node state is not a bug yet

**Surfaced by** cubic on PR #1083 (P2), which argued that `PipelexKernel.make_step_metadata` inherits the run-level `TraceContext` unchanged, so every step of a multi-call kernel run carries `node_sequence=0` and `parent_node_id=None` — and concluded that a multi-step run's usage records would collide onto one node. The cold `/code-review` raised the same point independently.

**Rejected as a code change, on measurement.** Two kernel LLM calls under one `TraceContext` produce two events and two records with the correct token total, on both emit paths (the registered-context fast path and the runner fallback). Nothing collides, because nothing on that path keys on the node: the event log's dedup key is `(workflow_id, writer_id, event type, sequence)` with `sequence` coming from a lock-guarded per-log counter, `UsageAggregator.aggregate` is a flat filter-and-map with no grouping, and `TokensUsageRecord` has no `node_id` field at all — so it never reaches `/execute`'s `tokens_usages` or `tokens_usages.json`.

**The fact worth recording, because it is what makes the whole class of finding moot.** `UsageReportEvent.node_id` has no *production* reader. The only other consumer of `UsageReportEvent` in the tree is `GraphSpecAssembler`, which matches it and does nothing (`pass  # Handled by UsageAggregator`); across the sibling repos, the sole non-test hits declare the type or list it in an ignore tuple. Two tests do read it — `tests/unit/pipelex/reporting/test_reporting_event_emission.py` asserts both the `"unknown"` fallback and a supplied `graph:node_42` — which strengthens rather than weakens the point: the first of those is the existing pin on exactly the behavior this item defends. A kernel run also emits no graph events — the graph tracer is interpreter-side and a leaf call does not pass through it — so the field's value is unobservable from a kernel call by any route available today.

**Why advancing the sequence would be worse than leaving it.** A kernel run has no graph. `"unknown"` states that honestly; minting `graph_id:node_0`, `graph_id:node_1` would manufacture references to nodes that exist in no `GraphSpec`, and put them into a field nothing reads. Two of cubic's supporting mechanisms were also wrong on inspection: `copy_with_update` applies its update values by reference *after* the deep copy rather than deep-copying them, and `make_node_id()` is never called on the usage path at all.

**What would reopen it.** Node identity becomes load-bearing the moment something reads it — graph-shaped tracing extended to kernel runs, or a consumer that groups usage events by node. At that point the answer is not a per-step sequence invented by the kernel but a decision about what a node *means* for a caller that has no graph, and it should be settled alongside whoever introduces the reader.

## KF-15 — `Stuff.as_list_of_fixed_content_type` documents an exception it does not raise

**Surfaced by** wiring the kernel's list-extraction helpers onto it, which meant reading what it actually raises in order to write their own `Raises:` sections honestly.

**The gap.** Its docstring documents `Raises: TypeError` (`pipelex/core/stuffs/stuff.py`). It raises `StuffContentTypeError`, via `content_as` and `verify_content_type`, like every other typed accessor on `Stuff`. A caller who writes `except TypeError` around it catches nothing — `StuffContentTypeError` descends from `StuffError`, not from `TypeError`.

**Why it is deferred rather than fixed here.** Pre-existing, one line, and in `pipelex/core/stuffs/` rather than on the kernel surface this PR is scoped to. Worth folding into whatever next touches those accessors; the same pass should check the sibling docstrings in that module for the same error, since this one was found by reading a single function rather than by sweeping.

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
