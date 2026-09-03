---
status: active
item: L-260903-9fe4ad
---

# Override files for `backends.toml` and `routing_profiles.toml`

## Problem

The two inference documents, `.pipelex/inference/backends.toml` and `.pipelex/inference/routing_profiles.toml`, each resolved to exactly one file (the project's copy if it existed, otherwise `~/.pipelex/`) and were read whole. A developer who wanted to live on a non-default backend had to flip `[<backend>] enabled` and `active = "<profile>"` in two tracked files the kit mirrors, in every worktree and every sibling project: per-checkout dirt flagged by `check-config-sync`, one `git add -A` away from shipping a personal choice as the default. The concrete need was the manifold beta, which is not on `dev` yet; the mechanism is generic and was built and verified against the backends that are.

## Decisions

1. **Merge sequence is `[resolved base, global override, project override]`.** The base keeps winner-takes-all resolution; the overrides layer over it, global then project. This is deliberately not `pipelex.toml`'s order, where a project base beats a global override: every project carries a tracked `backends.toml`, so a project base that won would defeat a machine-wide override. With an explicit `config_dir` (doctor `--global`, an init targeting one directory) the sequence is that directory's base and its own override, mirroring `load_config(config_dir=)`.
2. **Two files, no environment variants, no `${VAR}` on `enabled` or `active`** — both are read raw before substitution and a non-empty placeholder string is truthy.
3. **An override carries only the keys it sets.** `deep_update` semantics: tables merge, scalars and lists replace. The merge runs before validation, which is what makes `active = "…"` alone a complete override of a document whose `active` field is required.
4. **One path sequence, one loader, every reader.** `ConfigLoader.backends_file_paths()` / `routing_profiles_file_paths()` build the sequence; `load_toml_from_base_and_overrides` reads it (base required, overrides optional); the backend library, the routing loader, `ModelManager.setup`, `is_pipelex_gateway_enabled`, `pipelex show backends` and the doctor's three probes all go through them. No caller builds `config_dir / "inference" / "backends.toml"` by hand any more.
5. **Writers keep writing the base.** The init flow's backend and routing editors read and write the base file only: their checkboxes must pre-fill from the file they will write, or a personal override would leak into the tracked file on save. `check_is_initialized` checks the base for the same reason. The one init reader that mirrors the boot, the cache-priming gate, reads the merged document.
6. **Skip lists get the two bare names.** `GIT_IGNORED_CONFIG_FILES` is matched by basename at every depth by the kit mirror, `check-config-sync`, `pipelex init` and the global bootstrap copy, so two names there cover all four.
7. **Gitignore in both places.** The repo's root `.gitignore` names the two files bare, like `pipelex_override.toml`. The `.pipelex/.gitignore` writer gains one line per personal override file — the two new ones and the three existing ones it never listed — so a fresh `pipelex init` project is safe by default; its create-if-absent contract is untouched, so projects set up earlier add the names to their own root `.gitignore` (filed for the cookbook and `pipelex-server`'s `worker`).
8. **The migration ledger is untouched.** The registry never enters `.pipelex/inference/` itself, only `inference/backends/`, so the overrides are outside every surface like their base files. One comment in `surfaces.py` says so.
9. **Two dead boot catches fixed on the way.** `RuntimeBoot` caught `RoutingProfileLibraryNotFoundError` and `RoutingProfileDisabledBackendError`, which the routing loader never raised (it raised `ModelManagerError` and `RoutingProfileLibraryError`), so the half-written override — `active` flipped, the backend still off — surfaced as a raw `CogtError`. The loader now raises the classes the boot names, keeps `RoutingProfileLibraryError` for an invalid document or an unknown `active`, and the boot gained a clause for that one too.
10. **`InferenceBackendLibrary.check_backend_credentials` deleted**, with `CredentialsValidationReport`: zero callers, and a raw reader of the base file that would have ignored the overrides.

## Steps

