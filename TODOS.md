# The follow-ups #1076 deferred, in the order they had to happen

Branch `refactor/Follow-ups`, off `dev` at #1076. Three items, ruled to run 2 → 4 → 3 for a reason worth stating up front: item 4 *removes* an in-process conversion, so item 3's audit of the surviving conversions is only meaningful after it — and item 2 first, because both of the others needed a single home for the contract they were about to change. (The numbering is #1076's, kept so the deferral notes still line up. Its item 1 — func-registry entries outliving their library — is untouched here and stays its own later PR.)

This file is the review guide. The part most worth a reviewer's time is at the end of item 4: the live structured-search path turned out to be **broken today**, in a way none of the deferral notes predicted, and fixing it is what makes item 4 correct rather than merely wider.

---

## Item 2 — one home for "convert a leaf result into the caller's class"

### What was wrong

The same conversion existed four times across two repos: `_revalidate_against_object_class` in `content_generator.py`, a copy of it in our distributed-execution plugin's workflow arm, and a dict-shaped inline in each repo's `make_search_structured`. All four implement one contract — validate the leaf's data against the caller's original class, and on the dry path re-raise the `ValidationError` as `DryRunObjectFidelityError` naming the class and the `examples` / `mock_format` remedy.

The copies existed for one reason only: the original was `_`-private, so the plugin could not import it — even though it already imports `assignment_models`, `content_generator_protocol` and `exceptions` from that same package.

#1076 then made them **diverge**: core's copy gained the `isinstance` short-circuit, the plugin's did not. That is correct today — across `workflow.execute_activity` the object is always an instance of the class kajson rebuilt from `__kajson_class_source__`, never of `object_class` — but it is a latent trap, and the reasoning for why the check is `isinstance` and not `type(...) is` lived only in core's docstring.

### What landed

`pipelex/cogt/content_generation/object_revalidation.py`, a leaf module beside `object_class_resolution.py`. The two are the down leg and the up leg of the same journey, which is why they are siblings rather than one module.

- `revalidate_leaf_object(raw_obj, *, object_class, is_mock_built, dump_mode="python")` — the object arm, carrying the short-circuit.
- `revalidate_leaf_data(raw_data, *, object_class, is_mock_built)` — the data arm. Data is never an instance of anything, so there is no short-circuit to make and its validation is the single one on its path.

The object arm delegates to the data arm, so the tree has exactly one `model_validate` call and one `except ValidationError` for this contract. The dry/live split is a branch inside that single `except`, rather than the two separate validate calls all four copies carried.

**`dump_mode` is a parameter, not a unification.** Json mode coerces values (`datetime` → `str` and back); the in-process path must keep `"python"`. That was the deferral note's explicit instruction, and item 3 is why.

### Worth a reviewer's attention

- **The short-circuit now reaches the plugin's boundary path, where it never fires.** Intentional, not an oversight: it is dead code there today and exists so that a boundary which ever *does* hand back the caller's real class — a local activity, an in-process shortcut, a converter change — cannot silently reinstate the double validation. `test_instance_short_circuits_in_either_dump_mode` pins it in both modes.
- **A LIVE `ValidationError` passes through untouched, on purpose.** The plugin's `make_search_structured` catches exactly that to convert it into a terminal typed error, because a bare `ValidationError` raised in workflow code is neither a workflow-execution error nor a `PipelexError`, so the host runtime treats it as a workflow-task failure and retries it forever — hanging the submitter. Had the shared helper swallowed or re-typed it, that conversion would have gone quiet. `test_live_data_failure_keeps_its_validation_error` pins the half of the contract that lives here.
- **The plugin still carries its copies, and must.** It pins a released `pipelex` from PyPI, so it cannot import the new module until this ships. The swap is written up in the workspace notes, outside this repo.

---

## Item 4 — the in-process structured-*search* path still rebuilt the output class

### What was wrong

`make_search_structured` held the caller's `output_structure_class` and never threaded it down, so `PipeSearch` with a structured output still handed the provider a class rebuilt from JSON schema — losing the custom validators, the `json_schema_extra` hints, and the output structure's own description, exactly as #1076 established for the object paths. Same defect, same shape, one remaining path.

### Why it was not "four lines"

The search leaf is **dict-out by contract** — that is what keeps a dynamic class off a distributed orchestrator's wire — and the submitter's re-validation of that dict is the single validation on the live path. Mirroring the object path naively breaks that in the dry arm: `dry_search_gen_structured` builds the mock and *dumps it*, so a mock built from the real class would have the caller's validators run at build **and again** on the dump. A transforming validator would produce `INV-INV-…` — the defect #1076 fixed on the object path with the `isinstance` short-circuit, which cannot apply once the instance has become a dict.

### What landed

Two entry points rather than one nullable parameter, because the two arms genuinely return different things:

- `search_gen_structured(search_object_assignment) -> dict[str, Any]` — the boundary arm. Unchanged signature, unchanged return, so **the activity that calls it needs no change at all**.
- `search_gen_structured_object(search_assignment, *, output_class) -> BaseModelTypeVar` — the in-process arm. The class goes down to the provider; an instance of it comes back, validated once at the leaf. It takes the plain `SearchAssignment`, not the wire model: nothing crosses a boundary in-process, so there is no schema to ship — and building the `SearchObjectAssignment` anyway would pay a `model_json_schema()` per call for a field nothing reads.

