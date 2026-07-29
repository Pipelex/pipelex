# Emit lint-clean codegen artifacts

**Status: IMPLEMENTED 2026-07-29** on `fix/Codegen-lint-clean` (off `dev` at `8c0b99b3a`). Phases 1–5 done except the release-gated cross-repo sweep (5.4). `make agent-check` + full `make agent-test` green.

## What the plan did not anticipate (found while implementing)

1. **The isort grouping for `python-structures` cannot satisfy both contexts.** It imports from *both* `pydantic` and `pipelex`. In a consumer's tree `pipelex` is an installed dependency (third-party — merged group, `pipelex` before `pydantic`); in this repo it is first-party (separate group, after `pydantic`). Verified empirically both ways. **Resolution: emit for the consumer** — they are the only ones who lint generated artifacts, and this repo commits none. The regression test lints with `lint.isort.known-third-party=['pipelex']` for that reason, and `render_import_block` carries the rationale.
2. **`D301` is auto-fixed and byte-changing, and a plain double quote in a description triggered it.** `escape_py_string` backslash-escaped `"` into the docstring, so a description as ordinary as `The "primary" thing` produced `"""The \"primary\" thing"""` → `ruff check --fix` rewrites to `r"""` → stamp broken *and* text corrupted. Fixed with minimal, mode-aware docstring escaping (plain / raw / escaped). Exact description↔`__doc__` fidelity is preserved — `test_description_escaping.py` asserts it, and normalizing `\r` broke it once before being reverted in favour of routing hazards to the escaped branch.
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
