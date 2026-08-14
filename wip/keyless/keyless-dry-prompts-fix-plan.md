# Fix plan — a keyless boot must not change what a DRY run renders

**Written 2026-08-14 on `fix/Keyless-dry-run`, against tip `84b1f682c` (v0.44.0).** Brief: [`keyless-boot-changes-dry-prompts.md`](keyless-boot-changes-dry-prompts.md). Everything in §0 was measured on this branch today, not carried over from the 2026-08-08 measurement.

> ⏸ **On hold, and the headline symptom is likely to be dissolved rather than fixed.** Louis has decided prompt dialect should become a method-authoring decision instead of per-model infra config — see [`../prompting-style/prompt-style-as-an-authoring-decision.md`](../prompting-style/prompt-style-as-an-authoring-decision.md). Once prompt style depends on nothing but authored declarations and config, a keyless boot and a keyed boot agree by construction, and symptom 1 below (plus Part 1 and most of Part 3) stops existing. **Re-read this plan only after that design is settled**, and re-scope it to what actually survives: symptoms 3, 4, 5 and 7 in §2, which depend on the deck for reasons that have nothing to do with prompting.

## 0. Re-verification, and one correction to the brief

### 0.1 The divergence reproduces

Booting `Pipelex.make(...)` three ways and asking for the deck-resolved default text setting's style:

| boot | machine | deck `inference_models` | resolved setting | `derive_templating_style` |
| --- | --- | --- | --- | --- |
| `needs_inference=True` | keyed | 75 | `claude-4.6-sonnet` | `xml/plain` |
| `needs_inference=False` | keyed | 2 | `claude-4.6-sonnet` | **`None`** |
| `needs_inference=False, needs_model_specs=True` | keyed | 75 | `claude-4.6-sonnet` | `xml/plain` |
| `needs_inference=False` | **no credentials at all** | **0** | `claude-4.6-sonnet` | **`None`** |
| `needs_inference=False, needs_model_specs=True` | **no credentials at all** | **0** | `claude-4.6-sonnet` | **`None`** |

`None` is not inert. `apply_tag_style` (`pipelex/tools/jinja2/jinja2_filters.py:120-122`) reads `TAG_STYLE` off the Jinja2 context and, when the key was never set, falls back to `TagStyle.TICKS` — so the step-2 prompt says ``result: ``` `` where a keyed run says `<result>`. The brief's reproduction table is accurate.

### 0.2 The correction: `needs_model_specs=True` is **not** the faithful seam

The brief closes with "`needs_model_specs=True` already exists as that seam". It does not. The last two rows above are the measurement that matters — on a machine with **no credentials**, `needs_model_specs=True` changes nothing, because it only governs whether the *gateway's* remote specs are fetched or dummied (`pipelex/runtime_boot.py:295-342`). The thing that actually empties the deck is a different flag on a different axis:

```
runtime_boot.setup(needs_inference=False)
  → ModelManager.setup(needs_inference=False)                      # model_manager.py:72
    → InferenceBackendLibrary.load(lenient=True)                   # model_manager.py:83
      → every backend whose `api_key = "${…}"` cannot substitute
        is SKIPPED entirely                                        # backend_library.py:119-127
        (log.verbose only — invisible at default log level)
    → build_deck(enabled_backends=[])                              # model_manager.py:93
      → deck.inference_models == {}