1. Constants, `_inference_file_paths`, `backends_file_paths` / `routing_profiles_file_paths` on `ConfigLoader`; `load_toml_from_base_and_overrides` and `describe_toml_base_and_overrides` in `toml_utils`.
2. Loaders and callers: `backend_library.py`, `routing_profile_loader.py`, `model_manager.py`, `pipelex_service_config.py`, `init/command.py`, `doctor_cmd.py`, `show_cmd.py`, `runtime_boot.py`.
3. `kit/paths.py`, root `.gitignore`, `.worktreeinclude`, `migration/gitignore.py`, `surfaces.py` comment, `config_check.py` comment, `init/backends.py` docstring.
4. Tests: the helper, the path sequence, both loaders' override modules, the gate, the doctor probes, the sync exclusion, the written `.gitignore`, the boot clauses through an injected models manager, and an end-to-end module against the global `config_manager` with the kit tree in a faked home.
5. Docs: `inference-backend-config.md` (tree, "Personal overrides", "Custom deck files", loading process), `features/configuration.md`, `contribute/configuration-defaults-and-overrides.md`, `under-the-hood/init-cli-flows.md`, `migration-ledger.md`, `configuration/index.md`, `tools/cli/show.md`; the two drift acks.
6. Changelog under `[Unreleased]`: Added, Changed (breaking loader signatures and exception classes), Removed.
7. `make agent-check`, the targeted suites, `make agent-test`; a manual run in a scratch `HOME` and a project-tier override in this worktree with `git status` and `make check-config-sync` clean.
8. PR against `dev`, `Closes L-260903-9fe4ad`; `/ledger-land` after the merge.

## Out of scope

- `backends_dir_path` and `deck_dir_path` stay single-directory `str` parameters; the per-backend files and the deck have their own mechanisms (the ledger, the manifest) and no override layer.
- The CLI's hint texts still send a user to `.pipelex/inference/backends.toml` to enable or disable a backend. That is still the right file for most users; an override-aware hint is a wording change for later.
- A `pipelex_service.toml` line in the written `.pipelex/.gitignore`: it is not an override and this repo ignores it by path.

## Revisions

- 2026-09-03, while implementing: decision 9 was planned as a fix "on the way" and turned out to need a third clause, because an `active` naming no profile — the likeliest typo in an override — was still `ModelManagerError`, which no clause named. The loader keeps `RoutingProfileLibraryError` for that case and the boot catches it through the same validation-message builder the other libraries use.

## Checkpoint — 2026-09-03, paused before the full suite's verdict

Everything in the Steps list through step 7's targeted runs is in the tree on `feature/Inference-config-overrides` (worktree `_pipelex--inference-config-overrides`), and the ledger item is claimed and references this plan.

What is verified:

- `make agent-check` is green end to end, including both drift acks (`config-docs`, `cli-docs`, staged under `.drift/acks/`).
- The targeted suites (`tests/unit/pipelex/{system,cogt,cli,migration,tools,kit}/`, the two boot modules, `tests/integration/pipelex/cli/commands/init/`, `tests/integration/pipelex/system/`) pass — thousands of tests, one skip that predates this work.
- By hand, in a scratch `HOME` over this repository's tracked base: the two global overrides put `pipelex show backends` on `all_anthropic` with the gateway gone, `pipelex doctor` reports the merged view, deleting the two files restores `all_pipelex_gateway`. A project-tier `routing_profiles_override.toml` in this worktree is invisible to `git status`, passes `make check-config-sync`, activates `all_mistral`, and its removal restores the default.
- The ledger follow-ups for the sibling projects' `.gitignore` are filed: `L-260903-6b77c1` (cookbook) and `L-260903-36002a` (`pipelex-server`, member `worker`).

What is not: `make agent-test` was started and had not finished when the session paused, so the full suite has no recorded verdict yet.

Next session, in order:

1. `ledger claim L-260903-9fe4ad --renew`, then `make agent-test`. `tests/CLAUDE.md` mandates the full suite for a change under `pipelex/system/configuration/`; expect the only pre-existing skip in `tests/unit/pipelex/tools/misc/test_toml_utils.py`.
2. If red, the likeliest culprits are callers of the renamed loader parameters that the targeted runs did not import (grep `backends_library_path=` and `routing_profile_library_path=` across `tests/` — the singular spellings — and `is_pipelex_gateway_enabled(backends_file_path=`).
3. `make agent-check` once more (the formatter is idempotent now), then commit and open the PR against `dev` with `Closes L-260903-9fe4ad` in the body; `/ledger-land` after the merge.
