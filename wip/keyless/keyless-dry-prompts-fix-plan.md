# Fix plan — a keyless boot must not change what a DRY run renders

**Written 2026-08-14 on `fix/Keyless-dry-run`, against tip `84b1f682c` (v0.44.0).** Brief: [`keyless-boot-changes-dry-prompts.md`](keyless-boot-changes-dry-prompts.md). Everything in §0 was measured on this branch today, not carried over from the 2026-08-08 measurement.

> ✅ **Re-scoped 2026-08-14 — the hold is lifted and the headline symptom is gone, dissolved rather than fixed.** The templating-style change shipped on this same branch ([design](../prompting-style/prompt-style-as-an-authoring-decision.md), [build](../prompting-style/templating-style-implementation-plan.md)): prompt shape is now declared on the pipe and defaulted from config, and **no code path consults the deck, a model spec, or a credential to decide it.** A keyless boot and a keyed boot therefore render byte-identical prompts by construction. **Symptoms 1 and 2 no longer exist, and neither do the fields they were about** — `prompting_target` and `derive_templating_style` are deleted. Part 1 (§3.2) is dissolved entirely; Part 3 (§3.4) loses its warning site.
>
> **What survives is a real bug and still worth fixing**, but it is a different bug than the one this plan was written for. A keyless boot still drops every backend, so the deck is still empty — and the deck still governs things that have nothing to do with prompting: symptoms 3, 4, 5 and 7 in §2. **Part 2 (§3.3) remains the core and is unchanged**; Part 4 (§3.5) remains the user-visible half. Sections below are annotated in place: struck premises are kept as the record of what was measured, not as instructions.
>
> ⚠️ **Re-judging the surviving residue is its own task.** With the headline symptom gone the cost/benefit has changed — the remaining symptoms are narrower and none of them silently rewrites output. Whether Part 2's `BackendLoadMode` surgery is still worth its blast radius is an open question for Louis, not a conclusion this plan should be read as having reached.

## 0. Re-verification, and one correction to the brief

### 0.1 The divergence reproduces ~~(dissolved — historical record)~~

> **Dissolved.** `derive_templating_style` is deleted; the style no longer comes from the deck at all, so the last column of this table has no meaning against current code. Kept because the *first three* columns still reproduce exactly as measured — a keyless boot still yields a 0-model deck — and that is the mechanism symptoms 3/4/5 ride on.

Booting `Pipelex.make(...)` three ways and asking for the deck-resolved default text setting's style:

| boot | machine | deck `inference_models` | resolved setting | `derive_templating_style` |
| --- | --- | --- | --- | --- |
| `needs_inference=True` | keyed | 75 | `claude-4.6-sonnet` | `xml/plain` |
| `needs_inference=False` | keyed | 2 | `claude-4.6-sonnet` | **`None`** |
| `needs_inference=False, needs_model_specs=True` | keyed | 75 | `claude-4.6-sonnet` | `xml/plain` |
| `needs_inference=False` | **no credentials at all** | **0** | `claude-4.6-sonnet` | **`None`** |
| `needs_inference=False, needs_model_specs=True` | **no credentials at all** | **0** | `claude-4.6-sonnet` | **`None`** |

