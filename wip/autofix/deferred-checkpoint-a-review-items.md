# Deferred / reviewed items from Checkpoint A code review

Clean-context multi-angle review of the `sync-controller-inputs` diff (`git diff <phase-base>..HEAD`). The confirmed correctness defects were fixed in the same checkpoint (see below); the items here are the design-tradeoff and forward-looking findings that are real but deliberately NOT acted on now, per the no-over-engineering rule.

## Fixed in this checkpoint (not deferred — recorded for completeness)

- **Inline-table canonicalizer crashed on non-bare keys and nested values.** The old `_canonical_inline_table` assembled TOML text with raw `f"{key} = {value}"`, assuming every key is a bare unquoted key and every value a scalar. A supported dotted input key (`"cv.name"`, allowed by `validate_input_name` and used in real fixtures) raised `KeyAlreadyPresent`; a nested inline-table value (a pipe authored as a single-line inline table, patched by `match-sequence-output`) raised `UnexpectedCharError`. Fixed by letting tomlkit itself render keys/values (native `inline_table()` assignment quotes non-bare keys, nests, and preserves each value's own string style) and splicing only the outer brace padding. Pinned by `test_dotted_input_key_survives_canonicalization` and `test_set_output_on_whole_pipe_inline_table_stays_canonical`.
- **`declared_inputs` was missing from `PipeValidationError.desc()`** while `expected_inputs` was shown — the field was added as the diff counterpart, so the asymmetry hid the "before" side in logged errors. Added the symmetric line.

## 1. Keep the exhaustive `match self` classifier idiom (reviewed, not a defer)

Several angles flagged that `is_controller_input_drift` and `is_inadequate_output` each hand-enumerate the whole `PipeValidationErrorType` set, so a new member must be classified in every `is_*` property. This is the sanctioned house style (`.claude/rules/python-standards.md`: no `case _:`, so pyright's exhaustiveness check *forces* a decision on every new member) — a `{error_type: fix_code}` mapping would trade that compile-time guarantee for silence. Keeping the idiom is the correct call, not a deferral. Revisit the ergonomics only if wave-2 rules push the classifier count high enough that the per-member edit cost outweighs the guard — a real refactor with its own design, not a spike edit.

## 2. Trivia-preservation is solved twice (low-value consolidation, defer)

`applier._canonicalize_mutated_inline_table` transplants four trivia fields; `tools/misc/toml_sync.set_nested_value` swaps the whole trivia object. Same "preserve tomlkit trivia across an in-place replacement" idea, two techniques, two modules. Consolidating into a shared helper is a cross-module refactor touching code outside the fix pipeline; the drift risk (a future tomlkit trivia-model change) is low. Defer until a concrete tomlkit bump forces a look at both.

## 3. Per-`table_path` batch canonicalization (perf, defer)

`_canonicalize_mutated_inline_table` runs after every `SET_KEY`/`DELETE_KEY`. When one fix emits several ops against the same inline `inputs` table, each op re-canonicalizes the whole table — `O(N·K)` where `O(N+K)` (canonicalize each distinct `table_path` once, after all its ops land) would do. Negligible for real `inputs` tables (a handful of vars), and the per-op form is correct and idempotent (pinned by the multi-op golden test). Batching adds touched-path tracking to `apply_fix_ops`; not worth it until a rule produces many ops on one large table.

## 4. Micro-duplication in the `_*_for_fix` helpers (accept)

`_expected_inputs_for_fix` and `_declared_inputs_for_fix` repeat the `if not self.is_controller: return None` guard and the one-line `to_bundle_representation(relative_to_domain=self.domain_code)` render. A shared `_render_input_ref` / caller-side guard would save two lines across two tightly-related methods. Small enough to leave; reconsider if a third `_*_for_fix` helper appears.

## 5. Two op-shapes in `_plan_sync_controller_inputs` (early-warning, watch)

The rule emits either one whole-table `SET_KEY` (no `inputs` declared yet) or N per-key `SET_KEY`/`DELETE_KEY` ops (diff an existing table) — the reason `TomlValue` was widened to `TomlScalar | dict[str, TomlScalar]`. Fine for one rule. If a second table-create-vs-patch rule lands (e.g. sync operator config, sync structure fields), factor the create-vs-diff decision into a shared planner helper rather than widening `TomlValue` further per rule. Flagged so wave-2 doesn't accrete op-shapes silently.

## 6. `FixOp.value` wire-schema forward note (cross-repo, defer)

No `pipelex/` consumer serializes `SuggestedFix` to wire format yet, so the `TomlValue` widening (dict-valued ops) is inert here. When a CLI/API surface (mthds/protocol, sibling repo) starts rendering `SuggestedFix`, it must type the value slot as `TomlValue`, not `TomlScalar`, or it will reject the dict-valued `sync-controller-inputs` fix. Extends checkpoint-0 item 1c (additive-field changelog) with the container-value nuance; belongs to the cross-repo schema-sync wave.
