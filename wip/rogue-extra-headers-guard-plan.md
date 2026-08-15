# Guarding against rogue outbound headers — implementation plan

**Written 2026-08-14, to be executed after the templating-style branch merges.** This answers item 2 of [`prompting-style/gateway-config-outlived-prompting-target.md`](prompting-style/gateway-config-outlived-prompting-target.md) — "decide whether the per-model unknown-key → HTTP-header rule should survive" — which that document deliberately left open because it is a design question about the backend loader, not part of the templating change.

Progress is tracked with the checkboxes below. **The checkpoint marked ✋ is a hard stop: the executing agent must not proceed past it without Louis' explicit go.** At the checkpoint, update this doc first — tick boxes, fill the checkpoint log at the bottom — so the work can hand off into a fresh session with nothing lost.

## The behaviour today

`InferenceBackendLibrary.load` (`pipelex/cogt/model_backends/backend_library.py:195-199`) loops over each per-model TOML table and moves every key that is not a field of `InferenceModelSpecBlueprint` into `extra_headers`:

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
- **A typo becomes a header.** `max_tokns = 4096` on a model posts a junk header *and* silently leaves the real cap unset. That is exactly the class of silent misconfiguration `InferenceBackendLibrary.load`'s own docstring says it refuses to tolerate ("a config typo must never silently delete a backend, because the commands that boot leniently would then report the far more confusing 'model not found'").
- **We send unreviewed strings to third parties.** Whatever is in a model table goes out over the network to the provider. That deserves a deliberate opt-in, not a default.
- **The rule is undocumented.** `grep -rn "header" docs/` returns nothing about it. Nobody outside this file knows it exists, which means nobody outside this file can use it on purpose either.

## The rule to build

**An unknown per-model key is accepted as a header only if it is shaped like a header name.** Concretely: it contains a hyphen. HTTP header names conventionally do (`x-portkey-config`, `anthropic-beta`, `api-version`); blueprint field names never do, because they are Python identifiers. Every real key in the table above passes except `endpoint_path`, which is not a header and is promoted to a declared field in Phase 1.

A shape rule, not an allowlist of names: the whole point of the open bag is that the back office can start serving a new `x-portkey-*` header without waiting for a client release, and a name allowlist would take that away.

Everything unknown that is *not* header-shaped is then handled by source:

- **From a local backend TOML — fatal.** There, an unknown snake_case key really is the author's typo, and local files are already strict about `[defaults]`.
- **From the served gateway payload — pruned, silently.** There, it is version skew: a client legitimately reads a config written by a different release. This is the identical judgement `drop_unknown_gateway_defaults` already makes for the `defaults` block, for the identical reason, and the silence is required for the identical reason too — the prune runs before `runtime_hub.set_config()` on some boot paths, so a `log` call turns a data transform into a boot-order dependency (`test_pruning_does_not_need_the_log_hub` pins this).

**That skew tolerance is not theoretical, and the executing agent should verify it still holds before assuming otherwise.** Observed on 2026-08-14: a local `~/.pipelex/cache/remote_config.json` held the `_11` payload byte-for-byte while this branch pinned `_12`. The cache path is shared across every checkout on a machine, and the cache records `schema_version` / `cached_at` / `raw_config` but **no source URL** — so a `_12` client cannot tell it is reading an `_11` body, and whichever version most checkouts pin is the one that populates it. Making remote unknowns fatal would have turned that ordinary local condition into a red suite.

## Decisions (veto here, cheaply)

- **D1 — the classifier is pure, the policy lives at the call site.** A new `pipelex/cogt/model_backends/model_spec_keys.py` splits a raw model table into (blueprint fields, headers, rejected). It does not decide what "rejected" means. `InferenceBackendLibrary.load` decides, because only it knows the source. Functions are fully keyword-only so no subject grant is needed.
- **D2 — the source is an enum, not a bool.** `ModelSpecSource.LOCAL_FILE | REMOTE_GATEWAY`, matched with `match`/`case` per the repo's enum convention. `InferenceBackendLibrary.load` already distinguishes the two branches (`PipelexBackend.is_gateway_backend`), so this threads one value, not new logic.
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

