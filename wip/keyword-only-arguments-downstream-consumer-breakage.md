# Downstream consumer breakage — keyword-only refactor follow-up

> **Status (2026-06-15):** lockstep PRs opened against each consumer's `dev`, each pinning `pipelex` to the keyword-only branch git rev (`529b9082`, branch `refactor/Function-calling-4`) and carrying the call-site fixes. All four pass local `make agent-check` + `make agent-test`:
>
> - **pipelex-api** → [PR #19](https://github.com/Pipelex/pipelex-api/pull/19) — keyword-only delta only (it already tracked pipelex `dev`): one `parse_pipe_spec(pipe_type, spec_data=...)` fix.
> - **pipelex-starter-python** → [PR #55](https://github.com/Pipelex/pipelex-starter-python/pull/55)
> - **cocode** → [PR #75](https://github.com/Pipelex/cocode/pull/75)
> - **pipelex-cookbook** → [PR #153](https://github.com/Pipelex/pipelex-cookbook/pull/153)
>
> **Key finding:** cookbook/cocode/starter-python were pinned to **PyPI `pipelex` 0.32.x**, so pinning them to the branch (which tracks pipelex `dev`) surfaced the **whole accumulated dev delta**, dominated by a *non*-keyword-only change — the **`PipelexRunner` → `PipelexMTHDSProtocol`** runner rename (MTHDS Protocol surface alignment: `execute_pipeline()` → `execute()`, `response.pipe_output` unchanged). Those three PRs therefore carry that runtime-runner migration **in addition to** the keyword-only fixes. Keyword-only-specific fixes were tiny: cookbook's `save_text_to_path` + its `get_stuff_as`/`get_stuff_as_list` (`content_type=`/`item_type=`) calls; nothing extra in cocode/starter. The git-rev pins are **temporary** — swap each back to a released `pipelex` version once the refactor lands on PyPI.
>
> **Follow-up (2026-06-15b):** `parse_pipe_spec` arg order was **reversed** in pipelex — `parse_pipe_spec(pipe_type, *, spec_data)` → `parse_pipe_spec(spec_data, *, pipe_type)` — so the subject is now the thing being parsed (the data), matching its sibling `parse_concept_spec(spec_data)`. This re-breaks the **single** call site PR #19 had already fixed: `pipelex-api/api/routes/pipelex/agent/pipe_spec.py:48` must change from `parse_pipe_spec(request_data.pipe_type, spec_data=request_data.spec)` to `parse_pipe_spec(request_data.spec, pipe_type=request_data.pipe_type)`. **Sequence (don't desync the pin):** (1) commit the pipelex reversal → new SHA; (2) bump pipelex-api's `[tool.uv.sources]` rev from `529b908255…` to the new SHA on PR #19's branch `chore/keyword-only-pipelex-rev`; (3) apply the call-site fix; (4) `make agent-check` + `make agent-test` in pipelex-api. No other consumer calls `parse_pipe_spec`, so #55 / #75 / #153 are unaffected by the reversal (only a rev bump if we want them on the newest SHA).
>
> **Follow-up (2026-06-15c) — DONE (push pending):** pipelex HEAD `755b82117fd4c26ba090455cfd571099cf05708b` is pushed to `refactor/Function-calling-4`. That commit turned out **broader** than just the `parse_pipe_spec` reversal — it also flips the subject/keyword order of several other signatures (`save_bytes_to_binary_file`, `hydrate_content`, `load_template`, `load_config`, `build_deck`, `write_manifest`, `text_in_renaming_keys`/`text_in_renaming_values`, `_row_to_dict`, plus the `init` CLI helpers `customize_backends_config`/`setup_telemetry`/`display_selected_backends`/`prompt_primary_backend`). Re-audited every consumer for those names: **none** call them positionally (each site already passes by keyword), so `parse_pipe_spec` in pipelex-api stayed the *only* real call-site break. All four consumer PR branches (`chore/keyword-only-pipelex-rev`) had their pin bumped `529b9082…` → `755b8211…` in **both** `pyproject.toml` and `uv.lock`, re-synced, and verified green on `make agent-check` + `make agent-test`; pipelex-api additionally carries the `pipe_spec.py` call-site fix + CHANGELOG entry. Each branch has a fresh commit on top — **not yet pushed** (push was left to the user / blocked by auto-mode). When pushing, the open PRs #19 / #55 / #75 / #153 update in place.

> Original release-time checklist below (the pipelex-internal keyword-only refactor is **complete** — all waves landed, guard hard-blocks; see [`../TODOS.md`](../TODOS.md)). Companion to the convention itself at [`../docs/contribute/keyword-only-arguments.md`](../docs/contribute/keyword-only-arguments.md).

The keyword-only refactor intentionally turns multi-arg public helpers keyword-only (e.g. `save_text_to_path(text, *, path, create_directory=False)`, and on the public surface `Pipelex.make()` / `Pipelex.setup()` / `PipelexHub.setup_config()` — every argument after the first is now keyword-only). This is a deliberate breaking change, documented in the runtime `CHANGELOG.md`. Breaking changes are allowed in this workspace, but consumers must be updated in lockstep — otherwise the official examples ship broken.

## Confirmed breakage (Wave 1 — `tools/`)

- **`pipelex-cookbook/utils/results_utils.py:42`** — `save_text_to_path(content, result_file_path)` passes `path` positionally, but `path` is now keyword-only. Fix: `save_text_to_path(text=content, path=result_file_path)`. (The third param `create_directory` defaults to `False` and is unchanged.)

That is the only positional break found across the consumer repos for the Wave 1 public surface. The later waves (`core/` … the public `pipelex.py` / `hub.py` surface) have **not** yet been re-audited across the consumer repos — do that at release (recipe below).

## Repos audited and clean (Wave 1)

- **`cocode`** — already calls `save_text_to_path` in keyword form (`text=…, path=…`) at every site (`repox/repox_cmd.py`, `swe/swe_utils.py`, `swe/swe_cmd.py`). Its other pipelex-tools imports (`load_text_from_path`, `failable_load_text_from_path`, `ensure_path`, `path_exists`, `load_json_list_from_path`, `pascal_case_to_kebab`, `pascal_case_to_sentence`, `empty_list_factory_of`) are all single-arg or already keyword — no break.
- **`pipelex-starter-python`** — only uses `pretty_print` (single positional `content`), no break.
- **`pipelex-api`, `pipelex-worker`, `pipelex-mistralai-workflows`** — no positional calls to keyword-only Wave 1 helpers. (Re-check `Pipelex.make` / `setup` call sites — the public-surface change landed in Wave 5.)
- **`pretty_print` / `pretty_print_md` / `pretty_print_url`** (the only `pipelex/__init__.py` `__all__` exports) — now keyword-only on everything after `content`; no consumer passes `title` (or any later arg) positionally, so nothing breaks today. Worth keeping an eye on since these are the headline public API.

## Public surface converted in Wave 5 (re-audit before release)

The final wave made the top-level entry points keyword-only after their first parameter. A consumer passing a second-or-later argument positionally breaks:

- `Pipelex.make(integration_mode, *, ...)` — e.g. `Pipelex.make(IntegrationMode.PYTHON, False)` → `Pipelex.make(IntegrationMode.PYTHON, needs_inference=False)`.
- `Pipelex.setup(...)` and `PipelexHub.setup_config(config_cls, *, ...)` — same shape.

The common no-arg / all-keyword calls (`Pipelex.make()`, `Pipelex.make(needs_inference=False)`) are unaffected. Consumers to check: `pipelex-api`, `pipelex-worker`, `n8n-nodes-pipelex`, `pipelex-cookbook`, `pipelex-starter-python`, `pipelex-mistralai-workflows`.

## How to re-run the audit

From the workspace root (`/Users/lchoquel/repos/Pipelex`):

```bash
# 1. positional second-arg calls to the file/bytes writers
rg -n -g '*.py' -e 'save_text_to_path\(' -e 'save_bytes_to_path\(' \
  cocode pipelex-cookbook pipelex-starter-python pipelex-mistralai-workflows pipelex-api pipelex-worker \
  | grep -vE 'text=|path=|content='

# 2. pretty_print* called with a positional non-content arg
rg -n -g '*.py' 'pretty_print(_md|_url)?\([^)]*,[^=)]' \
  cocode pipelex-cookbook pipelex-starter-python | grep -vE 'title=|subtitle='

# 3. public bootstrap entry points with a positional second arg
rg -n -g '*.py' -e 'Pipelex\.make\(' -e 'Pipelex\.setup\(' -e 'setup_config\(' \
  cocode pipelex-cookbook pipelex-starter-python pipelex-mistralai-workflows pipelex-api pipelex-worker n8n-nodes-pipelex \
  | grep -E '\([^)]+,[^=)]'
```

Generalise the helper list per wave: take the functions a wave converted (the `### Changed` keyword-only entries in `CHANGELOG.md` name the packages and the headline signatures), keep only those imported by a consumer repo and exposing a second positional arg, then grep for positional call sites.

## Checklist

- [x] `pipelex-cookbook/utils/results_utils.py:42` → keyword form (PR #153, with its unit-test assertion updated to keyword form).
- [x] Re-run the audit greps for the full converted surface (Waves 1–5). Only positional keyword-only break found across consumers: cookbook's `save_text_to_path` + `get_stuff_as*`, and pipelex-api's `parse_pipe_spec`. All `Pipelex.make` call sites already pass the subject positionally + the rest by keyword (compliant).
- [x] Open lockstep PRs pinning each consumer to the branch git rev, all green on local `make agent-check` + `make agent-test` (PRs #19 / #55 / #75 / #153).
- [x] **`parse_pipe_spec` reversal (2026-06-15b) — pipelex-api lockstep:** done. pipelex reversal pushed (SHA `755b82117`); PR #19's pin bumped (pyproject + uv.lock), `pipe_spec.py:48` changed to `parse_pipe_spec(request_data.spec, pipe_type=request_data.pipe_type)`, CHANGELOG updated. `make agent-check` + `make agent-test` green. Committed on `chore/keyword-only-pipelex-rev`; push pending. The 2026-06-15c note widens this to all four consumers (the same SHA also reordered other signatures, none of which any consumer calls positionally).
- [ ] **At pipelex release:** swap each consumer's temporary `[tool.uv.sources]` git pin back to the released `pipelex` version (`==`/`>=`), and confirm CI stays green. Remember the release also ships the `PipelexRunner → PipelexMTHDSProtocol` rename — already handled in these PRs.
