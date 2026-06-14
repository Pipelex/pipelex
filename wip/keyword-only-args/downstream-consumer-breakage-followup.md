# Downstream consumer breakage — keyword-only refactor follow-up

The keyword-only refactor intentionally turns multi-arg public helpers keyword-only (e.g. `save_text_to_path(text, *, path, create_directory=False)`). This is a deliberate breaking change, documented in the runtime `CHANGELOG.md`. But sibling repos that consume `pipelex` from PyPI still call some of these helpers positionally, so they break at runtime (`TypeError`) the moment they upgrade to a version carrying this refactor. Breaking changes are allowed in this workspace, but consumers must be updated in lockstep — otherwise the official examples ship broken.

This doc tracks the consumer-side fixes. It is the companion to [`state.md`](state.md) (the refactor's running log) and [`convention.md`](convention.md) (the rule itself).

## Confirmed breakage (Wave 1 — `tools/`)

- **`pipelex-cookbook/utils/results_utils.py:42`** — `save_text_to_path(content, result_file_path)` passes `path` positionally, but `path` is now keyword-only. Fix: `save_text_to_path(text=content, path=result_file_path)`. (The third param `create_directory` defaults to `False` and is unchanged.)

That is the only positional break found across the consumer repos for the Wave 1 public surface.

## Repos audited and clean (Wave 1)

- **`cocode`** — already calls `save_text_to_path` in keyword form (`text=…, path=…`) at every site (`repox/repox_cmd.py`, `swe/swe_utils.py`, `swe/swe_cmd.py`). Its other pipelex-tools imports (`load_text_from_path`, `failable_load_text_from_path`, `ensure_path`, `path_exists`, `load_json_list_from_path`, `pascal_case_to_kebab`, `pascal_case_to_sentence`, `empty_list_factory_of`) are all single-arg or already keyword — no break.
- **`pipelex-starter-python`** — only uses `pretty_print` (single positional `content`), no break.
- **`pipelex-api`, `pipelex-worker`, `pipelex-mistralai-workflows`** — no positional calls to keyword-only Wave 1 helpers.
- **`pretty_print` / `pretty_print_md` / `pretty_print_url`** (the only `pipelex/__init__.py` `__all__` exports) — now keyword-only on everything after `content`; no consumer passes `title` (or any later arg) positionally, so nothing breaks today. Worth keeping an eye on since these are the headline public API.

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
```

Generalise the helper list per wave: take the functions a wave converts (see the package table in `state.md`), keep only those imported by a consumer repo and exposing a second positional arg, then grep for positional call sites.

## Future waves will widen the public surface

Wave 1 only touched leaf packages. Later waves convert domain code that consumers call far more often, so re-run the audit after each wave that touches a public surface. Known public-surface risks already spotted:

- **Wave 2 (`core/`)** — `WorkingMemory.get_typed_object_or_attribute` becomes keyword-only on `wanted_type`/`accept_list`; `StuffFactory`, `Concept`, and the `core/stuffs/*` content constructors are all on the user-facing path. The high-traffic getters (`WorkingMemory.get_stuff`, `get_stuff_as`, `get_stuff_as_str`) were deliberately left subject-positional — keep them that way so cookbook/cocode positional calls survive.
- **Waves 3–5 (`cogt/`, `cli/`, `system/`, `builder/`, `temporal/`)** — re-audit; these reach the runner API (`pipelex-api`) and the worker (`pipelex-worker`).

## Checklist

- [ ] `pipelex-cookbook/utils/results_utils.py:42` → keyword form, then run the cookbook example that exercises it.
- [ ] Re-run the audit grep above after each public-surface wave lands.
- [ ] When the refactor branch is released, confirm each consumer repo's pinned `pipelex` version and bump + fix in lockstep before they pick up the new release.
