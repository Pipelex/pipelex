# Guarding against rogue outbound headers — implementation plan

**Written 2026-08-14, to be executed after the templating-style branch merges.** This answers item 2 of [`prompting-style/gateway-config-still-declares-prompting-target.md`](prompting-style/gateway-config-still-declares-prompting-target.md) — "decide whether the per-model unknown-key → HTTP-header rule should survive" — which that document deliberately left open because it is a design question about the backend loader, not part of the templating change.

Progress is tracked with the checkboxes below. **The checkpoint marked ✋ is a hard stop: the executing agent must not proceed past it without Louis' explicit go.** At the checkpoint, update this doc first — tick boxes, fill the checkpoint log at the bottom — so the work can hand off into a fresh session with nothing lost.

## The behaviour today

`InferenceBackendLibrary._load_backend` (`pipelex/cogt/model_backends/backend_library.py:195-199`) loops over each per-model TOML table and moves every key that is not a field of `InferenceModelSpecBlueprint` into `extra_headers`:

```python
extra_headers: dict[str, str] = {}
for model_spec_key in model_spec_dict:
    if model_spec_key not in model_spec_blueprint_standard_fields:
        extra_headers[model_spec_key] = model_spec_blueprint_dict.pop(model_spec_key)
```

That dict lands on `InferenceModelSpec.extra_headers` (`model_spec.py:34`) and every provider factory forwards it to the wire as request headers — `gateway_factory.py:99`, `portkey_factory.py:47`, `openai_completions_factory.py:118`, `openai_responses_factory.py:113`, `openrouter_completions_factory.py:24`, `blackboxai_completions_factory.py:29`.

So the rule is: **anything the blueprint does not recognise is assumed to be a header the author meant to send, and is sent, silently.** There is no allowlist, no shape check, and no log line.

Note the asymmetry with the `[defaults]` block of the same file, which is validated strictly and raises on an unknown key — except for the remote gateway payload, where `drop_unknown_gateway_defaults` (`gateway_config.py:16`) prunes it as version skew. Same input, three different fates depending on where it sits and where it came from.

## What is actually in the bag (measured 2026-08-14)

Re-measure before starting; the served config moves independently of this repo.

```bash
# local backend TOMLs: per-model keys the blueprint does not know
python3 -c "
import tomllib, pathlib
KNOWN = {'enabled','sdk','variant','model_type','model_id','inputs','outputs','costs','structure_method','thinking_mode','max_tokens','max_prompt_images','listed_constraints','valued_constraints','rules'}
for p in sorted(pathlib.Path('.pipelex/inference/backends').glob('*.toml')):
    data = tomllib.loads(p.read_text())
    extras = {k for name, spec in data.items() if name != 'defaults' and isinstance(spec, dict) for k in spec if k not in KNOWN}
    if extras: print(p.name, sorted(extras))
"
# the served gateway payload (URL pinned in pipelex/system/pipelex_service/pipelex_details.py)
curl -s https://pipelex-config.s3.eu-west-3.amazonaws.com/pipelex_remote_config_12.json | python3 -m json.tool | head -40
```

What that turned up:

| Source | Key | Genuinely a header? |
|---|---|---|
| `.pipelex/inference/backends/portkey.toml`, per-model | `x-portkey-provider` | yes — read by Portkey |
| served gateway config, on every model | `x-portkey-config` | yes — also read back locally by `GatewayDeck.get_config_id` (`gateway_deck.py:9`) |
| served gateway config, on the image models | `endpoint_path` | **no** — internal routing, read back by `gateway_img_gen_worker.py:86` |

No other local backend TOML uses the mechanism at all, and the served `[defaults]` block is clean.

Two things follow. First, the mechanism is load-bearing and cannot simply be closed: the gateway would lose its per-model Portkey config id. Second, **the bag is already not what its name says** — `endpoint_path` is our own routing metadata, and it escapes the wire only by luck, because the image worker builds its headers explicitly instead of forwarding the bag. Put the same key on a model served by the LLM path and `GatewayFactory.make_extras` ships `endpoint_path: openai/deployments/…` to Portkey as a header.

## Why this is worth fixing