```

Every shipped backend declares its key as a `${VAR}` (`pipelex/kit/configs/inference/backends.toml`), the gateway included (`${PIPELEX_GATEWAY_API_KEY}`). So on a keyless machine **`lenient=True` drops every backend**, and `lenient` is wired to `needs_inference`, not to `needs_model_specs`. There is currently *no* flag combination that gives a credential-free process a populated deck.

That reframes the fix: this is not "flip the existing seam on", it is "build the seam".

### 0.3 The metadata is already credential-free on disk

The reason the faithful option is cheap: `prompting_target` — and `max_prompt_images`, `rules`, costs — live in the per-backend spec TOMLs (`pipelex/kit/configs/inference/backends/openai.toml:26`), which need no credential to read. Only the *backend entry's* `${VAR}` substitution fails. The load conflates two unrelated things — "can I call this provider" and "do I know what its models are like" — and drops the second because the first failed.

The gateway is the one genuine exception: its specs come from a remote fetch (`RemoteConfigFetcher.fetch_remote_config`, a public URL, no key needed for the fetch itself), so an offline keyless boot cannot know them. That residual is what §3.4 makes audible instead of silent.

## 1. The decision: faithful, with the residual said out loud

The brief asks the fix to choose between **faithful** and **cheap-but-honest**. Recommendation: **faithful**, because the metadata is free (§0.3) and because "same program, mocked leaves" is what a dry run is *for* — a rehearsal that quietly rewrites the script is worth less than no rehearsal. Concretely the invariant to establish:

> **Credentials gate inference. They do not gate knowledge of models.** A boot without credentials resolves the same models, the same prompting styles and the same model constraints as a boot with them; what it cannot do is call a provider.

Two things the invariant deliberately does not promise, both handled in §3.4:

- Gateway-hosted models on an **offline** keyless boot: unknowable, so warned.
- A model served by an **external LLM plugin**: genuinely absent from the deck, `None` stays correct — and after the fix `None` on a keyless boot is distinguishable from `None` on a keyed one, which is exactly what the brief says the caller cannot do today.

## 2. Blast radius, enumerated

The brief asks for this enumeration as part of the fix. Everything a keyless boot changes, via the one mechanism "the deck has no `InferenceModelSpec`":

| # | Symptom | Mechanism | Site | Status |
| --- | --- | --- | --- | --- |
| 1 | Step-2 prompts tag step-1 output with ``` ``` ``` instead of `<…>` | style `None` → Jinja2 `TAG_STYLE` unset → `TICKS` | `kernel/llm_ops.py:71-75`, `tools/jinja2/jinja2_filters.py:120` | **measured** |
| 2 | An **explicitly set** `llm_setting.prompting_target` is ignored | deck lookup short-circuits to `None` before the explicit target is read | `kernel/llm_ops.py:71-74` | **measured** (independent bug, keyed boots too) |
| 3 | `PipeImgGen`'s `max_prompt_images` limit is not enforced | `model_spec` `None` → limit `None` → check skipped | `pipe_operators/img_gen/pipe_img_gen.py:172-173`, `img_gen_prompt_blueprint.py:81` | code-read, test in §3.1 |
| 4 | `PipeImgGen` param-support validation is skipped | `spec is None` → early return | `pipe_operators/img_gen/pipe_img_gen.py:100-104` | code-read |
| 5 | A bundle pinning a **bare model handle** is *rejected* on a keyless machine | `is_model_handle_defined` false against an empty deck | `cogt/models/model_deck_check.py:91-101` | **measured** (`ModelChoiceNotFoundError`) |
| 6 | Deck preset validation degrades to log-only noise | every handle missing → `missing_presets_reaction = "log"` | `cogt/models/model_deck.py:612-630`, `pipelex.toml:140` | code-read |
| 7 | The two CLIs disagree with each other on a keyless machine | `pipelex run --dry-run` boots **keyed** (so it fails outright without keys); `pipelex-agent run --dry` boots keyless (so it degrades silently) | `cli/commands/run/_run_core.py:419` vs `cli/agent_cli/commands/run/*_cmd.py` | code-read |

Item 5 is the loud converse of item 1 and belongs in the same fix: today a keyless process silently rewrites prompts for preset-pinned methods *and* hard-rejects handle-pinned ones. Both stop once the deck is populated.

**Verified non-effects** (so the fix does not chase them): dry-run mock usage records are model-independent — `dry_mock.py:152-165` uses fixed `DRY_RUN_INFERENCE_MODEL_*` constants — and mock text length comes from `dry_run_config`, not from any spec. The brief's "both report the same usage records" holds.

## 3. The fix, in four parts

TDD throughout: each part lands its tests first, red, then the implementation that turns them green.

### 3.1 Part 0 — characterization tests (all red before any production edit)

New module `tests/integration/pipelex/system/test_keyless_boot_model_metadata.py`, sibling to the existing `test_keyless_boot_forced_dry.py` (reuse its module-scoped `Pipelex.teardown_if_needed()` fixture pattern).

**The two-sided gate must differ in exactly one variable — credential presence — and nothing else.** Do *not* compare a keyed boot against a keyless one: that varies the boot flag too, and CI machines may or may not carry real keys. Instead inject two secrets providers into an otherwise identical keyless boot:

- `EmptySecretsProvider` — every lookup raises `SecretNotFoundError` (a genuinely keyless machine).
- `FakeCredentialedSecretsProvider` — every lookup returns `"fake-key"` (a credentialed machine; no call is ever made, the boot is forced-DRY).

Both via `Pipelex.make(secrets_provider=…, needs_inference=False)`. Assertions, all failing today:

