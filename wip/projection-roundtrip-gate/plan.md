---
status: draft
item: L-260830-216378
---

# Round-trip every projected template through the input shaper at corpus-generation time

The projection corpus generator (`pipelex/cli/dev_cli/commands/generate_projection_corpus_cmd.py`) authors the fill-in templates the TypeScript and Python projections are pinned against, committed byte-identically in `mthds-js` and `mthds-python`. A template exists to be filled in and handed back to the runtime, so every slot it pins must survive `InputShaper.shape` — and the generator never checks that. Twice, corpus bytes pinned slots the runtime rejects outright (`WrongScalarKindError` on a bare date object, a bare string at a nested `TextContent` node), and both times a human review round caught it instead of the capture; the second time (L-260830-8695ba) the divergence gate actively absorbed the broken sites into a declared class and exited 0.

## The design decision: registry-gated, not report-only

The item's original note proposed a report-only verdict, because L-260830-191719 (a descriptor gap, not a projection error) makes `probe_single` unshapeable today and a hard refusal would block generation on a known-open defect. This plan refines that: the check follows the **declared-never-discovered** discipline the divergence record already has.

- An `EXPECTED_UNSHAPEABLE` registry maps `(pipe_ref, shape)` to the ledger item tracking the fix.
- A round-trip failure **not** in the registry fails the command, printing the pipe, shape and error. This is the mechanism that would have caught both prior escapes at generation time.
- A registry entry whose template **now shapes** also fails the command ("delete the entry, the gap closed"), so a fix retires its declaration deliberately — exactly the lapse rule `DivergenceCollector.declared()` applies.
- Generation is never blocked by the known-open gap: its entries are declared, recorded in the manifest, and printed.

Report-only would print a failure and still exit 0 with the broken bytes written; nothing forces anyone to read the output before committing them in two consumer repos. The registry keeps the item's stated goal (a stated fact, generation unblocked) while making the capture the thing that catches the next regression.

Measured ground truth (2026-08-31, `dev` at the projection-divergence-gate landing): over the three corpus bundles, the failing round-trips are exactly `input_semantics_probe.probe_single` and `input_semantics_probe.probe_markers`, each in **both** shapes, all four from the L-260830-191719 nested-list gap (`matrix` in `Widget`). Every other template shapes cleanly in both shapes — the file-ish mock-URL leaves and the fixed-count slots included. The check is offline: the shaper wraps URLs without fetching (`input_shaper.py`, file-ish arms) and the command already boots with `needs_inference=False`.

## Scope decisions

- **Both shapes round-trip, not just compact.** The item title says compact, but the explicit template is equally a runnable scaffold, it fails today for the same pipes, and the check is one extra call on a template already in memory. The registry key is `(pipe_ref, shape)`.
- **JSON form only.** Both serializations derive from the same in-memory template dict, so shaping the dict covers the values; TOML byte-fidelity is the consumer harnesses' concern.
- **The manifest records failures only, without the error message.** A new manifest field `unshapeable: [{pipe_ref, shape, error_type, ledger_item}]` — mirroring the divergence record, which lists departures, not conformances. The error **class name** is contract-stable (the error-identity snapshot discipline); the message is wording that would churn committed bytes across pydantic versions, so it goes to the console only. Passing verdicts are printed, not committed.
- **Catch broadly.** The round-trip wraps `Exception`, not `InputShapingError`: the explicit arm lets a raw pydantic `ValidationError` escape untyped today (filed as L-260831-1e1a71 — its fix will change the recorded `error_type` for the explicit entries, which the lapse-symmetric tests must not hardcode beyond the registry itself).

## Non-goals

- Fixing the descriptor gap that makes the registry non-empty — L-260830-191719. Its fix deletes the registry entries; the lapse rule forces that deletion.
- The projection's remaining unshapeable slot shapes (`native.Date[]`, class-backed date) — L-260830-8695ba. Landing this gate **first** is the point: that item's fix then proves itself against the round-trip instead of against a reviewer.
- Typing the explicit arm's escaped `ValidationError` — L-260831-1e1a71.
- Executing templates beyond shaping (no pipeline runs, no inference).

## Phase 1 — red tests

On `feature/Projection-roundtrip-gate` off `dev` (renew the claim on the branch). Tests first, failing:

- New `tests/unit/pipelex/cli/dev_cli/test_projection_shaping_gate.py`, in the style of `test_projection_divergence_gate.py` — the gate logic tested directly with an injected registry, no engine boot:
  - an undeclared failing `(pipe_ref, shape)` refuses the capture, naming the pipe, shape and error class;
  - a declared entry that now shapes refuses with the retire-it message;
  - a declared failing entry passes and yields the manifest record carrying its ledger item.
- Extend `tests/unit/pipelex/cli/dev_cli/test_generate_projection_corpus.py`:
  - the real corpus generates (the known gap is declared, so the command succeeds) and the manifest's `unshapeable` entries all cite L-260830-191719, cover both shapes, and name only pipes the registry declares;
  - the rerun byte-stability test still holds with the new manifest field.

## Phase 2 — implementation

All in `generate_projection_corpus_cmd.py` unless said otherwise:

- `EXPECTED_UNSHAPEABLE: dict[tuple[str, str], str]` beside `DIVERGENCE_ITEMS`, initially declaring `probe_single` and `probe_markers` in both shapes against `L-260830-191719`, with a comment stating the retire rule.
- `UnshapeableEntry` pydantic model (`pipe_ref`, `shape`, `error_type`, `ledger_item`), and `CorpusManifest.unshapeable: list[UnshapeableEntry]`.
- A small `ShapingGate` class (registry injected, module constant as the default) collecting one verdict per `(pipe_ref, shape)`; called from `_capture_pipe` with the already-projected template:
  `InputShaper.shape(template, concept_provider=get_concept_library(), input_specs=pipe.inputs, search_scope=pipe.domain_code)` — the same assembly as the entry-pipe run path in `pipeline_run_setup.py`. An empty descriptor's `{}` shapes trivially and is recorded as passing.
- After the walk, beside the unclassified-divergence check: raise on any undeclared failure and on any lapsed registry entry; otherwise emit the `unshapeable` manifest entries.
- Console output: one line per failing round-trip (error class + first message line), and a summary line for the passing count.

Gates: `make agent-check`, then `make agent-test` (new tests are unit-level and offline).

## Phase 3 — docs and changelog

- `docs/contribute/generate-projection-corpus.md`: a "The shaping round-trip" section — what is checked, the registry, the retire rule, and that the manifest states unshapeable templates as facts of the capture.
- `CHANGELOG.md` under `## [Unreleased]`: bold label + a few sentences.

**Checkpoint** — the pipelex half is complete and mergeable here. Open the PR against `dev` with `Closes L-260830-216378` in the body; the re-baseline below can hand off to another session.

## Phase 4 — re-baseline the committed corpus in the consumer repos

The only committed-bytes change is `inputs_template/manifest.json` gaining `unshapeable`. Regenerate with the documented bundle order and land the same bytes in `mthds-js/tests/fixtures/protocol/` and `mthds-python/tests/fixtures/protocol/`. Check each repo's manifest parser first — a strict model there must gain the field in the same change. If this session does not do it, file one ledger item per consumer repo linked to L-260830-216378 rather than leaving it implied.

## Interplay to keep in mind

- Land this before L-260830-8695ba's projection fixes: its new bundle slots then get verified by the gate at generation time.
- When L-260830-191719 closes, its fix must delete the registry entries and regenerate — the lapse rule fails the command until it does, which is the wanted loudness.