- **A deleted or renamed blueprint field becomes a header.** This is the hazard the templating-style plan flagged and then dodged by luck: `prompting_target` happened to live in `[defaults]`, so its removal was fatal and loud. Had it lived per-model — and in `portkey.toml` it *does* also live per-model — the same removal would have started sending `prompting_target: gemini` to the provider. No test in the suite would have gone red.
- **A typo becomes a header.** `max_tokns = 4096` on a model posts a junk header *and* silently leaves the real cap unset. That is exactly the class of silent misconfiguration `_load_backend`'s own docstring says it refuses to tolerate ("a config typo must never silently delete a backend, because the commands that boot leniently would then report the far more confusing 'model not found'").
- **We send unreviewed strings to third parties.** Whatever is in a model table goes out over the network to the provider. That deserves a deliberate opt-in, not a default.
- **The rule is undocumented.** `grep -rn "header" docs/` returns nothing about it. Nobody outside this file knows it exists, which means nobody outside this file can use it on purpose either.

## The rule to build

**An unknown per-model key is accepted as a header only if it is shaped like a header name.** Concretely: it contains a hyphen. HTTP header names conventionally do (`x-portkey-config`, `anthropic-beta`, `api-version`); blueprint field names never do, because they are Python identifiers. Every real key in the table above passes except `endpoint_path`, which is not a header and is promoted to a declared field in Phase 1.

A shape rule, not an allowlist of names: the whole point of the open bag is that pipelex-back-office can start serving a new `x-portkey-*` header without waiting for a client release, and a name allowlist would take that away.

Everything unknown that is *not* header-shaped is then handled by source:

- **From a local backend TOML — fatal.** There, an unknown snake_case key really is the author's typo, and local files are already strict about `[defaults]`.
- **From the served gateway payload — pruned, silently.** There, it is version skew: a client legitimately reads a config written by a different release. This is the identical judgement `drop_unknown_gateway_defaults` already makes for the `defaults` block, for the identical reason, and the silence is required for the identical reason too — the prune runs before `runtime_hub.set_config()` on some boot paths, so a `log` call turns a data transform into a boot-order dependency (`test_pruning_does_not_need_the_log_hub` pins this).

**That skew tolerance is not theoretical, and the executing agent should verify it still holds before assuming otherwise.** On 2026-08-14 this machine's `~/.pipelex/cache/remote_config.json` held the `_11` payload byte-for-byte while this branch pinned `_12` — because the cache path is shared across every checkout, seven of the eight on this machine pinned `_11`, and the cache records `schema_version` / `cached_at` / `raw_config` but **no source URL**, so a `_12` client cannot tell it is reading an `_11` body. Making remote unknowns fatal would have turned that ordinary local condition into a red suite.

## Decisions (veto here, cheaply)

- **D1 — the classifier is pure, the policy lives at the call site.** A new `pipelex/cogt/model_backends/model_spec_keys.py` splits a raw model table into (blueprint fields, headers, rejected). It does not decide what "rejected" means. `_load_backend` decides, because only it knows the source. Functions are fully keyword-only so no subject grant is needed.
- **D2 — the source is an enum, not a bool.** `ModelSpecSource.LOCAL_FILE | REMOTE_GATEWAY`, matched with `match`/`case` per the repo's enum convention. `_load_backend` already distinguishes the two branches (`PipelexBackend.is_gateway_backend`), so this threads one value, not new logic.
- **D3 — near-miss protection.** A key whose hyphens-to-underscores form matches a known blueprint field (`max-tokens`, `model-id`, `thinking-mode`) is rejected despite being header-shaped. Three lines, and it closes the one hole the shape rule leaves. **Separable — drop this if you think it is a solution in search of a problem.**
- **D4 — `endpoint_path` becomes a real field**, not a permanent exception to the rule. It is our own data, read by our own worker; it has no business in a bag named for headers.
- **D5 — no change to the backend-level twin** (`backend_library.py:154-156`, unknown backend keys → `extra_config`) in this change. Same silent-reclassification shape, but that dict never reaches a provider, so the blast radius is a local misconfiguration rather than an outbound one. See "Considered and deferred".
- **D6 — the error names the key and the file, and says what to do.** A boot failure reading `Unknown key 'max_tokns' on model 'gpt-4o' in '.pipelex/inference/backends/openai.toml' — not a known model-spec field, and not header-shaped (a header key must contain a hyphen, e.g. 'x-portkey-provider')` is the whole value of this change for a user. A bare pydantic `extra_forbidden` is not.

## Phase map