`dry_search_gen_structured_object` is the dry counterpart and returns the mock *instance*, not a dump of it. That is the double-validation fix, and its docstring says so in those terms.

No search-side resolution helper survived review: once the in-process arm carries the class outright, a `resolve_search_output_class` would have had no caller that ever passes a live class — a nullable arm that cannot fire. The boundary sites call `SchemaToModelFactory.make_from_json_schema` directly, and `resolve_object_class` keeps its genuinely dual-armed nullable parameter (exercised by `llm_generate`).

`ContentGenerator.make_search_structured` now returns the leaf's instance directly. It no longer re-validates, and therefore no longer raises `DryRunObjectFidelityError` — in-process the mock is built from the real class, so a constrained class fails earlier and louder as `DryRunMockBuildError`, exactly as the object path has since #1076. `test_dry_search_structured_fidelity_gap_raises_typed_error` was re-scoped to the boundary composition and renamed for it; the in-process build-error arm and an `INV-INV-` once-only arm are new tests beside it.

### ⚠ The live search path was broken, and threading the class down would have made it worse

The deferral note flagged the live arm as "unverified: check whether the SDK internally instantiates the schema class". It does — and checking turned up something else first.

**The Linkup backend asked for `include_sources=True`.** With that flag the SDK returns a `LinkupSearchStructuredResponse`, and the worker dumped the whole thing — so `search_structured` returned `{"data": {...}, "sources": [...]}` rather than the structured payload. The submitter then validated that envelope against the caller's output structure class, which has no `data` and no `sources` field. **Structured search through Linkup could not have worked.** The only test covering it is a live worker-level one written to assert the envelope, so it documented the shape rather than catching it. And the gateway backend had the same defect one hop removed: the relay's `WebSearcher.search_structured` also passes `include_sources=True` and returns the SDK response's `model_dump()`, so the gateway worker handed the leaf the same envelope — the default routing profile ships `all_pipelex_gateway`, so this was the arm users actually hit. The direct backend now asks for the payload alone; the gateway worker unwraps the relay's envelope on receipt (loudly, so a relay contract change surfaces as a classified error), and both backends hand the leaf the bare payload.

**And the SDK does instantiate the class.** `_parse_search_response` calls `structured_output_schema.model_validate(...)` whenever it was handed a class rather than a string. Threading the caller's real class in would therefore have run the caller's validators inside the SDK and then again at the leaf — the same `INV-INV-…` defect, arriving through the provider instead of through the mock.

Both are fixed at the worker, and the fix for the second is the one to check: **the schema crosses as a JSON string.** `_get_search_params` sends `json.dumps(cls.model_json_schema())` when handed a class and the string verbatim when handed a string, so `json.dumps(schema.model_json_schema())` is byte-for-byte the same request — while the parse branch that instantiates is guarded by `not isinstance(..., str)`, so the response comes back raw. The caller's real schema still reaches the provider in full; the single validation stays at the leaf, where the run mode and the fidelity contract live. `include_sources` is now `False`, matching what the contract can actually carry.

`tests/unit/pipelex/providers/linkup/test_linkup_structured_search_contract.py` pins all three properties against a mocked client, and the live worker test's assertions were corrected to the payload shape.

---

## Item 3 — auditing the boundary dump→validate round trip

The deferral said: audit what actually crosses this conversion, add a round-trip property test over the models that do, and *if the audit finds a real loss*, consider having the boundary return raw data instead of a reconstructed instance. It found one. The fix turned out to be one keyword, not a redesign.

### Who reaches the conversion

**Nothing in this repo does.** Every branch of `make_object` / `make_object_list` returns an `isinstance` of `object_class`, so the short-circuit always fires:

- **DRY** — `resolve_object_class` returns the caller's class unchanged and polyfactory's `build()` instantiates `__model__` itself, so the mock is exactly `object_class`.
- **LIVE** — checked against every concrete LLM worker, not a sample: the OpenAI (completions + responses), Anthropic, Mistral and Google workers all return instructor's object untouched, and Bedrock raises `LLMCapabilityError` rather than returning. Gateway / Portkey / Azure / OpenRouter are those same workers under a different factory. Instructor's wrapper is `create_model(cls.__name__, __base__=(cls, OpenAISchema))`, a subclass — which is why the check is `isinstance`.
- **The list path** wraps only the top-level `ListSchema`; its `items` are constructed by pydantic against `list[item_class]`.

**The distributed boundary always reaches it**, and cannot short-circuit: the activity calls the leaves without a class, and kajson re-execs the rebuilt class on the workflow side from `__kajson_class_source__`, so what comes back is never a subclass of `object_class`. That is the split the design intends, now established rather than assumed.

### The loss

`object_class` is always a `StuffContent` subclass resolved **by name** from the class registry, so the set is open — any field name a user writes in a concept structure crosses this conversion.

