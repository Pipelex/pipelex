# Phase 4 — xhigh code-review follow-ups

Record of the xhigh `/code-review` run on the Phase 4 commit (`6a0796548` — "invert model listing, the 5th and last dispatch seam"). The review confirmed the inversion is **byte-equivalent to the old static `match`** for every shipped config — no crash or wrong-output bug. Adversarial verify kept a handful of findings; this note dispositions them.

Two cheap cleanups were **applied in the same pass** (see the bottom of this note). The four below are **design tradeoffs, not bugs** — deferred deliberately rather than reflexively "fixed," so the decision is on the record for a future session. Sibling to [`phase-4-residual-core-vendor-couplings.md`](phase-4-residual-core-vendor-couplings.md) (which covers core→vendor couplings *outside* the enumerated seams); this note covers review findings *on the model-listing seam itself*.

## 1. Model listing is now coupled to the plugin enable/disable switch — DEFERRED (arguably correct as-is)

`cogt/model_backends/model_lists.py`. The old static `match sdk:` listed `anthropic` / `mistral` / `bedrock` / `google` SDKs unconditionally. After the inversion, listing dispatches through the registry, and those four plugins are **not** in `CORE_UNCONDITIONAL_PLUGIN_NAMES` — so adding one to `config.plugins.disabled` removes its lister, and `pipelex show models <backend>` then reports that SDK as "we don't support for remote listing."

- **Real?** Yes — it is the one live behavior change in the commit.
- **Why deferred (and arguably *correct*):** a disabled plugin also registers no `make_worker`, so its models can't be *run* either. Listing models you can't use was the old anomaly; gating listing on the same enable switch as execution is the more consistent behavior. "Fixing" it (e.g. registering listers even for disabled plugins) would re-introduce the inconsistency.
- **Revisit if:** product decides `plugins.disabled` should mean "hide the driver but still enumerate its catalog" (a discovery-vs-activation split). That is a config-semantics decision, not a Phase 4 bug.

## 2. Bedrock lister key skew (`bedrock` / `bedrock_aioboto3` vs worker key `bedrock_boto3`) — DEFERRED (zero live impact)

`plugins/bedrock/bedrock_plugin.py`. The lister registers under `bedrock` (dead — no shipped model spec carries `sdk="bedrock"`) and `bedrock_aioboto3`, while the **inference backend** in the same `register()` body registers under `bedrock_boto3` / `bedrock_aioboto3`. So within one function the lister and worker key sets deliberately differ.

- **Real?** Byte-equivalent to the old `case "bedrock" | "bedrock_aioboto3"` arm — carried forward verbatim, **zero live impact**. The `bedrock` key is dead today.
- **Why deferred:** dropping the dead `bedrock` key is a tiny cleanup, but `tests/unit/pipelex/plugins/test_model_lister_coverage.py` pins the registered-key set as an *exact-match* contract (`EXPECTED_LISTER_SDKS` includes `bedrock`), so the cleanup is "drop the key **and** update the exact-set test + its docstring framing" — a coupled edit better done deliberately than as a checkpoint drive-by.
- **Footgun to watch:** a future bedrock variant whose model specs use `bedrock_boto3` would get "unsupported for listing" instead of a model list, because no lister is registered under that key. If/when bedrock keys are consolidated, align the lister keys with the worker keys in the same `register()` body.

## 3. `any_listed` leaks the listing loop's display state into the public SPI — DEFERRED (pre-existing, now on the public surface)

`plugins/*/​*_plugin.py` lister closures + `ListModelsFn` + the authoring example in `docs/under-the-hood/inference-backend-plugins.md`. `any_listed` is CSV-header / separator suppression state owned by `ModelLister.list_models` — pure loop-presentation bookkeeping. The inversion re-published it as part of the *public* `ListModelsFn` contract, so every out-of-tree backend author must accept and correctly forward a flag whose meaning is internal to the loop; a lister that forwards it wrongly produces a duplicated/missing CSV header.

- **Real?** Pre-existing (the old per-arm calls already threaded it), but Phase 4 cemented it into the new SPI surface.
- **Why deferred:** the clean fix is to keep the lister contract to the data it needs (`sdk` / `backend_name` / `backend` / `flat`) and let the loop own the header decision (it already knows `any_listed` — pass an `is_first` hint or post-process). That is an SPI-shape change touching every lister + the doc + the display helpers — a focused refactor, not a checkpoint cleanup.
- **Best moment:** before any third-party backend ships against `ListModelsFn`, while the only implementers are in-tree.

## 4. `ListModelsFn = Callable[..., Awaitable[None]]` gives the loop's kwargs zero static checking — DEFERRED (follows Phase-1 precedent)

`plugins/model_lister_registry.py`. The whole byte-equivalence claim rests on every lister's kwargs matching the loop's `await` call, yet the `...` args mean pyright/mypy can't catch future drift: rename a lister param or change the loop's call kwargs and the mismatch surfaces only at runtime as a `TypeError` wrapped into a confusing `PipelexCLIError`.

- **Real?** Yes as a latent type-safety gap; not a live bug (the shipped kwargs match).
- **Why deferred:** a `Protocol` with the explicit keyword-only signature (the way `OrchestratorProtocol` already types the orchestrator seam) would catch drift statically at no runtime cost — but `MakeWorkerFn` uses the *same* loose `Callable[..., ...]` form, so tightening only `ListModelsFn` would split the convention. The right scope is "tighten both inference-family callables to Protocols together," a Phase-1-and-Phase-4 SPI-typing pass, not a model-listing-only edit.
- **Pairs with #3:** if `ListModelsFn` becomes a `Protocol`, drop `any_listed` from its signature at the same time.

## Applied in the same pass (not deferred)

- **Registrar `_add` helper** — `add_inference_backend` / `add_model_lister` / `add_orchestrator` each hand-rolled the identical dup-check → store → mirror-into-`_*_sources` → append-contribution shape. Generalized behind one `PluginRegistrar._add(...)` (each method supplies its keyed store, parallel sources dict, contribution label, and a factory that builds its distinctly-typed `Duplicate*Error`), mirroring the existing `_claim` helper on the slot menu. A future 6th registration seam now reuses `_add` instead of becoming a 4th copy.
- **Hardcoded counts in the Phase 4 as-built** — removed the item-count enumerations the workspace `CLAUDE.md` "Never hardcode counts" rule forbids (`9 expected sdk keys`, `4 soft-miss cases`, `2 new pages`, `274 unchanged`, `4 keys`, `2 keys`). Point-in-time test-run evidence (`715 passed`, pyright file count) was left as a verification snapshot.