`None` is not inert. `apply_tag_style` (`pipelex/tools/jinja2/jinja2_filters.py:120-122`) reads `TAG_STYLE` off the Jinja2 context and, when the key was never set, falls back to `TagStyle.TICKS` — so the step-2 prompt says ``result: ``` `` where a keyed run says `<result>`. The brief's reproduction table is accurate.

> **Both halves of that sentence are now false, deliberately.** There is no deck-derived style to be `None`, and `apply_tag_style` no longer has a `TICKS` fallback — a context with no tag style raises `Jinja2ContextError` rather than silently choosing a shape. The silent-rewrite failure mode this plan was named for cannot recur: the only two outcomes left are the authored style and a loud error.

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

The reason the faithful option is cheap: `max_prompt_images`, `rules`, `inputs`/`outputs` and costs live in the per-backend spec TOMLs, which need no credential to read. Only the *backend entry's* `${VAR}` substitution fails. The load conflates two unrelated things — "can I call this provider" and "do I know what its models are like" — and drops the second because the first failed.

> *(`prompting_target` was the fourth item on that list and the one the plan leaned on hardest; it no longer exists. The argument is unaffected — the remaining fields are just as credential-free, and `max_prompt_images` is what symptom 3 needs.)*

The gateway is the one genuine exception: its specs come from a remote fetch (`RemoteConfigFetcher.fetch_remote_config`, a public URL, no key needed for the fetch itself), so an offline keyless boot cannot know them. That residual is what §3.4 makes audible instead of silent.

## 1. The decision: faithful, with the residual said out loud

The brief asks the fix to choose between **faithful** and **cheap-but-honest**. Recommendation: **faithful**, because the metadata is free (§0.3) and because "same program, mocked leaves" is what a dry run is *for* — a rehearsal that quietly rewrites the script is worth less than no rehearsal. Concretely the invariant to establish:

> **Credentials gate inference. They do not gate knowledge of models.** A boot without credentials resolves the same models and the same model constraints as a boot with them; what it cannot do is call a provider.

*(The invariant originally said "the same prompting styles" too. That clause is now true unconditionally and for a different reason — prompt shape never consults the deck — so it is dropped rather than claimed as a benefit of this fix.)*

One thing the invariant deliberately does not promise, handled in §3.4: gateway-hosted models on an **offline** keyless boot are unknowable, so warned. *(The second exception — an external-LLM-plugin model, absent from the deck, where a `None` style stayed correct — is gone with the style derivation.)*

## 2. Blast radius, enumerated

The brief asks for this enumeration as part of the fix. Everything a keyless boot changes, via the one mechanism "the deck has no `InferenceModelSpec`":

| # | Symptom | Mechanism | Site | Status |
| --- | --- | --- | --- | --- |
| ~~1~~ | ~~Step-2 prompts tag step-1 output with ``` ``` ``` instead of `<…>`~~ | ~~style `None` → Jinja2 `TAG_STYLE` unset → `TICKS`~~ | — | **✅ dissolved** — no deck-derived style, and no `TICKS` fallback to land in |
| ~~2~~ | ~~An **explicitly set** `llm_setting.prompting_target` is ignored~~ | ~~deck lookup short-circuits to `None`~~ | — | **✅ dissolved** — the field is deleted; the authored `templating_style` on the pipe is the only declaration and it is always honoured |
| 3 | `PipeImgGen`'s `max_prompt_images` limit is not enforced | `model_spec` `None` → limit `None` → check skipped | `pipe_operators/img_gen/pipe_img_gen.py:172-173`, `img_gen_prompt_blueprint.py:81` | code-read, test in §3.1 |
| 4 | `PipeImgGen` param-support validation is skipped | `spec is None` → early return | `pipe_operators/img_gen/pipe_img_gen.py:100-104` | code-read |
| 5 | A bundle pinning a **bare model handle** is *rejected* on a keyless machine | `is_model_handle_defined` false against an empty deck | `cogt/models/model_deck_check.py:91-101` | **measured** (`ModelChoiceNotFoundError`) |
| 6 | Deck preset validation degrades to log-only noise | every handle missing → `missing_presets_reaction = "log"` | `cogt/models/model_deck.py:612-630`, `pipelex.toml:140` | code-read |
| 7 | The two CLIs disagree with each other on a keyless machine | `pipelex run --dry-run` boots **keyed** (so it fails outright without keys); `pipelex-agent run --dry` boots keyless (so it degrades silently) | `cli/commands/run/_run_core.py:419` vs `cli/agent_cli/commands/run/*_cmd.py` | code-read |

~~Item 5 is the loud converse of item 1 and belongs in the same fix: today a keyless process silently rewrites prompts for preset-pinned methods *and* hard-rejects handle-pinned ones. Both stop once the deck is populated.~~

**Item 5 now stands alone, and that changes its character.** With item 1 dissolved there is no longer a silent-rewrite half to pair it with: what remains is a keyless process *loudly rejecting* handle-pinned bundles. A loud wrong answer is a much weaker motivation for the Part 2 surgery than a silent one was — it is visible, diagnosable, and arguably even defensible ("this machine cannot resolve that handle"). This is the single biggest input into the re-judging flagged in the banner.

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
2. ~~`derive_templating_style(...)` is equal and non-`None` on both sides~~ — **dropped, the function is deleted.**
3. A bundle pinning a bare handle passes `check_llm_choice_with_deck` on both sides (today: `ModelChoiceNotFoundError` on the empty side — item 5).

