# Emit lint-clean codegen artifacts

**Status: PR [#1070](https://github.com/Pipelex/pipelex/pull/1070) → `dev`, OPEN.** Branch `fix/Codegen-lint-clean` off `dev` at `8c0b99b3a`. Phases 1–5 done except the release-gated cross-repo sweep (5.4). Local `make agent-check` + full `make agent-test` + `make drift-check` green.

⚠ **Round 2 (2026-07-29) found the lint-clean claim did not hold, and the fixes are not yet committed.** Five input shapes still broke the stamp, one of them a regression this branch introduced. All are fixed and guarded; see [Review rounds](#review-rounds). The two claims that changed shape as a result — `__doc__` is no longer byte-identical to the description, and long lines are now pre-exploded — are ruled decisions (D2, D3 below), not incidental.

## Review guide

Everything above the `---` divider is the record of what shipped. The original plan below it is kept for its reasoning and rejected alternatives — read it for *why the approach is what it is*, not for current state.

### What is in the diff, and why each file belongs

| Area | Files | What changed |
| --- | --- | --- |
| **The fix** | `codegen/emitters/python_common.py`, `python_pydantic.py`, `python_structures.py`, `ts_zod.py` | Emit what the formatter wants: builtin generics, `X \| None`, double-quoted `Literal` members, isort-grouped imports (`render_import_block`), mode-aware docstring escaping, prettier-shaped blank lines and import wrapping, and the header-only empty projection (`python_module_body`). |
| **Runtime generator (D1)** | `core/concepts/structure_generation/generator.py` | Same respelling, so the two paths that render the same resolved-type tree agree. Its output is `exec()`d, never written to disk, so no linter ever saw it — this is a consistency change, not a lint fix. |
| **A real bug the respelling exposed** | `libraries/library_manager.py` | Concept cycle detection branched on `__origin__`, which a PEP 604 union does not have. **Not scope creep** — see finding 5. |
| **Repo-side lint config** | `pyproject.toml`, `pipe_run/pipe_run_params.py`, `system/pipelex_service/remote_config_fetcher.py` | Sets `runtime-evaluated-base-classes` (phase 5.1), which retires two hand-written `# noqa: TC001` / `TC003` that were working around the same rule one file at a time. |
| **Convention gate** | `subject_grants.toml` | Positional-subject grants for the new `_breaks_out_of_docstring` and `render_import_block`. Mechanically required by `make check-keyword-only`. |
| **Tests** | `tests/unit/pipelex/codegen/*`, `.../structure_generation/test_structure_generator*.py` | The new guard plus the expectation churn from the respelling. |
| **Docs** | `CHANGELOG.md`, `docs/under-the-hood/codegen-projections.md` | The breaking-bytes notice + the consumer contract. |

### Deliberate — do not flag these

1. **The emitted `python-structures` import order fails *this repo's* own ruff (`I001`) — and running this repo's `ruff --fix` over a generated `structures.py` therefore still breaks its stamp.** That is expected, not a surviving bug. It imports both `pydantic` and `pipelex`, and isort wants opposite orders depending on whether `pipelex` is first-party (here) or a dependency (a consumer's tree) — the two cannot both be satisfied. The emitter targets the consumer, who is the only one who lints these files; this repo commits no generated artifact. The test passes `lint.isort.known-third-party=['pipelex']` for exactly this reason, and so must any manual check — see [Verify it locally](#verify-it-locally). `python-pydantic` imports no `pipelex` and so is config-independent. Full reasoning in finding 1.
2. **`TC003` is answered by consumer configuration, not by emitted bytes.** Moving `from datetime import date` into `if TYPE_CHECKING:` would break the generated models — pydantic resolves annotations at runtime. See ["`TC003` must not be satisfied by the emitter"](#tc003-must-not-be-satisfied-by-the-emitter).
3. **`INP001` is suppressed in the test's ruff invocation, not in the bytes.** It is an artifact of pointing ruff at a bare directory, not of file content.
4. **`class_docstring`'s fully-escaped branch is now reached only by genuinely pathological input** — a description carrying *both* `"""` and `'''`, a control character, or a trailing backslash. A description containing only `"""` falls back to `'''` instead, which keeps it backslash-free and therefore `D301`-clean (see [D2](#d2--docstring-rendering)). The escaped branch does trip `D301`, and that is accepted: ruff classes the fix as unsafe, so `ruff check --fix` never applies it and the stamp holds.
5. **The empty projection carries no imports at all**, not even `from __future__ import annotations`. A header is the only shape inert under every formatter. See finding 7.
6. **Emitted bytes change for all three targets — that is the point, and it is breaking.** Anyone holding a committed projection sees drift until they regenerate; the changelog says so and gives the command. See [Blast radius](#blast-radius).

### Where each property is guarded

| Property | Guard |
| --- | --- |
| Both Python targets are ruff-clean (`check` + `format --check`) | `test_emitted_artifacts_are_lint_clean.py::test_emitted_artifact_passes_ruff` |
| The fixture reaches **every** `ResolvedTypeKind`, so a new kind cannot go unlinted | `…::test_fixture_covers_every_resolved_type_kind` |
| An **empty** projection is ruff-clean for both Python targets | `…::test_empty_projection_is_lint_clean` |
| The *reachable* empty case — natives-only crate through `python-structures` — is a bare header | `…::test_natives_only_crate_emits_a_lint_clean_structures_module` |
| TS has no collapsible blank runs (config-independent, always runs) | `…::test_emitted_ts_has_no_collapsible_blank_runs` |
| An empty TS projection is a bare header (config-independent, always runs) | `…::test_empty_ts_projection_is_a_bare_header` |
| No emitted TS code line exceeds the print width (config-independent, always runs) | `…::test_emitted_ts_lines_fit_the_print_width` — the guard that actually holds the TS width line in CI. Comment lines are exempt: prettier reflows code, never `//` or `/** … */` contents. |
| TS is genuinely prettier-clean | `…::test_emitted_ts_is_prettier_clean` — **skipped unless `prettier` is on PATH, which CI does not have** (Python repo, no node toolchain). The three always-on invariants above are what actually hold the TS line in CI; the prettier assertion is a local-run confirmation. Worth knowing before trusting the TS side. |
| Python stays formatter-stable across the consumer's `line-length`, not just ours | `…::test_emitted_artifact_is_stable_at_every_consumer_line_length` (88–200) |
| Crate shapes that use no seeded import stay lint-clean | `…::test_crates_that_use_no_seeded_import_are_lint_clean` (all-opaque, refines-native-only) |
| `inspect.getdoc(cls)` round-trips the authored description | `test_description_escaping.py` |
| Concept cycle detection still sees optional refs | `test_concept_to_concept_references.py` (this is what caught finding 5) |
| The runtime generator's new spelling | `tests/unit/pipelex/core/concepts/structure_generation/test_structure_generator*.py` |

### Review rounds

- **Round 1 — greptile, resolved in `c9a7238e4`.** One finding, on `ts_zod.py`: the empty binder stayed formatter-unstable. Confirmed, and wider than reported — all four artifacts degenerate the same way, and the case is reachable from an ordinary method rather than only a degenerate crate. Written up as finding 7. Thread answered and resolved; no other thread was open.

- **Round 2 — `/review` (Claude) + `codex exec`, 2026-07-29.** The central claim did not hold. Reproduced end to end from an ordinary `.mthds` file: `codegen check` reported `[hand-edited]` on a projection nobody had touched. Five shapes, each verified against the real `ruff` / `prettier` binaries rather than argued:

    1. **A multi-line description — a regression this branch introduced.** `_breaks_out_of_docstring` treated a real newline as safe, which is true of the Python *parser* and false of the *formatter*. One-part docstrings tripped `D209`, two-part `D207`; both are safe fixes, and `ruff format` rewrote them too. The previous escaping put the description on one physical line, which trips only `D301` — an *unsafe* fix ruff never applies. So the bytes now changed where they previously survived.
    2. **A description with edge whitespace** → `D210`, a safe fix. Pre-existing.
    3. **An all-opaque or refines-native-only crate** → an unused `Field` / `StructuredContent` import, `F401`, a safe fix. Both are ordinary method shapes. (Found by codex; the fixture mixed opaque with fielded concepts, hiding it.)
    4. **A long description or choice list** → exceeds any `line-length`, and `ruff format` wraps the call. Fires even at this repo's generous 150 columns. (Found by codex.)
    5. **A long concept code in `ts-zod`** → prettier wraps the `z.infer` alias and the binder signatures; a long choice list expands `z.enum([...])`. Unguarded in CI, since the prettier test skips without a node toolchain.

    Fixed on all five, with the rulings recorded as [D2](#d2--docstring-rendering) and [D3](#d3--line-width) below. Verified by sweep rather than by example: 800 Python combinations (crate shape × description shape × target × `line-length` 88–200) and 44 TypeScript files against the real prettier, all clean; the docstring fidelity contract holds across every description shape including the malicious fixture, carriage returns and trailing backslashes.

    The two codex bot threads on the PR (`python_common.py:116` P1, `ts_zod.py:311` P2) are both confirmed-and-fixed by this round and still need answering.

### D2 — docstring rendering

For a description with a real newline you can have any two of {exact `__doc__` bytes, no `D301`, stable under `ruff format`}, never all three. **Ruled: render an idiomatic indented docstring**, and move the fidelity contract to the value consumers actually read:

```python
inspect.getdoc(cls) == inspect.cleandoc(description)
```

`__doc__` therefore carries the class-body indentation every hand-written docstring carries. Exact bytes still survive in `Field(description=...)` and the crate. A description that cannot sit between `"""` falls back to `'''` rather than backslash-escaping — that is what keeps it `D301`-clean, and `ruff format` rewrites `'''` to `"""` only when doing so needs no escaping, so the choice is stable. Only genuinely pathological input (both triple-quote styles, a control character, a trailing backslash) still escapes, and `D301`'s fix being unsafe means the stamp holds anyway.

### D3 — line width

The consumer's `line-length` is theirs, and we cannot know it. **Ruled: emit anything past 88 columns already exploded, with a magic trailing comma** — the one construct Black and ruff refuse to rejoin at any width (verified 60–200). 88 is ruff's default and therefore the tightest width a consumer is likely to use, and only the tightest threshold is safe. Short lines stay flat, so ordinary artifacts read unchanged and the "ejectable, human-maintainable" bar the plan argues for is preserved.

Below 88 columns a consumer can still rewrap short lines. That is the accepted, documented limit. `E501` on a single long string literal is unavoidable — you cannot wrap a string without altering the author's text — but it has no fix and is not in ruff's default rule set, so it can never break a stamp.

### Verify it locally

Build the rich method from the [reproduction](#reproduce-it-2-minutes-from-this-worktree) below, then lint it **the way a consumer would** — that isort override is not optional, see the trap right after:

```bash
CONSUMER=(--config pyproject.toml --config "lint.isort.known-third-party=['pipelex']" --config "lint.per-file-ignores={'*'=['INP001']}")
for t in python-structures python-pydantic; do
  .venv/bin/pipelex codegen types --target $t -o /tmp/lintcheck/$t /tmp/lintcheck/method
  .venv/bin/ruff check /tmp/lintcheck/$t "${CONSUMER[@]}"          # → All checks passed!
  .venv/bin/ruff format --check /tmp/lintcheck/$t --config pyproject.toml   # → already formatted
  .venv/bin/ruff check /tmp/lintcheck/$t --fix "${CONSUMER[@]}" && .venv/bin/ruff format /tmp/lintcheck/$t --config pyproject.toml
  .venv/bin/pipelex codegen check /tmp/lintcheck/$t                # → up to date  (the stamp survived)
done
```

⚠ **Do not drop the `known-third-party` override when checking `python-structures`.** Under *this repo's* bare config `pipelex` is first-party, so ruff reorders the generated imports, the bytes change, and `codegen check` reports `[hand-edited]` — which looks exactly like the bug still being live. It is not: it is the both-trees isort tension of deliberate item 1, and the emitter deliberately targets the consumer. Verified both ways. `python-pydantic` imports no `pipelex`, so it is config-independent and its stamp survives even under the bare config.

For the empty case, point it at any bundle that declares no concepts of its own:

```bash
.venv/bin/pipelex codegen types --target python-structures -o /tmp/emptycheck tests/data/packages/standalone_bundle
cat /tmp/emptycheck/structures.py     # stamp + header, nothing else
.venv/bin/ruff check /tmp/emptycheck --fix --config pyproject.toml && .venv/bin/ruff format /tmp/emptycheck --config pyproject.toml
.venv/bin/pipelex codegen check /tmp/emptycheck   # → up to date
```

A header-only artifact has no imports for isort to reorder, so this one is clean under any config. All commands above were run against `c9a7238e4` and produce the stated output.

## What the plan did not anticipate (found while implementing)

1. **The isort grouping for `python-structures` cannot satisfy both contexts.** It imports from *both* `pydantic` and `pipelex`. In a consumer's tree `pipelex` is an installed dependency (third-party — merged group, `pipelex` before `pydantic`); in this repo it is first-party (separate group, after `pydantic`). Verified empirically both ways. **Resolution: emit for the consumer** — they are the only ones who lint generated artifacts, and this repo commits none. The regression test lints with `lint.isort.known-third-party=['pipelex']` for that reason, and `render_import_block` carries the rationale.
2. **`D301` is auto-fixed and byte-changing, and a plain double quote in a description triggered it.** `escape_py_string` backslash-escaped `"` into the docstring, so a description as ordinary as `The "primary" thing` produced `"""The \"primary\" thing"""` → `ruff check --fix` rewrites to `r"""` → stamp broken *and* text corrupted. Fixed with minimal, mode-aware docstring escaping. ⚠ **Superseded by [D2](#d2--docstring-rendering) in round 2** — the fidelity claim originally recorded here (exact description↔`__doc__` bytes) turned out to be incompatible with formatter stability for a multi-line description, and the contract is now `inspect.getdoc(cls) == inspect.cleandoc(description)`.
3. **The imprecision caveat was emitted as a literal `\n`**, not a paragraph break — the multi-line docstring intent was defeated.
4. **`"Foo" | None` is a `TypeError`** in the runtime generator: it has no `from __future__ import annotations`, so concept refs are *quoted* forward references and `str` has no `|`. The union is folded inside the quotes. Only a bare quoted ref is affected; `list["Foo"] | None` is a real `GenericAlias`.
5. **The respelling silently disabled concept cycle detection.** `_detect_concept_cycles` walks the generated model's annotations and branched on `__origin__`, which a PEP 604 `X | None` (`types.UnionType`) does not have — so every optional concept reference vanished from the graph. The pre-existing TODO on that function warned about exactly this coupling. Fixed by branching on `__args__`; the 6 integration tests in `test_concept_to_concept_references.py` are what caught it.
6. **`ts-zod` does have the analogous collision** (Phase 4's open question): prettier reformatted both emitted files. Two causes — the Python two-blank-line idiom (prettier always collapses, config-independent) and the always-wrapped binder import (prettier keeps it inline while it fits its print width). Both fixed.
7. **The empty projection was the same bug in miniature** (raised in review, fixed on this branch). Every artifact assembles as `header + imports + separator + blocks`, which degenerates when `blocks` is empty: the import block has nothing left to use it (unused-import, which `ruff check --fix` deletes) sitting above a trailing blank-line run (`ruff format` collapses it), and `binder.ts` bottoms out at `import {  } from "./types";`. **It is not a degenerate-input-only case:** `python-structures` filters natives, so an ordinary method declaring no concepts of its own — a `Text -> Text` pipe — reaches it. Resolution: an empty projection is its **header alone**, assembled in one place for Python (`python_module_body`, which also absorbed the body-assembly line both emitters duplicated) and guarded inline at the two `ts_zod` call sites.

Also: adding `runtime-evaluated-base-classes` to this repo retired two hand-written `# noqa: TC001` / `# noqa: TC003` suppressions that were working around the same rule file by file.

---

**Original plan below, kept for the reasoning and the rejected alternatives.**

**Where to work:** this worktree (`pipelex/`, on `dev`). Branch off `dev` — e.g. `fix/Codegen-lint-clean` — and open a normal PR back to `dev`. Nothing here is specific to any feature track.

**Decision already taken (Louis, 2026-07-29):** emit what our linter wants, and code that matches our Python standards. The two turn out to be the same thing for every rule in play. The alternatives (hash a normalized body; tell consumers to exclude generated paths) are **rejected** — see [Why not the alternatives](#why-not-the-alternatives).

---

## The problem in one paragraph

`pipelex codegen types` writes a stamped artifact whose stamp is a raw SHA-256 over the body's UTF-8 bytes (`compute_content_hash`, `pipelex/codegen/stamp.py:80`). The emitted body is not what `ruff` wants, so the moment a consumer runs `ruff check --fix` or `ruff format` over their tree, the bytes change, the hash no longer matches, and `pipelex codegen check` reports the file as **hand-edited** — accusing the user of the one thing they did not do. It is silent until someone runs `codegen check`. Our own `pipelex-starter-python` already papers over this with an exclusion (see [Blast radius](#blast-radius)), which is the tell that the emitter, not the consumer, is wrong.

## Reproduce it (2 minutes, from this worktree)

```bash
mkdir -p /tmp/lintcheck/method && cat > /tmp/lintcheck/method/rich.mthds <<'EOF'
domain      = "lintcheck"
description = "Exercises every emitted annotation kind"
main_pipe   = "make_record"

[concept.Record]
description = "A record with many field kinds"

[concept.Record.structure]
name      = { type = "text", description = "Name", required = true }
published = { type = "date", description = "Publication date", required = true }
tags      = { type = "list", item_type = "text", description = "Tags", required = true }
counts    = { type = "dict", key_type = "text", value_type = "integer", description = "Counts", required = true }
status    = { choices = ["draft", "final"], description = "Status", required = true }
note      = { type = "text", description = "Optional note" }

[pipe.make_record]
type = "PipeLLM"
description = "Build a record"
inputs = { topic = "Text" }
output = "Record"
model = "$writing-factual-cheap"
prompt = "Make a record about $topic"
EOF

for t in python-structures python-pydantic; do
  .venv/bin/pipelex codegen types --target $t -o /tmp/lintcheck/$t /tmp/lintcheck/method
  echo "--- $t ---"
  .venv/bin/ruff check /tmp/lintcheck/$t --config pyproject.toml
  .venv/bin/ruff format --check /tmp/lintcheck/$t --config pyproject.toml
done
```

Then confirm the stamp actually dies:

```bash
.venv/bin/ruff check /tmp/lintcheck/python-structures --fix --config pyproject.toml
.venv/bin/pipelex codegen check /tmp/lintcheck/python-structures
# → [hand-edited] structures.py — Body was edited below the stamp (stamp hash no longer matches).
```

⚠ **Use a method with varied field kinds, like the one above.** A method whose fields are all `text` makes `python-pydantic` look clean and makes `ruff format` look harmless. Both impressions are wrong, and both were believed at first.

## What actually fires — measured, not assumed

| rule | what it does | `python-structures` | `python-pydantic` | fix belongs in |
| --- | --- | --- | --- | --- |
| `UP006` | `List[X]`/`Dict[K,V]` → `list[X]`/`dict[K,V]` | ✅ fires | — (already builtin) | **emitter** |
| `UP045` | `Optional[X]` → `X \| None` | ✅ fires | — (already `\| None`) | **emitter** |
| `Q000` | `Literal['a','b']` → `Literal["a","b"]` | ✅ fires | ✅ fires | **emitter** |
| `I001` | import block regrouped (stdlib / third-party / first-party, blank lines between) | ✅ fires | ✅ fires | **emitter** |
| `ruff format` | would reformat | ✅ reformats | ✅ reformats | **emitter** |
| `TC003` | move `from datetime import date` into an `if TYPE_CHECKING:` block | ✅ fires | ✅ fires | **NOT the emitter — see below** |
| `INP001` | "implicit namespace package, add `__init__.py`" | fires in a bare dir | fires in a bare dir | neither — artifact of linting a loose directory, not of file content |

**Both Python targets are affected.** `python-pydantic` is *closer* — it already uses builtin generics and `X | None` — but it is not clean.

### `TC003` must not be satisfied by the emitter

Moving the import into `if TYPE_CHECKING:` would **break the generated code**: pydantic resolves annotations at runtime to build validators, so `date` must be a real runtime import. Ruff has a first-class setting for exactly this, and it silences `TC003` for both targets — verified:

```toml
[tool.ruff.lint.flake8-type-checking]
runtime-evaluated-base-classes = [
  "pydantic.BaseModel",
  "pipelex.core.stuffs.structured_content.StructuredContent",
]
```

This is **consumer/repo configuration**, not emitted content. It goes in our docs and our starter template, and this repo should set it too (it currently does not).

## Why the two asks coincide

Every emitter-side rule above moves the output *toward* `.claude/rules/python-standards.md`: lowercase builtin generics (`list[]`, `dict[]`), `X | None` over `Optional[X]`, double quotes, sorted-and-grouped imports. There is no tension between "what ruff wants" and "our standards" here — satisfying one satisfies the other.

## Decisions to settle before coding

- **D1 — SETTLED (Louis, 2026-07-29): YES, change it too.** Does the runtime `StructureGenerator` change spelling too? `pipelex/core/concepts/structure_generation/generator.py:296` emits `Optional[{python_type}]`, and `python_structures.py`'s module docstring justifies its own spelling as mirroring that "runtime idiom". **The runtime generator's output is never written to disk** — `concept_factory.py` is its only caller and it `exec()`s the source — so no linter ever sees it and it is under no pressure to change.
  **Recommended: change it too.** It costs a handful of test updates (`tests/unit/pipelex/core/concepts/structure_generation/test_structure_generator*.py` pin `Optional[`), it keeps the two paths spelled alike so the emitter's docstring stays true, and it brings the runtime generator in line with the repo's own standards. If D1 goes the other way, the `python_structures.py` docstring **must** be rewritten to say the AOT projection deliberately diverges because only it is linted — do not leave a false rationale in place.
- **D2 — one PR or two?** Recommended: **one**. The emitter change and the runtime-generator change are independently correct but share the test-update surface and the changelog entry.

## Phases

### Phase 1 — make the emitters emit it

- [ ] 1.1 `pipelex/codegen/emitters/python_structures.py`: in `_annotation`, `List[...]` → `list[...]` and `Dict[str, ...]` → `dict[str, ...]`, dropping the `from typing import List` / `Dict` additions; in `_render_field`, `Optional[X]` → `X | None`, dropping the `from typing import Optional` addition.
- [ ] 1.2 `Literal` choices in **both** Python emitters: emit double-quoted members (`repr()` yields single quotes today — use an explicit double-quoting helper, and put it in `python_common.py` since both targets need it).
- [ ] 1.3 Import block in **both** emitters: `"\n".join(sorted(imports))` sorts raw strings, which is not isort order. Emit isort-grouped blocks — stdlib, third-party, first-party — separated by a blank line. Consider a small shared `render_import_block()` in `python_common.py`; both call sites are identical today.
- [ ] 1.4 Re-run the reproduction. `ruff check` must report only `INP001` (the loose-directory artifact) and `ruff format --check` must report "already formatted", for both targets, on the rich method.
- [ ] 1.5 Update the `python_structures.py` module docstring — the "runtime idiom" sentence is now either satisfied by D1 or falsified by it.

### Phase 2 — the runtime generator (gated on D1 = yes)

- [ ] 2.1 `structure_generation/generator.py`: same three spellings (`Optional` → `| None`, `List`/`Dict` → builtins), and drop the now-unused `typing` imports from its own import line.
- [ ] 2.2 Update `tests/unit/pipelex/core/concepts/structure_generation/test_structure_generator*.py` for the new expected source text.

**🛑 CHECKPOINT 1** — emitters and generator produce the new bytes, and every existing test is updated to match. Gates: `make agent-check` + full `make agent-test`. Do not start phase 3 in the same session; the test-expectation churn is the bulk of the work and is worth landing on its own.

### Phase 3 — the regression test that would have caught this

- [ ] 3.1 Add `tests/unit/pipelex/codegen/test_emitted_artifacts_are_lint_clean.py`: generate a projection covering **every** `ResolvedTypeKind` (text, number, integer, boolean, date, datetime, time, literal, concept, list, dict, any) plus an optional field and an opaque/structureless concept, for **each** Python target, then run `ruff check` and `ruff format --check` over it with this repo's own config and assert zero findings.
- [ ] 3.2 Suppress the two non-content rules in the test's invocation rather than in the emitted bytes: `INP001` (loose directory) and `TC003` (needs `runtime-evaluated-base-classes`, which the test should pass so it exercises the configuration we tell consumers to use).
- [ ] 3.3 Make the fixture method the **single source** for the type-kind coverage, so a new `ResolvedTypeKind` that nobody adds to it is visible. A test asserting the fixture covers every enum member is cheap and worth it.

### Phase 4 — the TypeScript target

- [ ] 4.1 Answer the open question: does `ts-zod` have the analogous collision with prettier / eslint? Nothing has checked. If it does, fix it the same way and extend the phase-3 test.

**🛑 CHECKPOINT 2** — the property is guarded for every target, not just repaired once.

### Phase 5 — consumers and docs

- [ ] 5.1 Set `runtime-evaluated-base-classes` in **this** repo's `pyproject.toml` (`[tool.ruff.lint.flake8-type-checking]`) — we do not set it today.
- [ ] 5.2 Document the consumer contract: generated artifacts are lint-clean by construction, here is the one ruff setting you need, and you should **no longer** need to exclude generated paths.
- [ ] 5.3 CHANGELOG: emitted bytes change for both Python targets. Breaking for anyone with a committed projection — their next `codegen check` reports drift until they regenerate. Say so plainly and give the one-line regeneration command.
- [ ] 5.4 Cross-repo sweep, **release-gated** (needs the new `pipelex` released first):
    - `pipelex-starter-python/piper/generated/` — three committed `python-pydantic` projections (`summarize_pdf`, `extract_entities`, `generate_image`), all stamped `engine_version = "0.38.0"`. Regenerate, then **delete the `piper/generated` exclusion** from its `[tool.ruff] exclude` — that line, comment and all, is the bug's monument and should not survive this change.
    - `pipelex-cookbook/` — grep for `codegen.lock`; none as of 2026-07-29, but check again at sweep time.

**🛑 CHECKPOINT 3 = done** — no consumer needs a lint exclusion to keep a stamp valid.

## Blast radius

- **Emitted bytes change for both Python targets.** Anyone holding a committed projection sees `codegen check` report drift until they regenerate. That is the intended, one-time cost.
- **`test_pure_build_and_disk_write_agree_byte_for_byte` does NOT need re-baselining.** It is a self-consistency check (pure build vs. disk write) over synthetic fixture files, not a golden-file test. Only tests that pin *expected emitted text* need updating — `tests/unit/pipelex/codegen/test_python_structures_emitter.py`, the `Literal`-quoting assertions in the pydantic/ts emitter tests, and (under D1) the runtime-generator tests.
- **`pipelex-starter-python` is a live instance of the bug.** Its `pyproject.toml` carries `"piper/generated",  # generated by \`pipelex codegen\` — reformatting would trip the codegen.lock drift check`. We shipped the workaround in our own template rather than fixing the emitter.
- **Not affected:** the crate fingerprint, the lock format, `codegen check`'s logic, and the HTTP codegen route's contract. This changes only what the emitters write.

## Why not the alternatives

- **Hash a normalized body.** Weakens the stamp from "byte-identical" to "semantically unchanged", and the normalizer becomes its own compatibility surface that has to agree across versions and languages. It also leaves the emitted code below the ejectability bar — code the project's own linter wants to rewrite on sight is not code we can call idiomatic and human-maintainable.
- **Tell consumers to exclude generated paths.** This is today's de-facto answer and it is why the bug survived: the exclusion is invisible, it must be copied into every consumer repo, and anyone who misses it gets an error message accusing them of hand-editing. It also does nothing for the quality bar.

## Cold-start brief

Read this file top to bottom, then:

1. `cd` to this worktree (`pipelex/`, on `dev`), `git pull`, `make install` if the venv is stale.
2. Run the [reproduction](#reproduce-it-2-minutes-from-this-worktree) to see the failure with your own eyes and confirm the rule table still matches.
3. Settle **D1** with Louis if it is not already recorded here, then start at Phase 1.
4. Branch off `dev` first — do not work on `dev` directly for this.

The two emitters are near-identical twins (`pipelex/codegen/emitters/python_structures.py` and `python_pydantic.py`, ~110 lines each) sharing `python_common.py` and the neutral `resolve_structure_fields` layer. Read all three before editing; most of Phase 1 is deciding what belongs in the shared module.
