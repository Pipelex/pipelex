# Downstream consumer breakage — keyword-only refactor follow-up

> **Status (2026-06-14):** the pipelex-internal keyword-only refactor is **complete** (all waves landed, guard hard-blocks — see [`../TODOS.md`](../TODOS.md)). What remains is this **cross-repo lockstep**: sibling repos that consume `pipelex` from PyPI and call the now-keyword-only public helpers positionally will break at runtime (`TypeError`) the moment they upgrade. This is the release-time checklist for that. Companion to the convention itself at [`../docs/contribute/keyword-only-arguments.md`](../docs/contribute/keyword-only-arguments.md).

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

- [ ] `pipelex-cookbook/utils/results_utils.py:42` → keyword form, then run the cookbook example that exercises it.
- [ ] Re-run the audit greps above for the full converted surface (Waves 1–5, incl. the public `Pipelex.make` / `setup` / `setup_config`).
- [ ] When the refactor branch is released, confirm each consumer repo's pinned `pipelex` version and bump + fix in lockstep before they pick up the new release.
