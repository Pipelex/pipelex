# Text-then-object — Deferred Items

Follow-ups deferred out of the text-then-object work that landed in PR #891 (`feature/Temporal-merge-3`). Mirrored here so they survive `TODOS.md` being cleared at release time.

**Source:** `TODOS.md` §"What remains as follow-up TODOs" from the PR recap.
**Owner doc:** this file once `TODOS.md` is cleared on next release.

---

1. **plxt schema sync.** `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json` is from before this PR — authoring `type = "PipeStructure"` directly in a `.mthds` file fails plxt validation. Regenerate via `pipelex-dev generate-mthds-schema` and ship a `pipelex-tools` release. The `preliminary_text` path is unaffected because the synthesized `PipeStructure` lives in-memory only.

2. **Synthetic-pipe marker on graph nodes + CLI listing exclusion.** When emitting `NodeSpec`, look up `bundle.elaboration_metadata` and set `tags["synthetic"] = "true"` + `tags["parent_pipe_code"] = parent`. Requires either a runtime-only field on `PipeAbstract` or a side-registry keyed by pipe code. Also hide synthetic pipes from `pipelex list`. ~2–3 file edits.

3. **Friendly synthetic-pipe rendering across logs/traces/run-reporting.** After (2), render `<parent_pipe_code> [<step_role_label>]` everywhere `self.code` appears. Touches graph_tracer, run_reporting, journal, distributed-tracing. ~5–8 file edits.

4. **`mthds-ui` graph viewer integration.** After (2), decide in the UI repo whether to nest synthetic pipes under their parent or hide them.

5. **Bundle-load benchmark in CI.** Microbenchmark library load time; alert on >5% regression. Protects future elaboration-pass additions.

6. **PipeStructure image input support.** v1 takes Text only; extend when a concrete need arises.

7. **Per-step prompt customization for `preliminary_text`.** Don't build until requested.

8. **Generic meta-pipe / build-time elaboration framework.** Promote `BundleElaborator._elaborate_preliminary_text` into a plugin registry when a SECOND elaboration directive appears.

9. **`pipelex-dev elaborate-bundle <path>`** debugging CLI to print the elaborated form without running.

10. **Revisit `StructuringMethod.DIRECT`.** Functionally identical to `None`. Delete if no second method materializes.

11. **Persist `elaboration_metadata` into MTHDS/JSON exports.** Today `Field(exclude=True)` drops it on every `model_dump`. When a cross-boundary consumer materializes (graph viewer over a serialized bundle, Temporal payload, persistent cache), flip `exclude=False`, regenerate the schema, ship a plxt bump. The regression test at `test_elaboration_metadata.py::test_bundle_round_trip_drops_elaboration_metadata` flips first.
