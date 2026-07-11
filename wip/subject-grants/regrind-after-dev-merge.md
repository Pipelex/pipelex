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

Each wave: `make agent-check` green. Full `make agent-test` green after wave B and after wave C (both waves demote framework-adjacent protocol members). `--report`: seeded remaining 0; grants total 1,746.