- [x] `InferenceModelSpecBlueprint.endpoint_path: str | None = None` (`model_spec_factory.py`) and the matching field on `InferenceModelSpec` (`model_spec.py`), with the factory passthrough.
- [x] `gateway_img_gen_worker.py:86` reads `self.inference_model.endpoint_path` instead of digging in `extra_headers`. Its existing "does not have an endpoint_path configured" error stays — it is the right error, it just now guards a real field.
- [x] Update the image-worker tests that stub the bag: `test_gateway_img_gen_worker_semantic.py`, `test_gateway_img_gen_worker_malformed_body.py`, `test_gateway_img_gen_worker_edit_routing.py`, `test_gateway_quota_detection.py`. Each sets `mock_model.extra_headers = {"endpoint_path": …}`; they should set the field and leave the bag to the headers that belong in it.
- [x] Verify against the live payload that the key still parses into the field and that `x-portkey-config` still lands in `extra_headers` — a real boot, not only mocks.
- [x] Gates: targeted tests, `make tb`, stage + `make agent-check`.

## Phase 2 — the shape guard

Goal: an unknown per-model key is either a plausible header or a loud error, and never a silent outbound string. TDD throughout — each box's test lands red first.

- [x] **Tests first (red):** new `tests/unit/pipelex/cogt/model_backends/test_model_spec_key_policy.py` — header-shaped key accepted; snake_case unknown rejected; D3 near-miss (`max-tokens`) rejected; known blueprint field never diverted.
- [x] New `pipelex/cogt/model_backends/model_spec_keys.py` (D1): the pure classifier plus `ModelSpecSource` (D2).
- [x] Wire it into `InferenceBackendLibrary.load` (`backend_library.py:195-199`), replacing the unconditional loop. Local source raises `InferenceBackendLibraryError` with D6's message; gateway source prunes.
- [x] **Tests (red first):** a local backend TOML carrying a synthetic unknown snake_case key fails the load with a message naming the key, the model and the file; the same key in a remote payload is pruned and the boot survives. Extend `test_gateway_unknown_defaults.py` rather than starting a parallel module — it already owns the remote-tolerance story, including the no-log-hub constraint.
- [x] **Regression, and the point of the whole change:** `x-portkey-provider` from local `portkey.toml` and `x-portkey-config` from the remote payload still reach `extra_headers` and still reach the wire.
- [x] **Leniency interaction:** confirm what a rejected key does under `lenient=True`. A typo must not silently delete a backend — that is the existing ruling in `InferenceBackendLibrary.load`'s docstring, and this new raise sits inside the same `try`. Decide deliberately and record the answer here; if it needs to escape the lenient skip, say why in a comment at the raise site.
- [x] **Mutation-check the new tests:** revert the guard, confirm the new tests go red, restore. A guard whose tests pass without it is not a guard.
- [x] Gates: `make tb`, targeted tests, stage + `make agent-check`, **full `make agent-test`**.

### ✋ CHECKPOINT — HARD STOP

Do not start Phase 3 without Louis' explicit go. This is where a config that booted yesterday can fail today. Present: the diff, the test results, the answer to the leniency question, and a **worked example of the new error message** as a user would see it. Louis rules on D3 (near-miss), on the leniency behaviour, and on the commit/PR shape. Update the checkpoint log.

---

## Phase 3 — Docs, changelog, dogfood

- [x] `docs/configuration/config-technical/inference-backend-config.md` — document the mechanism for the first time: extra per-model keys are sent to the provider as request headers, they must be header-shaped, anything else is a configuration error, and `endpoint_path` is a declared field. Include what a rejected key looks like.
- [x] Changelog `## [Unreleased]`, condensed style, **breaking**: a per-model key that is neither a known model-spec field nor header-shaped now fails the backend load instead of being sent to the provider as a request header; `endpoint_path` is a declared model-spec field.
- [x] Append a dogfood entry to `wip/drift-contracts/dogfood-log.md`. The observation worth recording: **`backend_library.py` shapes user-facing configuration and sits in no contract's trigger set** — the same shape of finding as the Phase 4 templating entry (a config surface documented outside `docs/configuration/`), from the other direction. Record it; per the pilot's bias, do not act on it here.
- [x] Gates: stage + `make agent-check`.