1. `len(deck.inference_models)` is equal on both sides (today: 0 vs 75).
2. `derive_templating_style(llm_setting=resolve_llm_setting_for_text())` is equal and non-`None` on both sides (today: `None` vs `xml/plain`).
3. A bundle pinning a bare handle passes `check_llm_choice_with_deck` on both sides (today: `ModelChoiceNotFoundError` on the empty side — item 5).

Then the end-to-end assertion the brief actually asks for, `tests/integration/pipelex/pipes/test_dry_prompt_parity_keyless.py`: a two-step method whose second `PipeLLM` embeds the first's output, dry-run under both providers, asserting the two `LlmTextResult.rendered_prompt` values are **identical** — not merely both non-empty. (`tests/unit/pipelex/pipe_operators/pipe_llm/test_prompt_rendering_purity.py` is the precedent for reaching the rendered prompt.)

And one for item 3: a `PipeImgGen` given more input images than the model's `max_prompt_images`, dry-run keyless with `EmptySecretsProvider`, must raise — today it passes.

### 3.2 Part 1 — style derivation precedence (small, independent, ships alone)

Unit module `tests/unit/pipelex/kernel/test_derive_templating_style.py`, stubbing the deck on the hub (`tests/unit/pipelex/cli/test_agent_models_cmd.py:86` shows the fake-deck pattern):

| case | expected | today |
| --- | --- | --- |
| setting carries `prompting_target`, deck has the model | the setting's target wins | deck's target wins — **red** |
| setting carries `prompting_target`, deck has **no** such model | the setting's target is honoured | `None` — **red** |
| setting has no target, deck has the model | the model's target | same — green, pin it |
| setting has no target, deck has no model | `None` (external-plugin case) | same — green, pin it |

Implementation in `pipelex/kernel/llm_ops.py:62-75`: read `llm_setting.prompting_target` first and only consult the deck when it is unset. Keeps the documented `None` path intact and makes an explicitly-pinned target authoritative — which it always should have been.

### 3.3 Part 2 — credential-free model metadata (the core)

**The conflation to break:** `lenient` currently means both "tolerate a missing credential" and "tolerate a broken config file", and answers both by dropping the backend.

Unit module `tests/unit/pipelex/cogt/model_backends/test_backend_library_metadata_load.py` — a temp-dir `backends.toml` + one backend spec TOML + `EmptySecretsProvider`:

1. metadata-only load: the backend **is present**, its `model_specs` carry `prompting_target`, `api_key is None`, and `missing_credential_vars == ["…_API_KEY"]`.
2. credentials-required load (a keyed boot): still raises `InferenceBackendCredentialsError` — unchanged.
3. metadata-only load of a **malformed** spec file: still skipped, still `log.verbose` — unchanged.
4. a backend with missing credentials is reported as enabled-but-uncredentialed, and is **not** in `all_credentialed_backends()`.

Implementation:

- Replace the `lenient: bool` parameter of `InferenceBackendLibrary.load` (`backend_library.py:57-65`) with an explicit `BackendLoadMode` StrEnum — `REQUIRE_CREDENTIALS` / `METADATA_ONLY`. Structural-error skipping stays tied to `METADATA_ONLY`; credential errors no longer skip.
- Substitution today is all-or-nothing: `apply_to_strings_recursive` raises on the first unresolvable `${VAR}` (`backend_library.py:105-145`). Add a collecting variant that, in `METADATA_ONLY`, substitutes what resolves, records the names it could not, and leaves those fields unset. Note `${AZURE_API_BASE}`-style endpoints go the same way — irrelevant to metadata, relevant only to a call.
- `InferenceBackend` (`backend.py:38-48`) gains `missing_credential_vars: list[str]` and an `is_credentialed` property. Keep `all_enabled_backends()` returning uncredentialed backends — the deck must contain their models — and add `all_credentialed_backends()` for callers that mean "usable for inference".
- `ModelManager.setup` picks the mode from `needs_inference` (`model_manager.py:83`, `:88`).
- **Guard the live path loudly.** `pipelex/providers/openai/openai_client_factory.py:45` turns a `None` key into `"unused-no-auth-needed"`, which would surface a missing credential as a provider 401 rather than as our own error. Gate at the point a backend becomes a client/worker: an uncredentialed backend raises `InferenceBackendCredentialsError` there. Defence in depth — a keyless boot is forced-DRY (`runtime_boot.py:539`) so no worker should be built at all — but the placeholder is a live-fire hazard either way and is worth closing while we are here.
- Sweep `all_enabled_backends()` callers (doctor, `show backends`, the init flows) and move the ones that mean "credentialed" onto the new accessor. This is the part most likely to surprise; do it with a grep, not from memory.

