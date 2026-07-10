# Checkpoint 3 review — Phase 4 grind complete

Cold, no-context `/code-review` fan-out over the grind range `a1649f269..ff8bfbdc6` (batches 8–11: plugins, cli, cogt, tools). Three fresh Sonnet `general-purpose` sub-agents, each pointed only at the commit range — never handed the tracker or my own conclusions.

## Agents

1. **code-correctness** — hunt for a demoted param still passed positionally somewhere (esp. dynamic/framework-invoked call sites type-checkers miss), signature rewrites that changed defaults/order/types, and protocol/ABC parity gaps.
2. **grant-judgment** — spot-check keep-vs-demote decisions: a KEPT grant whose first param is not the genuine subject (instrumental/scope/mode/symmetric), inaccurate rationales, and same-shape inconsistencies within a batch.
3. **mechanical-rewrite-safety** — verify the two script-generated edit kinds (AST signature rewrite + call-site keyword insertion): name-collision mis-edits (fixer keyed on simple function name) and multi-line signature corruption.

## Outcome

**Agents 1 & 3 (correctness + mechanical safety): clean.** No positional-call breakage anywhere in `pipelex/` or `tests/` (confirmed by an independent AST scan and the touched-area test suites, 4573 passing); every rewritten signature preserved parameter identity/order/annotations/defaults; the one duplicate simple name in range (`check_backend_credentials` — the unrelated `InferenceBackendLibrary.check_backend_credentials` has zero call sites) could not be mis-edited; `load`/`setup` call sites were already keyword so the fixer touched nothing there and left unrelated `.load(`/`.setup(`/`json.load` calls alone. One incidental (pre-existing, not from this range): `LLMSettingChoices.make_completed_with_defaults` has zero call sites — dead code from `944bce8d8`.

**Agent 2 (grant-judgment): 3 real misses — all fixed.** All three were the same failure mode: a lookup-container / scope param kept as the subject where a sibling in the *same batch* correctly demoted the identical shape. Fixed in the commit that carries this record:

1. `cli/dev_cli/commands/sync_main_config_cmd.py::sync_main_config_cmd` — `target: SyncTarget` is a scope selector (which config files to write); the synced file is a hardcoded path, not a param. Same shape as the demoted `generate_mthds_schema_cmd(output)` / `check_backend_credentials(config_dir)`. → demoted `target` to keyword-only (call site already keyword).
2. `cogt/models/model_manager.py::ModelManager._resolve_terminal_candidates` — `deck` is the lookup container; `ref` (already keyword-only) is the thing resolved, exactly as its sibling `_collect_candidates(ref, *, aliases, waterfalls, …)` chose. → demoted `deck` to keyword-only (call site already keyword).
3. `cogt/models/model_suggestion.py::suggest_model_alternatives` — `model_deck` is "the model deck to search in" (container), `name` is the actual target; same container+target shape the batch demoted in `RoutingProfile.get_backend_match_for_model(enabled_backends, model_name)`. → demoted `model_deck` to keyword-only; fixed the two positional call sites (`check_model_cmd.py`, `model_deck_check.py`).

**Considered and kept (agent flagged low-confidence, not a batch error):** the `GatewayFactory`/`PortkeyFactory`/`GoogleFactory`/`MistralFactory` `get_api_key(backend)` / `get_endpoint(backend)` / `is_debug_enabled(backend)` / `make_*_client(backend)` family, where `backend: InferenceBackend` (a `ConfigModel`) is the granted subject. This is a registry-wide "single input → derive/build a value" convention (the backend is the config the value is derived *from*, the operand consulted — like the taxonomy family), applied consistently, not a batch-specific inconsistency. Left as-is deliberately.

Gates after the fixes: `make agent-check` green; cogt + cli unit suites green (1983 passing).