- **Phase 1** — promote `endpoint_path` to a declared field. Standalone, no behaviour change, shippable on its own.
- **Phase 2** — the shape guard and its two policies (TDD). This is where a config that used to boot can start failing. → ✋ **Checkpoint**
- **Phase 3** — docs, changelog, dogfood log.

**Phase 1 must precede Phase 2, and they must ship in the same release.** If the guard lands first, `endpoint_path` — snake_case, no hyphen — gets pruned out of the remote payload and every image model breaks with "does not have an endpoint_path configured".

## Traps to keep in view

- **Do not write the regression test against `prompting_target`.** It no longer exists in the blueprint, so a test using it would prove nothing about the mechanism. Construct the dead-field case with a synthetic key.
- **Config sync is one-directional.** `.pipelex/inference/backends/` is the source of truth; edit there, then `make ukc`, gated by `make ccs`. Both trees carry the portkey headers.
- **The gateway's *local* override file is already safe** — `GatewayConfigMerger` restricts local overrides to `{sdk, structure_method}` (`gateway_config_merger.py:10`) and warns on anything else, so a user's `pipelex_gateway.toml` cannot inject headers today and will not be affected by this change. The exposure is the direct-provider local TOMLs and the served payload. Do not "fix" the merger; verify and move on.
- **No drift contract fires.** `backend_library.py` and `model_spec_factory.py` are in no contract's trigger set (`config-docs` triggers `system/configuration/**`, `cogt/config_cogt.py`, and friends). Do not hunt for an ack to record — but do log the observation, see Phase 3.
- **`make agent-check` runs the keyword-only auto-fixer**, which will silently keyword-only an ungranted subject. D1's functions are keyword-only by design, so there is nothing to grant here — just do not let the fixer surprise you elsewhere.
- **Drift reads the git index**: stage before `make drift-check` / `agent-check`.

---

## Phase 1 — `endpoint_path` becomes a declared field

Goal: the one non-header key in the bag stops pretending to be a header. No behaviour change, no served-config change, no config URL bump — the served TOML is untouched, the new client merely classifies the key differently, and older clients keep reading it out of `extra_headers` exactly as before.

- [ ] `InferenceModelSpecBlueprint.endpoint_path: str | None = None` (`model_spec_factory.py`) and the matching field on `InferenceModelSpec` (`model_spec.py`), with the factory passthrough.
- [ ] `gateway_img_gen_worker.py:86` reads `self.inference_model.endpoint_path` instead of digging in `extra_headers`. Its existing "does not have an endpoint_path configured" error stays — it is the right error, it just now guards a real field.
- [ ] Update the image-worker tests that stub the bag: `test_gateway_img_gen_worker_semantic.py`, `test_gateway_img_gen_worker_malformed_body.py`, `test_gateway_img_gen_worker_edit_routing.py`, `test_gateway_quota_detection.py`. Each sets `mock_model.extra_headers = {"endpoint_path": …}`; they should set the field and leave the bag to the headers that belong in it.
- [ ] Verify against the live payload that the key still parses into the field and that `x-portkey-config` still lands in `extra_headers` — a real boot, not only mocks.
- [ ] Gates: targeted tests, `make tb`, stage + `make agent-check`.

## Phase 2 — the shape guard

Goal: an unknown per-model key is either a plausible header or a loud error, and never a silent outbound string. TDD throughout — each box's test lands red first.

- [ ] **Tests first (red):** new `tests/unit/pipelex/cogt/model_backends/test_model_spec_key_policy.py` — header-shaped key accepted; snake_case unknown rejected; D3 near-miss (`max-tokens`) rejected; known blueprint field never diverted.
- [ ] New `pipelex/cogt/model_backends/model_spec_keys.py` (D1): the pure classifier plus `ModelSpecSource` (D2).
- [ ] Wire it into `_load_backend` (`backend_library.py:195-199`), replacing the unconditional loop. Local source raises `InferenceBackendLibraryError` with D6's message; gateway source prunes.
- [ ] **Tests (red first):** a local backend TOML carrying a synthetic unknown snake_case key fails the load with a message naming the key, the model and the file; the same key in a remote payload is pruned and the boot survives. Extend `test_gateway_unknown_defaults.py` rather than starting a parallel module — it already owns the remote-tolerance story, including the no-log-hub constraint.
- [ ] **Regression, and the point of the whole change:** `x-portkey-provider` from local `portkey.toml` and `x-portkey-config` from the remote payload still reach `extra_headers` and still reach the wire.
- [ ] **Leniency interaction:** confirm what a rejected key does under `lenient=True`. A typo must not silently delete a backend — that is the existing ruling in `_load_backend`'s docstring, and this new raise sits inside the same `try`. Decide deliberately and record the answer here; if it needs to escape the lenient skip, say why in a comment at the raise site.
- [ ] **Mutation-check the new tests:** revert the guard, confirm the new tests go red, restore. A guard whose tests pass without it is not a guard.
- [ ] Gates: `make tb`, targeted tests, stage + `make agent-check`, **full `make agent-test`**.