Green after this: every assertion in §3.1 except any gateway-only model on an offline machine.

### 3.4 Part 3 — the residual, made audible

Once Part 2 lands, a `None` style on a keyless boot means something specific and narrow: *this model's metadata is genuinely unknowable here* (gateway model, no network, dummy specs) — not "we forgot to load anything". Warn exactly there, and only there:

- In `derive_templating_style`, when the deck has no model **and** `is_dry_run_forced()` (`runtime_hub.py:526`) is set, emit a `log.warning` naming the handle and the fallback tag style the prompt will actually use. On a keyed boot the same `None` stays silent — that is the external-plugin case, where `None` is correct and expected. This is the discriminator the brief says the caller lacks today.
- Dedupe per boot, not per run: keep the already-warned handles on the `ModelDeck` instance, which is rebuilt at each boot. **Not** a ContextVar and not module-global state (`payload-first, no ContextVars`; a process-global set leaks across runs in a server).

### 3.5 Part 4 — entry-point audit

- `cli/commands/run/_run_core.py:419` boots with the default `needs_inference=True` even for `--dry-run`, so `pipelex run --dry-run` demands credentials it never uses — and outright fails on a keyless machine, while `pipelex-agent run --dry` succeeds and degrades. Change to `needs_inference=not dry_run`. This is what makes the documented promise in `docs/features/validation-dry-run.md` ("no API calls required") true for both CLIs, and it is the user-visible half of the fix.
- Re-check `graph_cmd.py:160` and `show_cmd.py:312` (neither asks for specs today; after Part 2 they get metadata anyway — confirm neither now does surprise network I/O).
- Confirm the programmatic path the brief reproduces with, plain `Pipelex.make(needs_inference=False)`, is faithful for every locally-configured backend without needing `needs_model_specs=True`.

## 4. Sequencing

1. **Part 0 tests** — commit red (or `xfail` with a reason naming this doc, flipped in step 4). They are the receipt that the bug existed.
2. **Part 1** — self-contained; can merge on its own if Part 2 stalls.
3. **Part 2** — the core. ⛳ *Checkpoint*: at this point re-run the §3.1 gate and record actual numbers in this doc before touching the CLI surface; Part 2 is where a hidden `all_enabled_backends()` consumer would show up.
4. **Parts 3 + 4**, then flip the xfails.
5. **Mutation-check the gate**: revert Part 2 locally and confirm the parity test goes red. A parity test that passes against the old code is testing nothing.
6. `make agent-check` && `make agent-test`.

## 5. Decisions for Louis

- **Faithful over cheap** (§1) — confirm. The alternative is a log line and a documented divergence, which is honest but leaves dry-run-as-validation validating a prompt that will not be sent.
- **`pipelex run --dry-run` stops requiring credentials** (§3.5). Behaviour change, arguably breaking for anyone relying on it as a credential check. It is the right default, but say so in the changelog.
- **Handle-pinned bundles start validating keylessly** (item 5). A bundle that today fails `pipelex-agent validate` on a keyless machine will pass. That is a fix, but it changes CI outcomes for keyless runners.
- **Does `needs_model_specs` survive?** After Part 2 it means only "fetch the gateway's remote specs rather than dummy them" — i.e. a *network* flag, not a metadata flag. Either rename it (`needs_gateway_specs`) or document the narrowed meaning. Renaming touches every CLI command listed in §2 item 7; recommend renaming, since the current name is precisely what made the brief's closing sentence wrong.

## 6. Docs, changelog, drift

- `docs/features/validation-dry-run.md` — state the guarantee and its two exceptions (§1).
- `docs/under-the-hood/dry-run-mock-generation.md` — the credentials-vs-metadata split, and what the new warning means.
- Backend config docs — `missing_credential_vars` / uncredentialed-but-enabled as a visible state.
- `CHANGELOG.md` under `## [Unreleased]`: the dry-run parity fix, the explicit-`prompting_target` fix, and the `pipelex run --dry-run` credential change.
- `make drift-plan` after staging — Part 2 touches config-model and CLI trigger files; ack with an honest rationale.

## 7. Out of scope

- Anything about *live* runs. This is a dry-run faithfulness fix.
- Making gateway specs available offline (a cache-warming feature, not this bug).
- The `missing_presets_reaction` policy (item 6) — after Part 2 the deck is populated, so the noise disappears on its own; if it does not, that is its own investigation.
