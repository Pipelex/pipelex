# The gateway config still declares `prompting_target` — a cross-repo follow-up

**Found 2026-08-14, during Phase 3 of the templating-style plan.** Deleting `prompting_target` from `InferenceModelSpecBlueprint` made **every** test in the suite error at boot, on this machine and on any machine with a cached gateway config:

```
InferenceBackendLibraryError: Invalid inference model spec 'gpt-4o-mini' for backend
'pipelex_gateway' from remote config with local overrides from '.pipelex/inference/backends/pipelex_gateway.toml':
Extra forbidden fields: 'prompting_target'
```

## Why it happens

The Pipelex Gateway backend does not read its model specs from a file in this repo. They are fetched from the Pipelex API and cached at `~/.pipelex/cache/remote_config.json`, and that config's `backend_model_specs.defaults` block carries `prompting_target = "anthropic"`. `InferenceModelSpecBlueprint` is `extra="forbid"`, so once the field was deleted here, a config that still declares it stopped validating.

Note the asymmetry inside `InferenceBackendLibrary.load`: the loop that reclassifies unknown keys as outbound HTTP headers iterates the **per-model** dict only. So an unknown key per-model is silently turned into a header (the hazard the implementation plan already flags), while an unknown key in `defaults` is fatal. Same input, two opposite failure modes, neither of them "ignore it".

## What was done here

`drop_unknown_gateway_defaults` (`pipelex/cogt/model_backends/gateway_config.py`) prunes keys the blueprint does not know from the **remote** config's `defaults` before the merge with local overrides. Rationale, stated in the docstring: the gateway config is served by a component that deploys on its own schedule, so a client legitimately reads a config written by a different release than itself — unknown key there is version skew, not a typo. Local backend files stay strict.

This is not a shim for `prompting_target` specifically; it is the tolerance a remote config needs in general, and it would have prevented this failure for any removed field. Tested in `tests/unit/pipelex/cogt/model_backends/test_gateway_unknown_defaults.py`.

The prune is pure and silent by design. It first logged the dropped keys, which crashed any caller that loads backends before `runtime_hub.set_config()` has configured the log dispatch (`RuntimeError: LogConfig is not set`) — and since the served config really does declare an unknown key, that fired on the ordinary success path, not a corner. Pinned by `test_pruning_does_not_need_the_log_hub`.

## What still needs doing, elsewhere

1. **Drop `prompting_target` from the gateway config served by the Pipelex API.** It is dead data as of this change: nothing in `pipelex` reads it any more. The source is **our back-office repo** (private), not the hosted server: its gateway-models TOML declares it in `[defaults]`, and its build service publishes that block as the remote config's `backend_model_specs`.

   **Done — and the mechanism that made it safe is the versioned config URL, not timing.** Deleting the key would have been a live prompt change for every deployed client, in the one direction we do not want:

   | Client | Config declares the key | Config drops it |
   |---|---|---|
   | With the prune (this branch) | pruned → `xml` (the new resolved default) | `xml` |
   | Earlier release | `anthropic` → `xml` | **`None` → the filter's own `TICKS` fallback** |

   An older client never reaches its configured `default_prompting_style`: `PromptingConfig.get_prompting_style(None)` returns `None` rather than the default, so no style reaches `apply_tag_style`, which applies its own `TagStyle.TICKS` (`tools/jinja2/jinja2_filters.py`). Every gateway prompt in the field would have moved from XML tags to backtick fences, silently.

   That never happens because the served config is **versioned in its URL**, and this branch bumps it: `pipelex_details.py` now points at `pipelex_remote_config_12.json` (was `_11`). The edited `gateway_models.toml` was published as `_12`; `_11` is frozen and still carries `prompting_target = "anthropic"`, so every earlier release keeps rendering XML. Verified live against both URLs: `_12` `defaults` = `{model_type, sdk, structure_method}`, `_11` = the same plus `prompting_target`, 73 model entries either side.

   The URL bump is the compatibility boundary for *any* breaking change to this config, which is worth knowing before the next one — it is the reason the deletion did not need to wait for a deployed floor.
2. **Decide whether the per-model unknown-key → HTTP-header rule should survive for the gateway backend.** Deliberately untouched here. A removed field that had lived per-model rather than in `defaults` would have been sent to the provider as a header instead of raising — a worse outcome than the one that was actually hit, and one no test would catch.

   **Decided, and planned: [`../rogue-extra-headers-guard-plan.md`](../rogue-extra-headers-guard-plan.md).** The rule survives, but only for header-shaped keys; anything else is fatal from a local file and pruned from the served payload. To be executed after the templating-style branch merges.

Neither is in scope for the templating-style change. Item 1 is a back-office deliverable (private repo); item 2 is a design question about the backend loader that deserves its own look.
