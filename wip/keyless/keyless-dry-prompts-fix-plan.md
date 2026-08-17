# Fix plan — a keyless boot must not change what a DRY run validates

**Written 2026-08-14 on `fix/Keyless-dry-run` (measured at v0.44.0), for the brief in [`keyless-boot-changes-dry-prompts.md`](keyless-boot-changes-dry-prompts.md). Re-scoped the same day, when the templating-style change dissolved the headline symptom, and again on 2026-08-15 when Part 4 shipped.** What is left is a real bug and still worth fixing, but a narrower one than the plan was written for: a keyless boot drops every backend, so the deck is empty — and the deck governs things that have nothing to do with prompting.

**Status:**

- **Part 4 — ✅ shipped** on the stacked branch `fix/keyless-followups`: `pipelex run --dry-run` boots keyless, like `pipelex-agent run --dry-run` (§3.4).
- **Part 2 — ⏸ awaiting Louis' ruling** (§5). It is the core and the expensive half, and its case got weaker when the silent-rewrite symptom vanished; whether it is still worth its blast radius is an open question, not a conclusion this plan has reached.
- **Parts 0 and 3** — build only with Part 2; they have no meaning without it.

## 0. The mechanism, measured

### 0.1 A keyless boot yields an empty deck

Booting `Pipelex.make(...)` several ways and counting the deck:

| boot | machine | deck `inference_models` |
| --- | --- | --- |
| `needs_inference=True` | keyed | every configured model |
| `needs_inference=False` | keyed | only the backends whose key happens to be set |
| `needs_inference=False, needs_model_specs=True` | keyed | every configured model |
| `needs_inference=False` | **no credentials at all** | **0** |
| `needs_inference=False, needs_model_specs=True` | **no credentials at all** | **0** |

Re-verified live on 2026-08-15 with a scratch `HOME` holding no `.env` and every `*_API_KEY` unset: a bundle pinning `model = "gpt-4o-mini"` fails a dry run with *"Model handle 'gpt-4o-mini' was not found in the model deck"*, and passes on the same code with credentials present.

### 0.2 `needs_model_specs=True` is **not** the credential-free seam

The brief assumed it was. It is not: on a machine with **no credentials**, `needs_model_specs=True` changes nothing, because it only governs whether the *gateway's* remote specs are fetched or dummied (`pipelex/runtime_boot.py`). The thing that actually empties the deck is a different flag on a different axis:

```
runtime_boot.setup(needs_inference=False)
  → ModelManager.setup(needs_inference=False)
    → InferenceBackendLibrary.load(lenient=True)
      → every backend whose `api_key = "${…}"` cannot substitute
        is SKIPPED entirely (log.verbose only — invisible at default log level)
    → build_deck(enabled_backends=[])
      → deck.inference_models == {}
```

Every shipped backend declares its key as a `${VAR}` (`pipelex/kit/configs/inference/backends.toml`), the gateway included. So on a keyless machine **`lenient=True` drops every backend**, and `lenient` is wired to `needs_inference`, not to `needs_model_specs`. There is currently *no* flag combination that gives a credential-free process a populated deck. Note that since the templating-style branch, `lenient` swallows *only* `InferenceBackendCredentialsError` — a broken config file is fatal in both modes — so the conflation left to break is exactly "cannot call this provider" vs "do not know what its models are like".

This is not "flip the existing seam on"; it is "build the seam".

### 0.3 The metadata is already credential-free on disk

`max_prompt_images`, `rules`, `inputs`/`outputs` and costs live in the per-backend spec TOMLs, which need no credential to read. Only the *backend entry's* `${VAR}` substitution fails. The load conflates two unrelated things — "can I call this provider" and "do I know what its models are like" — and drops the second because the first failed.

The gateway is the one genuine exception: its specs come from a remote fetch (a public URL, no key needed for the fetch itself), so an offline keyless boot cannot know them. That residual is what §3.3 makes audible instead of silent.