Then the end-to-end assertion the brief actually asks for, `tests/integration/pipelex/pipes/test_dry_prompt_parity_keyless.py`: a two-step method whose second `PipeLLM` embeds the first's output, dry-run under both providers, asserting the two `LlmTextResult.rendered_prompt` values are **identical** — not merely both non-empty. (`tests/unit/pipelex/pipe_operators/pipe_llm/test_prompt_rendering_purity.py` is the precedent for reaching the rendered prompt.)

> **This one is now green before any production edit, and is worth writing anyway — as a guard, not as a receipt.** Prompt rendering no longer reads the deck, so the parity it asserts holds by construction. That makes it exactly the kind of test the sequencing step 5 warns about (*"a parity test that passes against the old code is testing nothing"*) — it must be understood as a regression guard against re-coupling prompt shape to infrastructure, and it should be labelled as such in its docstring so a future reader does not mistake it for evidence that Part 2 works.

And one for item 3: a `PipeImgGen` given more input images than the model's `max_prompt_images`, dry-run keyless with `EmptySecretsProvider`, must raise — today it passes.

### 3.2 ~~Part 1 — style derivation precedence~~ ✅ DISSOLVED — do not build

> **Nothing in this section is buildable or wanted.** `derive_templating_style` and `llm_setting.prompting_target` are both deleted; the four-case precedence table below describes a resolution that no longer has any inputs. The concern it encoded — *an explicitly authored declaration must beat an inferred one* — is satisfied structurally: `resolve_templating_style(authored=…)` returns the authored style when there is one and the config default otherwise, with nothing in between to override it. Kept only so a reader of the original plan can see why this part vanished.

<details>
<summary>Original Part 1 (obsolete)</summary>

Unit module `tests/unit/pipelex/kernel/test_derive_templating_style.py`, stubbing the deck on the hub (`tests/unit/pipelex/cli/test_agent_models_cmd.py:86` shows the fake-deck pattern):

| case | expected | today |
| --- | --- | --- |
| setting carries `prompting_target`, deck has the model | the setting's target wins | deck's target wins — **red** |
| setting carries `prompting_target`, deck has **no** such model | the setting's target is honoured | `None` — **red** |
| setting has no target, deck has the model | the model's target | same — green, pin it |
| setting has no target, deck has no model | `None` (external-plugin case) | same — green, pin it |

Implementation in `pipelex/kernel/llm_ops.py:62-75`: read `llm_setting.prompting_target` first and only consult the deck when it is unset. Keeps the documented `None` path intact and makes an explicitly-pinned target authoritative — which it always should have been.

</details>

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

Once Part 2 lands, a missing model spec on a keyless boot means something specific and narrow: *this model's metadata is genuinely unknowable here* (gateway model, no network, dummy specs) — not "we forgot to load anything". Warn exactly there, and only there.

> **The warning site named below is deleted; the need is smaller but not zero.** `derive_templating_style` was where this plan proposed to warn, because a silently-wrong prompt shape was the damage being detected. That damage is gone. What is left worth warning about is narrower: a model whose spec is unknowable still silently skips the `max_prompt_images` check (symptom 3) and the param-support validation (symptom 4). If Part 2 is built, warn at *those* two sites — where a constraint is being skipped rather than enforced — and drop the notion of a style-derivation warning entirely.

- ~~In `derive_templating_style`, when the deck has no model **and** `is_dry_run_forced()` is set, emit a `log.warning` naming the handle and the fallback tag style.~~ **Obsolete.** Replace with: at the `max_prompt_images` and param-support checks, when the spec is absent under a forced-dry boot, log that the constraint was not enforced and why.
- Dedupe per boot, not per run: keep the already-warned handles on the `ModelDeck` instance, which is rebuilt at each boot. **Not** a ContextVar and not module-global state (`payload-first, no ContextVars`; a process-global set leaks across runs in a server). *(Unchanged — this part of the design survives whichever site does the warning.)*

### 3.5 Part 4 — entry-point audit

