# `config_dir` at boot scopes the main TOML load but not the inference file paths

**Status:** deferred, with the docstrings narrowed to say exactly what the parameter does. Found by Codex on PR #1073. Attempted on that PR and backed out — the fix needs a public abstract interface widened, which is a decision of its own.

## What it does and does not scope

`RuntimeBoot.__init__(config_dir=…)` passes the directory to `runtime_hub.setup_config(config_dir=…)`, so the **main TOML** load becomes `package defaults + this directory` instead of following project → global layering.

It stops there. `models_manager.setup(...)` is called without path arguments, and `ModelManager.setup` falls back to the layered `config_manager.*` properties when they are `None`:

- `config_manager.backends_file_path` → `inference/backends.toml`
- `config_manager.backends_dir_path` → `inference/backends/`
- `config_manager.routing_profiles_file_path` → `inference/routing_profiles.toml`
- `config_manager.model_decks_dir_path` → `inference/deck/`

Each resolves from the *detected* project or global config dir. So a boot pointed at an alternate `config_dir` combines that directory's main settings with whatever inference tree happens to be detected — cross-contamination between two config trees, silently.

There is a **fifth** unscoped read, and it is not an inference path at all: the gateway consent/onboarding state.

```python
pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)
```

That is hardcoded to the global dir, so a `config_dir`-scoped boot still reads `~/.pipelex/` for terms acceptance and `inference_setup_completed` — the two whose absence raises `GatewayTermsNotAcceptedError` / `InferenceSetupRequiredError`. Compounding it, the `config_dir` branch of `load_config` skips `ensure_global_config_exists()`, so a scoped boot never materialises the tree that this line then reads.

Unlike the four inference paths, it is **not obvious that scoping this one is correct**: terms acceptance is per-user consent, and per-user global state is arguably where it belongs no matter which config directory a given boot reads. That is the question to settle first — the fix here may be "document it as intentional" rather than "propagate `config_dir`". It is listed with the others because the *documented limit* had omitted it, not because the behaviour is known to be wrong.

`ModelManager.setup`'s own comment already says this is the intended remedy: *"Override paths let the doctor scope --global properly; default None falls back to layered config_manager paths for all other callers."* The doctor's `--global` path does exactly that, pinning all four with the comment *"so layered config_manager.X resolution doesn't silently fall back to the project-local files."*

## Why it was not fixed on PR #1073

The four-line propagation was written, tested, and backed out for one reason: **the path overrides exist on the concrete `ModelManager`, not on `ModelManagerAbstract`.**

`RuntimeBoot.models_manager` is typed `ModelManagerAbstract` — and that is deliberate, because `models_manager` is a documented `make()` injection point, so an embedder may supply their own. Pyright rejects the call:

```
error: No parameter named "backends_library_path" (reportCallIssue)
```

The doctor avoids this only by constructing a concrete `ModelManager()` itself.

This repo's own rule forbids the shortcut: *"When a getter returns a Protocol type, callers must only rely on methods declared on that Protocol. If you need to call a method that lives on a concrete implementation, extend the Protocol — do not work around it with `isinstance`, `cast`, or inline imports."* So the honest fix is to widen `ModelManagerAbstract.setup()` with the four optional path parameters and update every implementation — a change to a public injection contract, which does not belong inside a placement refactor whose whole claim is that behaviour is unchanged.

Two smaller observations that argue for doing it properly rather than quickly:

- Completing the scoping makes an explicit `config_dir` **require a complete config directory**. Verified: with the paths pinned, a directory holding only `pipelex.toml` fails boot with `InferenceBackendLibraryNotFoundError`. That is the correct contract — it is what "only this directory is read" means, and what `~/.pipelex` satisfies because `ensure_global_config_exists` materialises it from kit templates — but it is a real behavioural requirement that deserves to be introduced deliberately, not as a side effect.
- The four path literals are currently spelled inline in `doctor_cmd.py` (`"inference"`, `"backends.toml"`, …) while `config_loader.py` already owns them as constants (`INFERENCE_DIR_NAME`, `BACKENDS_FILE_NAME`, `BACKENDS_DIR_NAME`, `ROUTING_PROFILES_FILE_NAME`, `MODEL_DECKS_DIR_NAME`). A second copy would double a drift risk that should instead be collapsed.

## Suggested shape

1. Widen `ModelManagerAbstract.setup()` with the four optional path parameters, and update every implementation (`@override` will surface any that drift).
2. Add a `config_manager` helper that derives the scoped set from a directory — something like `inference_paths_for(config_dir)` returning the four — and use it from **both** `RuntimeBoot.setup` and `doctor_cmd`, replacing doctor's inline literals. That is the step that removes the drift risk rather than duplicating it.
3. Pin it with the negative that matters: a `config_dir` holding only `pipelex.toml` must **fail** rather than quietly borrowing another tree's backends. That test was written on #1073 and verified to fail when the propagation is reverted, so it can be lifted straight from this branch's history.
4. Document the "complete config directory required" contract on `config_dir` in both `make()` docstrings.

## What exists today instead

Both `make()` docstrings now state the limit explicitly and point here, so the parameter no longer promises isolation it does not deliver. The boot carries a `NOTE:` at the `models_manager.setup` call naming the same thing.
