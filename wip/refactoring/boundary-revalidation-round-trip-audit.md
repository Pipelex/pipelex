# The boundary re-validation round trip, audited

Supersedes `boundary-revalidation-round-trip-is-unaudited.md` (deferred out of PR #1076). The audit was done, it found one real loss, the loss is fixed, and the parts that turned out to be safe now have tests so they stay that way. This note records what was established, what was corrected, and the two things still not established.

The conversion in question is the boundary arm of `revalidate_leaf_object` (`pipelex/cogt/content_generation/object_revalidation.py`): `object_class.model_validate(raw_obj.model_dump(mode=dump_mode, serialize_as_any=True, by_alias=True))`.

## Who actually reaches it

**Nothing in this repo.** Every branch of `ContentGenerator.make_object` / `make_object_list` returns an `isinstance` of `object_class`, so the short-circuit always fires and the conversion arm is dead code here:

- **DRY** — `dry_llm_gen_object` resolves the caller's class unchanged and `build_mock_object` builds through polyfactory, whose `build()` instantiates `__model__` itself. The result is exactly `object_class`.
- **LIVE** — every concrete LLM worker returns instructor's object untouched (`llm_worker_abstract.gen_object` only strips `_raw_response` and reports). Instructor's `prepare_response_model` wraps the class as `create_model(cls.__name__, __base__=(cls, OpenAISchema))`, a *subclass*, so `isinstance` holds. The Bedrock worker raises `LLMCapabilityError` instead of returning. Gateway / Portkey / Azure / OpenRouter are the OpenAI workers under a different factory, not separate classes.
- **The list path** wraps only the top-level `ListSchema`; its `items` are constructed by pydantic against `list[item_class]`, so each item is exactly `item_class`.

**The distributed boundary always reaches it.** The activity calls the leaves without a class, so the object is built from a `SchemaToModelFactory` rebuild; kajson re-execs that class from `__kajson_class_source__` on the workflow side and a per-call scoped registry makes the source-derived type win over the globally registered one. A rebuilt class is never a subclass of `object_class`, so the short-circuit cannot fire there — which is exactly the split the design intends.

## What crosses it

In production `object_class` is always a `StuffContent` subclass resolved **by name** from the class registry — the concept's `structure_class_name`. That registry holds the native content classes, the generated `<domain>__<Concept>` structure classes, everything `auto_register_all_subclasses(base_class=StructuredContent)` sweeps out of `sys.modules` (including the builder spec classes), and user classes from library folders. So the set is open: **any field name a user can write in a concept structure can cross this conversion.** That is what makes the loss below matter.

## The loss, and the fix

`datamodel-code-generator` cannot name a field `json`, `copy`, `schema` or `construct` — they shadow `BaseModel` attributes — nor can it use a python keyword. It renames the field (`construct_`) and records the schema's property name as the alias. Dumping **by field name** then emitted `construct_` for a field the caller's class calls `construct`, and re-validation failed with a bare `Field required` — on a field the caller had supplied.

Reproduced, fixed by dumping `by_alias=True`, and pinned by `tests/integration/pipelex/cogt/content_generation/test_boundary_roundtrip_fidelity.py` (which fails on every shadowing field without it, in both dump modes). The dump now emits exactly the schema's property names, which is what the round trip and the provider are both keyed on. Where nothing was renamed, the rebuilt class's alias *is* its field name, so nothing else changed — the native content classes are parametrized in that test as the control.

The same fix was needed on the structured-search dry boundary arm (`dry_search_gen_structured`), which dumps its mock for the wire.

**`PipeSearchSpec` / `PipeComposeSpec` were the models the old note worried about, and it had the mechanism wrong.** It supposed they survive thanks to `populate_by_name=True`. They do not: `PipeComposeSpec` **failed** this round trip before the fix, because its `construct` property is exactly a shadowed name — `populate_by_name` lets `construct_spec` through, but the dump emitted `construct_`, which matches neither the field name nor the alias. `PipeSearchSpec` survived only because its alias `query` is a legal field name that needed no rename.

## What the old note worried about that is genuinely safe

- **Plain aliases need no compensation.** `model_json_schema()` emits **by alias**, so the shipped schema's property names are the ones `object_class` accepts on the way in, and the rebuilt class's field name simply *is* the alias. This holds with or without `populate_by_name`. Pinned by `test_a_plain_alias_round_trips`.
- **Subclass erasure is structurally unreachable**, not merely unobserved. The object that crosses is built from `object_class`'s own schema, so it cannot carry a field `object_class` lacks; and the one object that *is* a subclass — instructor's — hits the short-circuit and is never dumped. Nested erasure would need a leaf that produces a subclass instance inside a declared field, which neither arm does. There is no test for this because there is no way to construct the case through this path.
- **`CompositeContent` survives.** Its `extra="allow"` config comes through the rebuild, so the components it keeps as pydantic extras are preserved rather than dropped as unknown keys. Parametrized in the round-trip test.
- **`DateContent` / `TimeContent`'s `mode="before"` validators are total over their own serialized output.** They are the closest thing on this path to a validator that would not be, and they only see json mode (the distributed arm): an ISO date survives both the numeric-string and the time-bearing-string rejection.

## Still not established

- **`Mode.PARALLEL_TOOLS` / `VERTEXAI_PARALLEL_TOOLS` would break the short-circuit's premise.** Instructor returns a *generator* in those modes, not an instance of the response model. They are reachable from `StructureMethod` but **no model in the shipped TOMLs selects them**, so this is a config-reachable hazard rather than a live one. If one is ever configured, `make_object` returns something that is neither an instance nor dumpable the way this helper expects — worth a guard at that point, not before.
- **Whether the json-mode round trip is lossless for every field type a user can write.** The audit covered the native content classes and the alias/rename mechanics; it did not enumerate arbitrary user field types under `mode="json"`. This is the residue of the original note, narrowed: it is now specifically about json-mode coercion on the distributed arm, not about the conversion in general.

## The fix the old note proposed, and why it was not needed

It suggested that if the audit found a real loss, the fix was "probably to have the boundary return raw data rather than a reconstructed instance, so there is one validation instead of a dump of one". That is a larger change — it alters what the object leaf returns across the payload boundary — and the loss found did not require it. Worth keeping in mind if the json-mode residue above ever turns up something `by_alias` cannot fix.
