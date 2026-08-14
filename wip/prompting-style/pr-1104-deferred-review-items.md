# PR #1104 — review findings deferred, not dropped

Two findings from the bot review of [#1104](https://github.com/Pipelex/pipelex/pull/1104) were confirmed real but deliberately left out of that PR. Both threads stay **open** on the PR.

---

## 1. `TemplatingStyle` silently ignores unknown keys

**Reported by:** chatgpt-codex-connector (P2), on `pipelex/pipe_operators/llm/pipe_llm_blueprint.py`.

`TemplatingStyle` (`pipelex/tools/templating/templating_style.py`) is a bare `BaseModel`, so it inherits pydantic's default `extra="ignore"`. An author who misspells an optional key gets a silently different prompt shape:

```toml
templating_style = { tag_style = "xml", text_formt = "markdown" }   # parses fine, yields xml/plain
```

Confirmed end-to-end through the MTHDS parse path — nothing at bundle level catches it, because the blueprint validation *is* the check and it stops at the nested-model boundary.

Note the reporter's literal example (`{ text_formt = "markdown" }` alone) does **not** reproduce: `tag_style` has no default, so a table missing it fails both arms of the union. The misspelled key has to be an *optional* one, with `tag_style` present.

Every sibling authoring model is strict — `PipeBlueprint`, `ConceptBlueprint`, `DomainBlueprint`, `SubPipeBlueprint` all set `extra="forbid"`, and `ConfigModel` exists as a shared strict base. `TemplatingStyle` is one of the few nested authoring models that inherits neither.

**Why it was deferred.** The fix reads like a one-liner and isn't:

- `TemplatingStyle` is pre-existing and **already reachable from the published JSON Schema** via `TemplateBlueprint` (on `dev`). Its generated definition currently emits no `additionalProperties`; adding `extra="forbid"` emits `"additionalProperties": false`. That is a schema change requiring `pipelex-dev generate-mthds-schema` plus the `mthds-schema-sync` propagation to the downstream committed copies, gated on a released `pipelex` version. The drift is invisible in a PR because `derived/mthds_schema.json` is gitignored.
- `TemplateBlueprint` itself has the **same hole and a bigger one** — both `templating_stile` and `extra_contxt` are silently dropped today, on the `PipeCompose` authoring surface. Closing only `TemplatingStyle` is exactly the partial fix the templating-style plan warns about elsewhere.

**Recommendation.** One deliberate strictness pass over the nested authoring models — `TemplatingStyle` and `TemplateBlueprint` together — with the schema regen and downstream sync budgeted as part of it. Not a drive-by line in a 120-file PR.

**When.** Any time before the next release that moves the schema; it composes naturally with any other MTHDS-schema-affecting change, since the sync tax is paid once.

---

## 2. `PipeStructure` does not resolve the authored templating style

**Reported by:** cubic-dev-ai (P2), as the second half of the `preliminary_text` finding. The first half — the draft blueprint dropping `templating_style` — was a real bug and is fixed in #1104.

There is a genuine asymmetry between the two structuring paths:

- `direct` — `run_llm_object` renders `output_structure_prompt` under the **authored** style.
- `preliminary_text` — the synthesized `PipeStructure` renders it under the **runtime default**.

**Why it was deferred.** It is unobservable under the shipped templates, and closing it is a refactor that contradicts a decision the code already records:

- Both built-in structuring templates (`structuring_prompt`, `output_structure_prompt` in `pipelex.toml`) use bare `{{ }}` interpolation with no style-sensitive filter, on a value that is already a `str`. The style is inert there.
- `pipe_structure.py` states the choice deliberately: *"No authored style on this operator: the structuring prompt takes the runtime default, the same one an LLM pipe that declares nothing gets."* The matching docs say the same.
- Closing it means a new field on `PipeStructureBlueprint` + `PipeStructureFactory` + the runtime pipe + the builder spec + the JSON schema + downstream schema sync — for zero observable effect today.

**Recommendation.** Leave it. Revisit only if a structuring template ever grows a style-sensitive filter (`| tag`, `| format`), at which point the asymmetry becomes observable and the field earns its cost. If revisited, it lands with item 1 above — both pay the same schema-sync tax.