- `cli/commands/run/_run_core.py:419` boots with the default `needs_inference=True` even for `--dry-run`, so `pipelex run --dry-run` demands credentials it never uses — and outright fails on a keyless machine, while `pipelex-agent run --dry` succeeds and degrades. Change to `needs_inference=not dry_run`. This is what makes the documented promise in `docs/features/validation-dry-run.md` ("no API calls required") true for both CLIs, and it is the user-visible half of the fix.
- Re-check `graph_cmd.py:160` and `show_cmd.py:312` (neither asks for specs today; after Part 2 they get metadata anyway — confirm neither now does surprise network I/O).
- Confirm the programmatic path the brief reproduces with, plain `Pipelex.make(needs_inference=False)`, is faithful for every locally-configured backend without needing `needs_model_specs=True`.

## 4. Sequencing

1. **Part 0 tests** — commit red (or `xfail` with a reason naming this doc, flipped in step 4). They are the receipt that the bug existed. *(Assertion 2 is dropped and the prompt-parity test is green from the start — see §3.1.)*
2. ~~**Part 1** — self-contained; can merge on its own if Part 2 stalls.~~ **Dissolved; Part 2 no longer has a cheap independent sibling to ship ahead of it.**
3. **Part 2** — the core. ⛳ *Checkpoint*: at this point re-run the §3.1 gate and record actual numbers in this doc before touching the CLI surface; Part 2 is where a hidden `all_enabled_backends()` consumer would show up.
4. **Parts 3 + 4**, then flip the xfails.
5. **Mutation-check the gate**: revert Part 2 locally and confirm the *deck-count and handle-resolution* assertions go red. ⚠️ **Do not mutation-check against the prompt-parity test** — it passes with or without Part 2 now, by construction; using it as the mutation target would produce a false green on the whole gate.
6. `make agent-check` && `make agent-test`.

## 5. Decisions for Louis

- **⚠️ First, the prior question: is any of this still worth building?** The symptom that justified "faithful over cheap" — a dry run silently validating a prompt that will not be sent — is gone. Every survivor is either loud (5) or a skipped constraint check (3, 4) or a CLI inconsistency (7). Part 4 is cheap and clearly right on its own; Part 2 is the expensive one and now has to earn its keep against a weaker case. Recommend deciding Part 2 and Part 4 **separately** rather than as one plan.
- **Faithful over cheap** (§1) — confirm, *if Part 2 proceeds at all*. The alternative is a log line and a documented divergence, which is honest but leaves dry-run-as-validation skipping constraint checks it claims to run.
- **`pipelex run --dry-run` stops requiring credentials** (§3.5). Behaviour change, arguably breaking for anyone relying on it as a credential check. It is the right default, but say so in the changelog.
- **Handle-pinned bundles start validating keylessly** (item 5). A bundle that today fails `pipelex-agent validate` on a keyless machine will pass. That is a fix, but it changes CI outcomes for keyless runners.
- **Does `needs_model_specs` survive?** After Part 2 it means only "fetch the gateway's remote specs rather than dummy them" — i.e. a *network* flag, not a metadata flag. Either rename it (`needs_gateway_specs`) or document the narrowed meaning. Renaming touches every CLI command listed in §2 item 7; recommend renaming, since the current name is precisely what made the brief's closing sentence wrong.

## 6. Docs, changelog, drift

- `docs/features/validation-dry-run.md` — state the guarantee and its two exceptions (§1).
- `docs/under-the-hood/dry-run-mock-generation.md` — the credentials-vs-metadata split, and what the new warning means.
- Backend config docs — `missing_credential_vars` / uncredentialed-but-enabled as a visible state.
- `CHANGELOG.md` under `## [Unreleased]`: ~~the dry-run parity fix, the explicit-`prompting_target` fix,~~ and the `pipelex run --dry-run` credential change. *(The first two are dissolved and are already covered by the templating-style entry that shipped on this branch — do not double-report them.)*
- `make drift-plan` after staging — Part 2 touches config-model and CLI trigger files; ack with an honest rationale.

## 7. Out of scope

- Anything about *live* runs. This is a dry-run faithfulness fix.
- Making gateway specs available offline (a cache-warming feature, not this bug).
- The `missing_presets_reaction` policy (item 6) — after Part 2 the deck is populated, so the noise disappears on its own; if it does not, that is its own investigation.
