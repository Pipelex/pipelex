# The served gateway config outlived `prompting_target` — what happened, and what made the fix safe

**Found 2026-08-14, during Phase 3 of the templating-style plan; fully resolved the same day.** Kept as the record of a failure mode that will recur for any field ever removed from `InferenceModelSpecBlueprint`, and of the mechanism that makes such a removal safe.

## What happened

Deleting `prompting_target` from `InferenceModelSpecBlueprint` made **every** test in the suite error at boot, on this machine and on any machine with a cached gateway config:

```
InferenceBackendLibraryError: Invalid inference model spec 'gpt-4o-mini' for backend
'pipelex_gateway' from remote config with local overrides from '.pipelex/inference/backends/pipelex_gateway.toml':
Extra forbidden fields: 'prompting_target'
```

The Pipelex Gateway backend does not read its model specs from a file in this repo. They are fetched from the Pipelex API and cached at `~/.pipelex/cache/remote_config.json`, and that config's `backend_model_specs.defaults` block declared `prompting_target = "anthropic"`. `InferenceModelSpecBlueprint` is `extra="forbid"`, so once the field was deleted here, a config that still declared it stopped validating.

Note the asymmetry inside `InferenceBackendLibrary.load`: the loop that reclassifies unknown keys as outbound HTTP headers iterates the **per-model** dict only. So an unknown key per-model is silently turned into a header, while an unknown key in `defaults` is fatal. Same input, two opposite failure modes, neither of them "ignore it". That asymmetry is the subject of [`../rogue-extra-headers-guard-plan.md`](../rogue-extra-headers-guard-plan.md).

## What was done in `pipelex`

`drop_unknown_gateway_defaults` (`pipelex/cogt/model_backends/gateway_config.py`) prunes keys the blueprint does not know from the **remote** config's `defaults` before the merge with local overrides. Rationale, stated in the docstring: the gateway config is served by a component that deploys on its own schedule, so a client legitimately reads a config written by a different release than itself — an unknown key there is version skew, not a typo. Local backend files stay strict.

This is not a shim for `prompting_target` specifically; it is the tolerance a remote config needs in general, and it would have prevented this failure for any removed field. Tested in `tests/unit/pipelex/cogt/model_backends/test_gateway_unknown_defaults.py`.

The prune is pure and silent by design. It first logged the dropped keys, which crashed any caller that loads backends before `runtime_hub.set_config()` has configured the log dispatch (`RuntimeError: LogConfig is not set`) — and since the served config really did declare an unknown key, that fired on the ordinary success path, not a corner. Pinned by `test_pruning_does_not_need_the_log_hub`.

## What was done in the served config, and why it was safe

`prompting_target` is deleted from the gateway config our back-office repo (private) serves — its gateway-models TOML declared it in `[defaults]`, and its build service publishes that block as the remote config's `backend_model_specs`. It is dead data: nothing in `pipelex` reads it any more.

**The mechanism that made the deletion safe is the versioned config URL, not timing.** Deleting the key would otherwise have been a live prompt change for every deployed client, in the one direction we do not want:

| Client | Config declares the key | Config drops it |
|---|---|---|
| A client with the prune (this branch onward) | pruned → `xml` (the resolved default) | `xml` |
| Earlier release | `anthropic` → `xml` | **`None` → the filter's own `TICKS` fallback** |

An older client never reaches its configured `default_prompting_style`: `PromptingConfig.get_prompting_style(None)` returns `None` rather than the default, so no style reaches `apply_tag_style`, which applies its own `TagStyle.TICKS`. Every gateway prompt in the field would have moved from XML tags to backtick fences, silently.

That never happens because the served config is **versioned in its URL**: `pipelex_details.py` now points at `pipelex_remote_config_12.json` (was `_11`). The edited gateway TOML was published as `_12`; `_11` is frozen and still carries `prompting_target = "anthropic"`, so every earlier release keeps rendering XML. Verified live against both URLs: `_12` `defaults` = `{model_type, sdk, structure_method}`, `_11` = the same plus `prompting_target`, the same model entries either side.

**The URL bump is the compatibility boundary for any breaking change to this config.** It is the reason the deletion did not need to wait for a deployed floor, and it is worth knowing before the next one. Two cautions that go with it: the local cache at `~/.pipelex/cache/remote_config.json` is shared across every checkout on a machine and records no source URL, so a `_12` checkout can be reading an `_11` body populated by another checkout; and our JS runtime (private repo) is a second consumer of this wire contract that still pins `_11` and models `promptingTarget` on its own spec — unaffected today, divergent the moment it moves to `_12`.

## The open design question, answered elsewhere

Whether the per-model unknown-key → HTTP-header rule should survive is decided and planned in [`../rogue-extra-headers-guard-plan.md`](../rogue-extra-headers-guard-plan.md): the rule survives, but only for header-shaped keys; anything else is fatal from a local file and pruned from the served payload. To be executed after the templating-style branch merges, and never in a release that predates the `prompting_target` deletion.
