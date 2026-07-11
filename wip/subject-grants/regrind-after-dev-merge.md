# Regrind record — redoing the Phase-4 grind after the dev merge (Phase M step 5)

The `feature/Signatures` branch was rewound to the pre-grind mechanism commit and `origin/dev` merged there, which reset every grant to `seeded = true` (plus dev's new wave). This record documents how the regrind was executed so its verdicts are auditable against the archived first grind (tag `subject-grants-grind-archive`, tip `2ebf3f293` — checkpoint-2 and checkpoint-3 review records live in that branch's `wip/subject-grants/`).

## Method — classification against the archive

An AST-based classifier compared, per seeded key, the def's signature across three trees: the pre-grind base (`9f5bd54a3`), the archived grind tip, and the merged working tree. Buckets:

| Bucket | Count | Treatment |
|---|---|---|
| PORT | 1,470 | Archive KEPT it and dev left the def's signature unchanged → archive rationale ported verbatim (wave A) |
| REDO_DEMOTE | 148 | Archive demoted it and dev left the def unchanged → the archive's demoted header spliced back over the working-tree def, byte-for-byte (wave B) |
| REVIEW_NEW | 285 | Dev-new def → genuinely reviewed against the rubric + case-law (wave C) |
| REVIEW_CHANGED | 24 | Archive had a verdict but dev changed the signature → genuinely re-reviewed (wave C); archive-kept rationales re-used where the verdict stood |

Wave B also re-applied the archive's demotes on `@override`/Protocol implementers (carve-outs, so registry-invisible), recovered pyright-guided; call sites re-labelled with the keyword mechanically.

## Wave C verdicts (the genuine review): 268 kept, 41 demoted

Demote families applied (all existing case-law): console/sink-first params (`_print_*`/`_display_*`/`_render_fix_result(console, …)`), key+payload targets (`apply_fix_ops(toml_doc, *, ops)`, `resolve_field(field_name, *, blueprint)`, `add_stuff_spec`, `normalize_typeless_signature_section`), optional-selector-among-alternatives (`inputs_core(pipe_code=None, …)` family, matching the archive's `build_inputs_for_pipe` demote), config-first (`pipeline_run_setup(execution_config)` — literally the case-law example), lookup-container/scope (`_default_main_pipe_ref(crate)`, `find_default_inputs_file(directory)`, `_iter_stampable_files(directory)`, `_resolve_table(toml_doc, …)`), accumulator-sink (`_add_native_ref(referenced, …)`), same-type pair (`_file_state_matches(current_snapshot, *, expected_snapshot)`), bare-literal call sites (`_text_field("The text", …)`, `build_fix_command("pipelex", …)`), job_metadata run-family (`PipeAbstract._make_lifted_output`), derived-value registry lookup (`_custom_import_statement`, matching the demoted `_get_structure_class_import`).

Protocol parity handled: demoting `GraphTracerProtocol.setup(graph_id)` demoted `GraphTracer.setup` and `GraphTracerNoOp.setup` in the same commit (the manager's `open_tracer(graph_id)` stays granted — entity-keyed, per the archive).

Keeps of note: the codegen emitters/resolvers/parsers (single-operand transformations and noun-named derivations), the `markdown_renderer` formatters and provider factories (positional-`Callable` protocol), `plugin.register(registrar)` (duck-typed third-party dispatch invoked positionally by discovery), the InputShaper `_shape_*` family (the raw value is the operand), WorkingMemory getters/recorders (entity-keyed / verb-object).

Judgment calls worth spot-checking: the record-vs-registry discriminator — extraction from a single record analyzed (`_extract_wrapped_*_error(error)`, `_pending_signatures_from_validation_result`) KEEPS, while lookup of one entry in a keyed container (`_get_raw_main_absence(working_memory_raw)`, `_default_main_pipe_ref(crate)`) DEMOTES; and `_validation_category_header(category)` / `_markdown_category_header(category)` kept as noun-named derivations (pure match/case over the operand) rather than demoted as mode-selectors.

## Gates

Each wave: `make agent-check` green. Full `make agent-test` green after wave B and after wave C (both waves demote framework-adjacent protocol members). `--report`: seeded remaining 0.

## Checkpoint review (Phase M step 6) — 3-agent fan-out over the merge+grind range

Three fresh no-context Sonnet agents reviewed the `d58cd847b..` grind commits, same shape as checkpoint 3. Findings and triage:

- **Code-correctness** — one real defect: `PipeAbstract.validate_before_run` had lost its `-> InputPresenceScan` return annotation in the wave-B splice (the archive grind itself had dropped it, and the byte-for-byte splice faithfully copied the loss). Restored. Everything else clean: no positional call-site breakage, protocol/implementer pairs in lockstep, no framework callbacks wrongly keyword-only'd.
- **Mechanical-rewrite-safety** — independent AST audit over all demoted defs: zero parameter/default/decorator/docstring losses, zero missed call sites across the tree, registry consistent with the demoted set. Its only confirmed finding was the same annotation loss.
- **Grant-judgment** — audited rationale quality and same-file consistency (including a mechanical sibling-diff sweep). Verdict: regrind well-applied; case-law families (console-first, key+payload, lookup-container, entity-keyed getters vs payload setters, positional-Callable protocols, two-candidate demotes) all held up on inspection. Three high-confidence inconsistencies, all triaged as real misses and **demoted** (def + call sites + registry entry removed):
  - `DeliveryExecutor._get_raw_main_stuff_dict(working_memory_raw)` — structurally identical to its sibling `_get_raw_main_absence` (demoted): a keyed-container lookup, the record's own stated DEMOTE discriminator.
  - `check_keyword_only_cmd.py::_print_violation_lines(violations)` — three same-shape siblings in the same file (`_print_failure_panel`, `_print_failure_quiet`, `_print_violations_by_kind`) were all demoted; "when in doubt → keyword-only" settles the 3-of-4 split.
  - `kit_cmd.py::_cleanup_other_targets(repo_root)` — `repo_root` is a scope param, not the verb's object (the objects are the keyword params); the lone call site already passed it by keyword.

Post-triage: `make agent-check` green; delivery-executor tests green. Grants total 1,743.

The post-triage full-suite run also caught one failure class the reviews missed: dev-new unit tests stubbing `render_stuff_spec` with mocks asserted the pre-demote positional call (`assert_called_once_with(JSON)`). Mock assertions are invisible to pyright, so the wave-B pyright-guided call-site fixer never flagged them. Rewrote the assertions to the keyword form (`output_format=...`); the `side_effect` usages are exception instances, unaffected. This is a known blind spot of mechanical demotes: mock-based tests only fail at runtime — the full test suite is the safety net.