`datamodel-code-generator` cannot name a field `json`, `copy`, `schema` or `construct` (they shadow `BaseModel` attributes), nor use a python keyword. It renames the field and records the schema's property name as an alias. Dumping **by field name** emitted `construct_` for a field the caller's class calls `construct`, and re-validation failed with a bare `Field required` — on a field the caller had supplied.

`by_alias=True` on the dump fixes it: the schema's property names are what the class was serialized as and what it accepts back, and where nothing was renamed the alias *is* the field name, so nothing else moves. The same one-word fix was needed on `dry_search_gen_structured`, which dumps its mock for the wire. `test_boundary_roundtrip_fidelity.py` fails on every shadowing field without it, in both dump modes, and carries the native content classes as controls.

**The old note had the mechanism wrong, and it matters.** It supposed `PipeSearchSpec` / `PipeComposeSpec` survive thanks to `populate_by_name=True`. `PipeComposeSpec` did **not** survive — its `construct` property is exactly a shadowed name, and `populate_by_name` cannot help when the emitted key (`construct_`) matches neither the field name nor the alias. `PipeSearchSpec` survived only because `query` happens to be a legal field name.

### What turned out to be safe, and now has a test

- **Plain aliases need no compensation at all.** `model_json_schema()` emits by alias, so the rebuilt class's field name *is* the alias — with or without `populate_by_name`.
- **Subclass erasure is structurally unreachable**, not merely unobserved: the crossing object is built from `object_class`'s own schema so it cannot carry extra fields, and the one object that *is* a subclass hits the short-circuit and is never dumped. No test, because the case cannot be constructed through this path.
- **`CompositeContent` survives** — `extra="allow"` comes through the rebuild, so its components are preserved rather than dropped as unknown keys.

### Left open, deliberately

- **Instructor's `PARALLEL_TOOLS` modes return a generator, not an instance** — which would break the short-circuit's premise. Reachable from `StructureMethod`, but no model in the shipped TOMLs selects them. A config-reachable hazard, not a live one; worth a guard when one is configured, not before.
- **Json-mode losslessness for arbitrary user field types** on the distributed arm. The residue of the original note, now narrowed to that.

Both are recorded in `wip/refactoring/boundary-revalidation-round-trip-audit.md`, which replaces the "unaudited" note.

---

## Still deferred

- **Func-registry entries outliving their library** (#1076's item 1). Ruled to be its own later PR, after these. `wip/refactoring/func-registry-entries-outlive-their-library.md`.
- **Our distributed-execution plugin's copies of the revalidation helper.** Release-gated on shipping `object_revalidation`; the swap is written up in the workspace notes, outside this repo.
- **Dry search leaves report no usage.** None of the dry search leaves (`dry_search_gen_sourced_answer`, `dry_search_gen_structured`, `dry_search_gen_structured_object`) emits a usage event, so a dry run's cost/usage report shows zero search calls for a method that will make one per run — where the dry LLM leaves report a synthetic job (`report_dry_llm_job` / `report_mock_usage_llm_job`). Pre-existing (dry search never reported), not introduced here. Fixing it means choosing the synthetic-search-job conventions (model name/id placeholders, the per-request 1M-token cost convention, dry vs `is_mock_usage` variants) — a small design, not a mechanical patch, so it was deferred rather than improvised.

## Cross-repo

The sweep was done by enumerating the workspace's sibling repos one directory at a time. ⚠ A workspace-rooted `grep -r … .` silently returns zero matches here; exactly one consumer holds affected code, and every other hit is another worktree of this same repo.

**Our distributed-execution plugin** — carries the copies item 2 replaces, and needs no change for item 4: the structured-search activity calls the boundary arm, whose signature and return type did not move. Release-gated on this shipping; the swap is written up in the workspace notes, outside this repo.

**`pipelex-relay`** — optional alignment, not required for correctness: the relay's structured route still passes `include_sources=True`, making Linkup gather sources the structured contract cannot carry, and wraps the payload in the `{data, sources}` envelope the gateway worker now unwraps. The relay could stop requesting sources and return the payload alone — but that must land *together* with dropping the worker-side unwrap (which fails loudly on a bare payload by design), so it is a coordinated two-sided change, not a cleanup either side can do alone.

**`cocode` breaks on upgrade — still open, carried over from #1076, needs a follow-up PR in that repo.** `cocode/cocode/pipelines/doc_proofread/file_utils.py` carries `@pipe_func()` *and* a redundant module-level `func_registry.register_function(read_file_content, name="read_file_content")`. `cocode/cocode/swe/swe_cmd.py:18` dotted-imports that module at CLI startup, registering object **A**; `PIPELINE_LIBRARY_DIRS` then makes the same directory a library dir, so the boot scan re-imports the file under a path-mangled `sys.modules` key, the module-level call fires again with object **B**, and #1076's collision check raises. Every `cocode` command would die at first `load_libraries`. Shielded only by cocode's `pipelex==0.41.0` pin. The fix belongs in cocode and is a deletion: the `@pipe_func()` decorator already covers the registration. ⚠ `cocode/cocode/pipelines/text_utils.py:81` is *not* the same fix — it has no decorator, so its explicit call is its only registration.