## Cross-repo / release-gated follow-ups

- **The downstream backend-TOML sweep gets louder, and that is the good news.** The templating-style plan already lists this as its one non-optional follow-up: every repo shipping `.pipelex/inference/backends/*.toml` still declares `prompting_target`, and `portkey.toml` carries it **per-model as well as in `[defaults]`**, so a fix that deletes only the `[defaults]` line unblocks the boot while quietly turning the per-model ones into outbound headers. With this guard in place that residue becomes a boot error naming the key instead. Confirmed tracked-file hits at the time of writing: `pipelex-api/`, `cocode/`, `pipelex-cookbook/`, `mthds-ui/`, plus our hosted worker, our demo repos, and fixtures in our JS runtime (all private). **Ship this guard in or after the release that deletes `prompting_target`, never before** — before, it would reject the key while the field still exists.
- **Our back-office repo** (private) owns the served gateway config, in its gateway-models TOML. Nothing to change now: `endpoint_path` becomes a declared field on the client side and `x-portkey-config` is header-shaped. Worth telling whoever maintains it that a *new* non-header per-model key would from now on be pruned by new clients rather than forwarded as a header.
- **Our JS runtime** (private repo) is a second consumer of the same wire contract and models these specs its own way, in its worker catalogue. Whether it wants a parallel rule is its own call, not this plan's.

## Considered and deferred

- **The backend-level twin** (`backend_library.py:154-156`): unknown *backend* keys are reclassified into `extra_config` with the same silence. Deferred because `extra_config` never reaches a provider — the failure is a local misconfiguration, not an outbound string. It is a small follow-up on its own, and the classifier built in Phase 2 would serve it directly.
- **Renaming `extra_headers`.** Once `endpoint_path` moves out, the field genuinely holds only headers and the name is finally honest. Renaming it touches every provider factory for zero behaviour change; do it only if it rides along with something else in that area.
- **Logging accepted headers at load time.** Tempting — "here is what we will send" — but the prune path runs before the log hub is configured, and the accepted path would need the same care. Not worth a boot-order dependency.

## Checkpoint log

### 2026-08-15 — Phase 1 and Phase 2 done, stopped at the ✋ checkpoint