## 1. The decision: faithful, with the residual said out loud

Recommendation, *if Part 2 proceeds at all*: **faithful**, because the metadata is free (§0.3) and because "same program, mocked leaves" is what a dry run is *for* — a rehearsal that quietly skips checks is worth less than no rehearsal. The invariant to establish:

> **Credentials gate inference. They do not gate knowledge of models.** A boot without credentials resolves the same models and the same model constraints as a boot with them; what it cannot do is call a provider.

One thing the invariant deliberately does not promise, handled in §3.3: gateway-hosted models on an **offline** keyless boot are unknowable, so warned.

## 2. Blast radius, enumerated

Everything a keyless boot changes, via the one mechanism "the deck has no `InferenceModelSpec`":

| # | Symptom | Mechanism | Site | Status |
| --- | --- | --- | --- | --- |
| 3 | `PipeImgGen`'s `max_prompt_images` limit is not enforced | `model_spec` `None` → limit `None` → check skipped | `pipe_operators/img_gen/pipe_img_gen.py`, `img_gen_prompt_blueprint.py` | code-read, test in §3.1 |
| 4 | `PipeImgGen` param-support validation is skipped | `spec is None` → early return | `pipe_operators/img_gen/pipe_img_gen.py` | code-read |
| 5 | A bundle pinning a **bare model handle** is *rejected* on a keyless machine | `is_model_handle_defined` false against an empty deck | `cogt/models/model_deck_check.py` | **measured** (`ModelChoiceNotFoundError`, re-verified 2026-08-15) |
| 6 | Deck preset validation degrades to log-only noise | every handle missing → `missing_presets_reaction = "log"` | `cogt/models/model_deck.py`, `pipelex.toml` | code-read |
| 7 | The two CLIs disagreed on a keyless machine | `pipelex run --dry-run` booted **keyed** (failed outright without keys); `pipelex-agent run --dry` booted keyless | `cli/commands/run/_run_core.py` | **✅ fixed** — Part 4 |

**Item 5 is the strongest survivor, and it stands alone.** It used to be paired with a *silent* prompt rewrite; what remains is a keyless process *loudly* rejecting handle-pinned bundles. A loud wrong answer is a much weaker motivation for the Part 2 surgery than a silent one was — it is visible, diagnosable, and arguably defensible ("this machine cannot resolve that handle") — but it does mean a keyless CI runner or an agent authoring before keys are configured gets a false rejection for any method that pins a handle. This is the single biggest input into the ruling in §5.

**Verified non-effects** (so the fix does not chase them): dry-run mock usage records are model-independent — `dry_mock.py` uses fixed `DRY_RUN_INFERENCE_MODEL_*` constants — and mock text length comes from `dry_run_config`, not from any spec.

## 3. The fix

TDD throughout: each part lands its tests first, red, then the implementation that turns them green.

### 3.1 Part 0 — characterization tests (all red before any production edit)

New module `tests/integration/pipelex/system/test_keyless_boot_model_metadata.py`, sibling to the existing `test_keyless_boot_forced_dry.py` (reuse its module-scoped `Pipelex.teardown_if_needed()` fixture pattern).

**The two-sided gate must differ in exactly one variable — credential presence — and nothing else.** Do *not* compare a keyed boot against a keyless one: that varies the boot flag too, and CI machines may or may not carry real keys. Instead inject two secrets providers into an otherwise identical keyless boot:

- `EmptySecretsProvider` — every lookup raises `SecretNotFoundError` (a genuinely keyless machine).
- `FakeCredentialedSecretsProvider` — every lookup returns `"fake-key"` (a credentialed machine; no call is ever made, the boot is forced-DRY).

Both via `Pipelex.make(secrets_provider=…, needs_inference=False)`. Assertions, all failing today:

1. `len(deck.inference_models)` is equal on both sides (today: 0 vs every configured model).
2. A bundle pinning a bare handle passes `check_llm_choice_with_deck` on both sides (today: `ModelChoiceNotFoundError` on the empty side — item 5).
3. A `PipeImgGen` given more input images than the model's `max_prompt_images`, dry-run keyless with `EmptySecretsProvider`, raises — today it passes (item 3).

