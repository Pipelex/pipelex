# PR #1104 — review findings deferred out of that PR

Two findings from the bot review of [#1104](https://github.com/Pipelex/pipelex/pull/1104) were confirmed real but deliberately left out of that PR. Their state today:

---

## 1. `TemplatingStyle` silently ignores unknown keys — ✅ resolved on the stacked branch `fix/keyless-followups`

**Reported by:** chatgpt-codex-connector (P2), on `pipelex/pipe_operators/llm/pipe_llm_blueprint.py`.

`TemplatingStyle` was a bare `BaseModel` inheriting pydantic's default `extra="ignore"`, so `templating_style = { tag_style = "xml", text_formt = "markdown" }` parsed fine and yielded `xml/plain`. `TemplateBlueprint` — the rich `[pipe.name.template]` table on `PipeCompose` — had the same hole and a bigger one: `templating_stile` and `extra_contxt` were both dropped silently. Note the reporter's literal example (`{ text_formt = "markdown" }` alone) did **not** reproduce, because `tag_style` has no default and a table missing it fails both arms of the union; the misspelled key has to be an optional one.

**Fixed as one strictness pass over both nested authoring models, not a drive-by on one of them:** both are `extra="forbid"` now, with tests that pin the rejection directly, through `PipeLLMBlueprint`, through `PipeComposeBlueprint`, and across a kajson round trip. The MTHDS JSON Schema gains `additionalProperties: false` on both definitions (`make gms` / `make cms` green; no tracked diff, since `derived/mthds_schema.json` is gitignored).

**What is still release-gated:** the downstream propagation of that schema change to the committed copies in `mthds`, `vscode-pipelex` and `mthds-ui`, via the `mthds-schema-sync` skill once a `pipelex` release carries it. It rides with the `templating_style` schema change from #1104 itself — the sync tax is paid once. Already listed in the [implementation plan's out-of-scope follow-ups](templating-style-implementation-plan.md#out-of-scope-here--release-gated--cross-repo-follow-ups).

---

## 2. `PipeStructure` does not resolve the authored templating style — deliberately left as is

**Reported by:** cubic-dev-ai (P2), as the second half of the `preliminary_text` finding. The first half — the draft blueprint dropping `templating_style` — was a real bug and is fixed in #1104.

There is a genuine asymmetry between the two structuring paths: `direct` renders `output_structure_prompt` under the **authored** style, while `preliminary_text` synthesizes a `PipeStructure` that renders it under the **runtime default**.

**Why it stays:** it is unobservable under the shipped templates, and closing it contradicts a decision the code records on purpose. Both built-in structuring templates (`structuring_prompt`, `output_structure_prompt` in `pipelex.toml`) use bare `{{ }}` interpolation with no style-sensitive filter, on a value that is already a `str` — the style is inert there. `pipe_structure.py` states the choice: *"No authored style on this operator: the structuring prompt takes the runtime default, the same one an LLM pipe that declares nothing gets."* Closing it would mean a new field on `PipeStructureBlueprint` + `PipeStructureFactory` + the runtime pipe + the builder spec + the JSON schema + downstream schema sync, for zero observable effect today.

**Revisit only if** a structuring template ever grows a style-sensitive filter (`| tag`, `| format`), at which point the asymmetry becomes observable and the field earns its cost.