**Branch and PR shape.** `feat/rogue-extra-headers-guard`, stacked on `fix/keyless-followups` (PR #1106), which is itself stacked on `fix/Keyless-dry-run` (PR #1104). Two commits, one per phase, so Phase 1 could ship alone if ever needed: "endpoint_path is a declared model-spec field, not an extra header" and "Unknown per-model backend keys are headers only if header-shaped". Opened as a draft PR because Phase 3 (docs, changelog, dogfood log) is not started.

**Re-measurement (2026-08-15).** Identical to the 2026-08-14 table: local `portkey.toml` carries `x-portkey-provider` per model and nothing else; the served `_12` payload carries `x-portkey-config` on every LLM model and `endpoint_path` on the four image models; the served `[defaults]` block is clean. The local `~/.pipelex/cache/remote_config.json` (`schema_version` / `cached_at` / `raw_config`, no source URL) was refreshed this morning, so this session did not reproduce the `_11`-body-under-a-`_12`-pin condition — but nothing in the change depends on it, and the remote path prunes rather than raises precisely so that condition stays harmless.

**What was built.**

- Phase 1: `endpoint_path: str | None = None` on `InferenceModelSpecBlueprint` and `InferenceModelSpec`, factory passthrough, `gateway_img_gen_worker.py` reads the field. The four image-worker tests set the field and leave `extra_headers` to headers. Verified with a real `Pipelex.make(needs_inference=False, needs_model_specs=True)` boot against the live payload: `gpt-image-1.endpoint_path` is the Azure route, `gpt-image-1.extra_headers == {'x-portkey-config': …}`, `gpt-4o-mini.endpoint_path is None`, and the local portkey model still carries `{'x-portkey-provider': '@openai'}`.
- Phase 2: `pipelex/cogt/model_backends/model_spec_keys.py` — `ModelSpecSource` (D2), `split_model_spec_keys` returning a `ModelSpecKeySplit(fields, headers, rejected)` NamedTuple, `RejectedModelSpecKey(key, near_miss_of)`, `describe_rejected_keys` for the wording. Fully keyword-only, no subject grant. `InferenceBackendLibrary.load` threads the source (`REMOTE_GATEWAY` on the `is_gateway_backend` branch, `LOCAL_FILE` otherwise) and does a `match`/`case`: local raises `InferenceBackendLibraryError`, remote prunes with no log call. `drop_unknown_gateway_defaults`'s docstring updated to point at the new per-model rule.
- Tests: `test_model_spec_key_policy.py` (classifier), three new cases in `test_backend_library_leniency.py` (unknown per-model key fatal in both modes naming key/model/file; near-miss fatal naming the field; `x-portkey-provider` still becomes a header), and a new `TestGatewayUnknownPerModelKeys` class (header kept, non-header pruned and boot survives, `endpoint_path` lands in the field, header reaches `GatewayFactory.make_extras`, prune needs no log hub).

**Gates.** `make tb`, `make agent-check` (staged), and the full `make agent-test` are all green. Mutation check done: with the guard replaced by the old "everything unknown is a header" behaviour, exactly the four guard tests go red; restored, all green.

**Answer to the leniency question.** A rejected key from a local file is fatal in *both* modes. No new mechanism was needed: the raise is an `InferenceBackendLibraryError` inside the same `try` as before, and the lenient `except` only catches `InferenceBackendCredentialsError`, so it lets this through — exactly the docstring's ruling ("a config typo must never silently delete a backend"). A comment at the raise site says so, and `test_an_unknown_per_model_key_in_a_local_backend_is_fatal_in_both_modes` is parametrized over `lenient`.

**Worked example of the error, as a user sees it** (a local `openai.toml` with `max_tokns = 4096` on `gpt-4o`):

> Unknown key on model 'gpt-4o' for backend 'openai' from file '.pipelex/inference/backends/openai.toml': 'max_tokns' is not a known model-spec field, and not header-shaped. A per-model key that is not a model-spec field is sent to the provider as a request header and must contain a hyphen (e.g. 'x-portkey-provider'): fix the typo, or name the key like a header if that is what it is meant to be.

The near-miss variant (`max-tokens = 4096`):

> Unknown key on model 'gpt-4o' for backend 'openai' from file '.pipelex/inference/backends/openai.toml': 'max-tokens' looks like the model-spec field 'max_tokens' spelled with hyphens — use 'max_tokens'. A per-model key that is not a model-spec field is sent to the provider as a request header and must contain a hyphen (e.g. 'x-portkey-provider'): fix the typo, or name the key like a header if that is what it is meant to be.

Several rejected keys on one model are listed in one message ("Unknown keys on model …: 'prompting_target' is …; 'max_tokns' is …"), with the rule stated once at the end.

**Awaiting Louis' rulings.**

- D3 (near-miss): built as planned; separable — dropping it removes `near_miss_of`, the second `describe` branch, and one test each in the classifier and leniency modules.
- Leniency: fatal in both modes, as above. Confirm.
- Commit/PR shape: two commits on one draft PR stacked on #1106. Confirm, or ask for a squash / a separate Phase 1 PR.

### 2026-08-15 — Louis' rulings, and Phase 3 done

**Rulings.** Leniency: **confirmed** — a rejected local key is fatal in both modes. D3 near-miss: **confirmed, kept**. PR shape: one PR (#1107), not a draft; two commits kept.

**Phase 3.** The docs page gained a "Sending extra request headers per model" subsection under Model Specifications — the mechanism's first documentation: the header rule, the shape requirement, the error as a user sees it, the lenient treatment of the served Gateway config, and `endpoint_path` as a declared field. Changelog: a condensed breaking entry under `[Unreleased]`, and the `prompting_target` removal entry's sentence about per-model keys becoming headers rewritten to the new truth. Dogfood log: recorded the "no contract has a stake in the backend-TOML schema" observation, paired with the 2026-08-14 scope-miss.

**Remaining:** nothing on this branch. The cross-repo / release-gated follow-ups below stand as written.

### 2026-08-15 — Review-bot pass on PR #1107

Three unresolved bot threads, two issues, both fixed. (1) codex + cubic: `TestGatewayUnknownPerModelKeys` shared a module with `TestGatewayUnknownDefaults`, against the one-TestClass-per-module rule — moved to its own `test_gateway_unknown_per_model_keys.py`. (2) cubic: a header-shaped key with a non-string value (`x-foo = 3`) fell through the classifier into strict `extra_headers: dict[str, str]`, so pydantic raised `string_type` — fatal for a *remote* payload too, which contradicts the skew-tolerance contract, and in pydantic's voice rather than D6's for a local file. The bot's suggested remedy (`str(value)`) was declined: stringifying `True` or a list onto the wire is the rogue header this branch exists to stop. Instead the value check joined the shape check: `RejectedModelSpecKey` now carries a `ModelSpecKeyRejection` reason (`NOT_HEADER_SHAPED` / `HYPHENATED_KNOWN_FIELD` / `NON_STRING_VALUE`), a non-string value is rejected like any other rogue key, and the loader's existing per-source `match` does the rest with no call-site change — local fatal naming key/model/file and saying the value must be a quoted string, remote pruned. The hyphen trailer in `describe_rejected_keys` is emitted only when a shape rejection is present, so a value-only failure is not told to add a hyphen. Tests red-first in the classifier, leniency and gateway per-model modules; docs page and changelog entry extended with the value half of the rule.

### 2026-08-15 — Review-bot pass on PR #1109

Five unresolved threads (one greptile, four cubic); four fixed, one deferred.

- **Fixed — near-miss got the hyphen trailer** (cubic, `describe_rejected_keys`). `HYPHENATED_KNOWN_FIELD` was grouped with `NOT_HEADER_SHAPED` under `is_about_shape`, so a lone `max-tokens` was told the key "must contain a hyphen … name the key like a header" right after being told to use `max_tokens` — the key already has a hyphen, and the advice contradicted its own message. The property is gone; only a `NOT_HEADER_SHAPED` rejection earns the trailer. Red-first test in the classifier module. The near-miss worked example in the Phase 1/2 checkpoint above therefore no longer carries the trailer.
- **Fixed — docs led with the old behaviour** (cubic, `inference-backend-config.md`). The subsection's first sentence said every extra key is sent as a header; it now states the gate up front, and the full rule paragraph follows unchanged.
- **Fixed — dogfood-log premise** (cubic, `wip/drift-contracts/dogfood-log.md`). The entry claimed the backend TOMLs are "neither the config model nor a shipped default"; they *are* shipped defaults (`pipelex/kit/configs/inference/backends/*.toml`, mirrored by the `.pipelex/` overrides). Reworded: the finding sharpens rather than dissolves — the contract's description promises "the shipped defaults" while its trigger set names only `pipelex/pipelex.toml`.
- **Fixed — stale "Superseded note"** (cubic, this file). The trailing paragraph reasserting Phase 3 as not done was an archived Phase 1/2 remark sitting after the Phase 3-done entries; deleted, since its one surviving fact (the `prompting_target` changelog sentence needed rewriting) is recorded in the rulings entry above.
- **Deferred — strict header-name/value validation** (greptile, `is_header_shaped`). h11 rejects an illegal name or value at send time, so it is a boot-vs-first-call timing gap for a deliberately quoted key, not a wire risk. Thread left open at the time; taken up the same day — see the entry below.

### 2026-08-15 — Strict header-name and header-value validation (the deferred greptile item, built)

Louis' ruling: close the gap now, at **wire parity** — boot rejects exactly what the HTTP stack rejects — landing as a third commit on PR #1109 so the thread closes where it was raised.

**The rule as built.** A key still has to be *shaped* like a header (contains a hyphen, string value) before anything else; the new gate asks whether it is *usable* as one. A header name must be an RFC 7230 token — letters, digits and `` !#$%&'*+-.^_`|~ `` — and a header value must be printable ASCII on a single line with no leading or trailing whitespace. Two new `ModelSpecKeyRejection` members carry it, `ILLEGAL_HEADER_NAME` and `ILLEGAL_HEADER_VALUE`, and `RejectedModelSpecKey` gained an `illegal_character` field so the name error can name the character — the failure is routinely invisible in the file (a pasted non-breaking space, a trailing space), which is the whole reason to say it out loud. `InferenceBackendLibrary.load` needed no edit at all: its per-source `match` already turns any rejection into a local fatal error or a remote prune, which is the payoff of D1 keeping the policy at the call site.

**Wire parity, measured not assumed.** Checked in the venv against h11 and httpx before writing the predicates: `x-foo bar`, `x-foo@bar`, `x-foo/bar`, `x-foo(bar)` and a non-ASCII name are refused (`LocalProtocolError: Illegal header name`, or `UnicodeEncodeError` from httpx); `a\r\nb`, a NUL, a leading space, a trailing space and a non-ASCII value are refused; `a b`, `a\tb`, the empty string, `x-foo_bar`, `x-foo.bar` and `x-foo|bar` are all accepted — underscore, dot and pipe are token characters, so the over-tightening trap has its own test. One deliberate divergence, recorded in the module docstring: h11 accepts `0x7f` (DEL) in a value and we do not. Deliberately **no** test couples our predicates to h11's own patterns — it is a transitive dependency of httpx, and the rule must not become "whatever this version of h11 does".

**Nothing in the wild moves.** Re-measured through the real classifier rather than a hand-rolled regex: every per-model key in `.pipelex/inference/backends/*.toml`, in the shipped `pipelex/kit/configs/inference/backends/*.toml`, and in the live `_12` payload still classifies exactly as before — `x-portkey-provider` and `x-portkey-config` accepted, nothing rejected. Confirmed by a real boot too (`Pipelex.make(needs_inference=False, needs_model_specs=True)`): the gateway models still carry `x-portkey-config`, `gpt-image-1.endpoint_path` still resolves to the Azure route, and the local Portkey model still carries `x-portkey-provider`.

**Worked examples, as a user sees them.**

> Unknown key on model 'gpt-4o' for backend 'openai' from file '.pipelex/inference/backends/openai.toml': 'x-foo bar' cannot be a header name: ' ' is not allowed in one — a header name may contain only letters, digits and the characters !#$%&'*+-.^_`|~.

> Unknown key on model 'gpt-4o' for backend 'openai' from file '.pipelex/inference/backends/openai.toml': 'x-foo' is header-shaped, but its value cannot be sent as a header value — it must be printable ASCII on a single line, with no leading or trailing whitespace.

Neither earns the hyphen trailer, and both have a test saying so: the key already has a hyphen, so "add a hyphen" would be the same contradiction the previous review pass removed from the near-miss message.

**Tests and mutation check.** New cases in all three modules that own this story — the classifier (`test_model_spec_key_policy.py`), the local-file fatal path (`test_backend_library_leniency.py`, including `x-foo = "trailing "`, valid TOML and invisible on the page), and the remote prune path (`test_gateway_unknown_per_model_keys.py`, where an illegal name or value is skew like any other and must not break the boot). Mutation check: with both new predicates stubbed to `return True`, exactly the new tests go red across the three modules and nothing else moves; restored, all green.