Optional guard, not a receipt: `tests/integration/pipelex/pipes/test_dry_prompt_parity_keyless.py` — a two-step method whose second `PipeLLM` embeds the first's output, dry-run under both providers, asserting the two rendered prompts are **identical**. It is green before any production edit, because prompt rendering no longer reads the deck; it guards against re-coupling prompt shape to infrastructure and must be labelled as such in its docstring. **Never use it as the mutation-check target for Part 2** — it passes with or without Part 2, so it would produce a false green on the whole gate.

### 3.2 Part 2 — credential-free model metadata (the core)

**The conflation to break:** a lenient load answers "cannot resolve this backend's credential" by dropping the backend, and with it every fact about its models.

Unit module `tests/unit/pipelex/cogt/model_backends/test_backend_library_metadata_load.py` — a temp-dir `backends.toml` + one backend spec TOML + `EmptySecretsProvider`:

1. metadata-only load: the backend **is present**, its `model_specs` carry `max_prompt_images` and friends, `api_key is None`, and `missing_credential_vars == ["…_API_KEY"]`.
2. credentials-required load (a keyed boot): still raises `InferenceBackendCredentialsError` — unchanged.
3. metadata-only load of a **malformed** spec file: still fatal — unchanged (a config typo must never silently delete a backend).
4. a backend with missing credentials is reported as enabled-but-uncredentialed, and is **not** in `all_credentialed_backends()`.

Implementation:

- Replace the `lenient: bool` parameter of `InferenceBackendLibrary.load` with an explicit `BackendLoadMode` StrEnum — `REQUIRE_CREDENTIALS` / `METADATA_ONLY`. Credential errors no longer skip the backend in `METADATA_ONLY`; nothing else changes.
- Substitution today is all-or-nothing: `apply_to_strings_recursive` raises on the first unresolvable `${VAR}`. Add a collecting variant that, in `METADATA_ONLY`, substitutes what resolves, records the names it could not, and leaves those fields unset. Note `${AZURE_API_BASE}`-style endpoints go the same way — irrelevant to metadata, relevant only to a call.
- `InferenceBackend` gains `missing_credential_vars: list[str]` and an `is_credentialed` property. Keep `all_enabled_backends()` returning uncredentialed backends — the deck must contain their models — and add `all_credentialed_backends()` for callers that mean "usable for inference".
- `ModelManager.setup` picks the mode from `needs_inference`.
- **Guard the live path loudly.** `pipelex/providers/openai/openai_client_factory.py` turns a `None` key into `"unused-no-auth-needed"`, which would surface a missing credential as a provider 401 rather than as our own error. Gate at the point a backend becomes a client/worker: an uncredentialed backend raises `InferenceBackendCredentialsError` there. Defence in depth — a keyless boot is forced-DRY so no worker should be built at all — but the placeholder is a live-fire hazard either way.
- Sweep `all_enabled_backends()` callers (doctor, `show backends`, the init flows) and move the ones that mean "credentialed" onto the new accessor. This is the part most likely to surprise; do it with a grep, not from memory.

Green after this: every assertion in §3.1 except any gateway-only model on an offline machine.

### 3.3 Part 3 — the residual, made audible

Once Part 2 lands, a missing model spec on a keyless boot means something specific and narrow: *this model's metadata is genuinely unknowable here* (gateway model, no network, dummy specs) — not "we forgot to load anything". Warn exactly there, and only there: at the `max_prompt_images` and param-support checks, when the spec is absent under a forced-dry boot, log that the constraint was not enforced and why.

Dedupe per boot, not per run: keep the already-warned handles on the `ModelDeck` instance, which is rebuilt at each boot. **Not** a ContextVar and not module-global state (payload-first, no ContextVars; a process-global set leaks across runs in a server).