### ✋ CHECKPOINT — HARD STOP

Do not start Phase 3 without Louis' explicit go. This is where a config that booted yesterday can fail today. Present: the diff, the test results, the answer to the leniency question, and a **worked example of the new error message** as a user would see it. Louis rules on D3 (near-miss), on the leniency behaviour, and on the commit/PR shape. Update the checkpoint log.

---

## Phase 3 — Docs, changelog, dogfood

- [ ] `docs/configuration/config-technical/inference-backend-config.md` — document the mechanism for the first time: extra per-model keys are sent to the provider as request headers, they must be header-shaped, anything else is a configuration error, and `endpoint_path` is a declared field. Include what a rejected key looks like.
- [ ] Changelog `## [Unreleased]`, condensed style, **breaking**: a per-model key that is neither a known model-spec field nor header-shaped now fails the backend load instead of being sent to the provider as a request header; `endpoint_path` is a declared model-spec field.
- [ ] Append a dogfood entry to `wip/drift-contracts/dogfood-log.md`. The observation worth recording: **`backend_library.py` shapes user-facing configuration and sits in no contract's trigger set** — the same shape of finding as the Phase 4 templating entry (a config surface documented outside `docs/configuration/`), from the other direction. Record it; per the pilot's bias, do not act on it here.
- [ ] Gates: stage + `make agent-check`.

## Cross-repo / release-gated follow-ups

- **The downstream backend-TOML sweep gets louder, and that is the good news.** The templating-style plan already lists this as its one non-optional follow-up: every repo shipping `.pipelex/inference/backends/*.toml` still declares `prompting_target`, and `portkey.toml` carries it **per-model as well as in `[defaults]`**, so a fix that deletes only the `[defaults]` line unblocks the boot while quietly turning the per-model ones into outbound headers. With this guard in place that residue becomes a boot error naming the key instead. Confirmed tracked-file hits at the time of writing: `pipelex-server/worker/`, `pipelex-api/`, `cocode/`, `pipelex-cookbook/`, `pipelex-demos/`, `mthds-ui/`, plus `pipelex-js/` fixtures. **Ship this guard in or after the release that deletes `prompting_target`, never before** — before, it would reject the key while the field still exists.
- **`pipelex-back-office`** owns the served gateway config (`pipelex_back_office/remote_config/gateway_models.toml`). Nothing to change now: `endpoint_path` becomes a declared field on the client side and `x-portkey-config` is header-shaped. Worth telling whoever maintains it that a *new* non-header per-model key would from now on be pruned by new clients rather than forwarded as a header.
- **`pipelex-js`** is a second consumer of the same wire contract and models these specs its own way (`packages/runtime/src/worker/catalogue.ts`). Whether it wants a parallel rule is its own call, not this plan's.

## Considered and deferred

- **The backend-level twin** (`backend_library.py:154-156`): unknown *backend* keys are reclassified into `extra_config` with the same silence. Deferred because `extra_config` never reaches a provider — the failure is a local misconfiguration, not an outbound string. It is a small follow-up on its own, and the classifier built in Phase 2 would serve it directly.
- **Renaming `extra_headers`.** Once `endpoint_path` moves out, the field genuinely holds only headers and the name is finally honest. Renaming it touches every provider factory for zero behaviour change; do it only if it rides along with something else in that area.
- **Logging accepted headers at load time.** Tempting — "here is what we will send" — but the prune path runs before the log hub is configured, and the accepted path would need the same care. Not worth a boot-order dependency.

## Checkpoint log

*(Filled in as the checkpoint is reached: status, decisions taken, open questions, state of the code.)*