### 3.4 Part 4 — entry-point audit — ✅ shipped

- `pipelex run --dry-run` boots `needs_inference=not dry_run` with `needs_model_specs=True`, the same boot `pipelex-agent run --dry-run` uses. Verified live: on a truly keyless machine the unfixed CLI died with *"Pipelex Gateway API key not set"*, the fixed one completes the dry run. Documented on `docs/tools/cli/run.md` and `docs/features/validation-dry-run.md` (including the item-5 limit, honestly), changelog entry under `[Unreleased]`, `cli-docs` drift contract acked.
- Still to confirm *if Part 2 lands*: `graph_cmd.py` and `show_cmd.py` boot with `needs_inference=False`; after Part 2 they get metadata anyway — confirm neither then does surprise network I/O. And the programmatic path, plain `Pipelex.make(needs_inference=False)`, becomes faithful for every locally-configured backend without needing `needs_model_specs=True`.

## 4. Sequencing (Parts 0, 2, 3)

1. **Part 0 tests** — commit red (or `xfail` with a reason naming this doc, flipped in step 3). They are the receipt that the bug exists.
2. **Part 2** — the core. ⛳ *Checkpoint*: re-run the §3.1 gate and record actual numbers in this doc before touching anything else; Part 2 is where a hidden `all_enabled_backends()` consumer would show up.
3. **Part 3**, then flip the xfails.
4. **Mutation-check the gate**: revert Part 2 locally and confirm the *deck-count and handle-resolution* assertions go red. Do not mutation-check against the prompt-parity guard.
5. `make agent-check` && `make agent-test`.

## 5. Decisions for Louis

- **⚠️ The prior question: is Part 2 still worth building?** The symptom that justified "faithful over cheap" — a dry run silently validating a prompt that would never be sent — is gone. Every survivor is either loud (5), a skipped constraint check (3, 4), or already fixed (7). The case *for*: item 5 gives keyless CI runners and pre-setup agents a false rejection on handle-pinned methods, and the invariant in §1 is the right one in principle. The case *against*: it is a loader-semantics change with a caller sweep and a live-path guard, for symptoms that are all visible or minor. If it proceeds, it is its own PR, not a rider.
- **Faithful over cheap** (§1) — confirm, if Part 2 proceeds. The alternative is a log line and a documented divergence (the docs already state the item-5 limit), which is honest but leaves dry-run-as-validation skipping constraint checks it claims to run.
- **Handle-pinned bundles start validating keylessly** (item 5). A bundle that today fails `pipelex-agent validate` on a keyless machine will pass. That is a fix, but it changes CI outcomes for keyless runners — say so in the changelog.
- **Does `needs_model_specs` survive?** After Part 2 it means only "fetch the gateway's remote specs rather than dummy them" — i.e. a *network* flag, not a metadata flag. Either rename it (`needs_gateway_specs`) or document the narrowed meaning. Renaming touches every CLI command that passes it; recommend renaming, since the current name is precisely what made the brief's closing assumption wrong.

## 6. Docs, changelog, drift (with Part 2)

- `docs/features/validation-dry-run.md` — replace the item-5 limit with the guarantee and its one exception (offline gateway models).
- `docs/under-the-hood/dry-run-mock-generation.md` — the credentials-vs-metadata split, and what the new warning means.
- Backend config docs — `missing_credential_vars` / uncredentialed-but-enabled as a visible state.
- `CHANGELOG.md` under `## [Unreleased]`: the keyless-validation change for handle-pinned bundles, and the `needs_model_specs` rename if taken.
- `make drift-plan` after staging — Part 2 touches config-model and CLI trigger files; ack with an honest rationale.

## 7. Out of scope

- Anything about *live* runs. This is a dry-run faithfulness fix.
- Making gateway specs available offline (a cache-warming feature, not this bug).
- The `missing_presets_reaction` policy (item 6) — after Part 2 the deck is populated, so the noise disappears on its own; if it does not, that is its own investigation.
