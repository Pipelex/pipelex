# Python version floor — keep `pipelex` on 3.10 while Mistral Workflows stays 3.12-only

Self-contained plan. Goal: restore `pipelex`'s published Python floor to `>=3.10` while keeping the optional Mistral Workflows orchestration integration (which needs `>=3.12`) available to the users who can run it. Siblings `mistral-workflows-plugin-extract.md` (extracting the integration into the standalone `pipelex-mistralai-workflows` distribution) and `mistral-workflows-sub-module.md` (the in-tree build history that produced `bridge.py` and the execution modes) are the inputs to this; this doc only addresses the packaging/version-floor policy.

## Problem

`pipelex` is meant to install on Python `>=3.10`. The Mistral Workflows integration depends, transitively, on `mistralai-workflows`, which requires `>=3.12`. On `feature/Mistral-workflows-merge-3`, commit `91f3eae5` ("Fix mistral wf skill") raised pipelex's own `requires-python` from `>=3.10,<3.15` to `>=3.12,<3.15` (and the matching line in `uv.lock`).

That bump is heavier than the problem requires and is internally inconsistent — three other signals all still say 3.10 is fine:

- `pyproject.toml` classifiers still advertise `Programming Language :: Python :: 3.10` and `3.11`.
- The CI matrices in `lint-check.yml` and `manual-trigger-tests-check.yml` still run Tests **and** Typecheck on `3.10`–`3.14`, and they pass.
- pipelex's own test suite passes on 3.10/3.11, i.e. the code genuinely runs there.

So `requires-python` is the only place asserting 3.12, and it asserts it for a dependency pipelex does not actually have.

## Why the architecture already solves this

The dependency boundary is already in the right place — only the metadata is wrong:

- pipelex core declares **no** dependency on `mistralai-workflows` or `pipelex-mistralai-workflows`. Verified: neither appears in `pyproject.toml`, `uv.lock`, the `Makefile`, or `.github/`.
- The only `mistralai` reference is the optional `mistralai` extra = the base SDK (`mistralai>=2.4.4`, itself `>=3.10`), used by the Mistral *LLM* plugin under `pipelex/plugins/mistral/`. That code imports `mistralai.client` and is additionally `importlib.util.find_spec`-gated in `mistral_list.py`. Fully 3.10-safe.
- `MISTRAL_NATIVE` execution is **runtime-gated, not import-gated**. `runtime_bridge/bridge.py::_run_mistral_native` does a lazy `from pipelex_mistralai_workflows.primitives.pipe_run import ...` *inside the function* and, on `ImportError`, raises `MissingMistralWorkflowsPluginError` with a `pip install pipelex-mistralai-workflows` hint. There is no module-level import of the 3.12 package anywhere in core.
- The Mistral Workflows code is being extracted into the standalone `pipelex-mistralai-workflows` distribution (`mistral-workflows-plugin-extract.md`), which is the package that owns the `mistralai-workflows` (3.12+) pin.

In other words: pipelex core is framework-agnostic and 3.10-compatible; the 3.12 requirement lives entirely in a separate package that depends on pipelex, never the other way round.

## Decision

Keep pipelex's published floor at **`>=3.10,<3.15`**. Ship the Mistral Workflows integration as the **separate** `pipelex-mistralai-workflows` package (its own `requires-python >= 3.12`), installed on its own. pipelex never declares it as a dependency or an extra.

User experience:

- A user on 3.10/3.11 gets all of pipelex, including the Mistral *LLM* features (`pipelex[mistralai]`), just not the Workflows *orchestration* path.
- A user on 3.12+ who wants orchestration runs `pip install pipelex-mistralai-workflows`, which pulls pipelex in automatically. The runtime error in `bridge.py` already points them there if they forget.

### Alternative considered and rejected: a `pipelex[mistral-workflows]` extra

Declaring `mistral-workflows = ["pipelex-mistralai-workflows>=X ; python_version >= '3.12'"]` was considered for the nicer `pip install pipelex[mistral-workflows]` UX. Rejected because:

- On 3.10/3.11 the environment marker makes the extra resolve to **nothing** — `pip install pipelex[mistral-workflows]` would succeed and silently install no integration, which is a worse failure mode than a clear "requires 3.12" message.
- It introduces a back-edge (`pipelex` → `pipelex-mistralai-workflows` → `pipelex`). Resolvable, but needless coupling for a package whose whole point is to be an independent plugin.

Keeping the install standalone is simpler and the runtime gate already gives a good error.

## Plan

### 1. Revert the floor

- `pyproject.toml`: `requires-python = ">=3.10,<3.15"`.
- Regenerate the lock with `uv lock`; confirm `uv.lock`'s `requires-python` returns to `>=3.10`.
- Classifiers already list 3.10/3.11, so they become consistent again — no edit needed.

### 2. Confirm nothing actually required 3.12

The bump landed inside an otherwise docs-only commit, so the most likely root cause is a local `uv lock` during development that pulled `mistralai-workflows` (3.12) via an editable/ad-hoc install of the standalone package, after which the floor was raised to make the lock resolve. The committed dependency set contains no such package, so the floor is not needed. Verify:

- After `uv lock`: `requires-python` in `uv.lock` is `>=3.10`, and `mistralai-workflows` appears nowhere in the lock.
- `uv sync` succeeds against a 3.10 interpreter.
- The existing 3.10/3.11 CI lanes stay green (they already are).

### 3. Guardrails against regression

- Keep the lazy in-function import in `bridge.py`. Never add a module-level `import mistralai.workflows` or `import pipelex_mistralai_workflows` to pipelex core.
- Do not add `pipelex-mistralai-workflows` to pipelex's `pyproject.toml` — not as a runtime dep, not in the `dev` group, not as an extra. If an in-repo smoke test of the live MISTRAL_NATIVE path is ever wanted, install the package **ad-hoc in a dedicated 3.12-only CI lane** (not via pyproject) and `pytest.importorskip("pipelex_mistralai_workflows")` so it skips on every other lane.
- Add a focused regression test for the gate: requesting `MISTRAL_NATIVE` without the plugin importable raises `MissingMistralWorkflowsPluginError` with the install hint (simulate by patching the in-function import to raise `ImportError`). The "core imports cleanly without the optional packages" guarantee is already covered by the 3.10/3.11 CI lanes, which install neither. Natural home: `tests/unit/pipelex/runtime_bridge/`.
- Optional CI guard: a one-line check that `requires-python` in `pyproject.toml` starts at `>=3.10`, so a future accidental bump fails fast in review.

### 4. Document the install boundary

State it once, where users look: Mistral Workflows orchestration needs Python `>=3.12` and ships as the separate `pipelex-mistralai-workflows` package; pipelex itself supports `>=3.10`. The runtime error already says this — mirror it in the install docs and the Mistral Workflows guide.

## Verification

- `uv lock && uv sync` on a 3.10 venv → success; `mistralai-workflows` absent from the lock.
- `python3.10 -c "import pipelex"` → success with neither optional package installed.
- Requesting MISTRAL_NATIVE without the plugin → `MissingMistralWorkflowsPluginError` carrying the `pip install pipelex-mistralai-workflows` hint.
- CI: Tests + Typecheck remain green on 3.10–3.14.

## Out of scope / adjacent

- The `instructor` fork pin in `[tool.uv.sources]` (waiting on https://github.com/567-labs/instructor/pull/2298) is separate packaging hygiene; it does not affect the Python floor and is tracked via that PR. It must be reverted to a PyPI release before any tagged release, but it does not block this change or a `dev` merge.
- The `mistralai-workflows` version pin is owned by the standalone `pipelex-mistralai-workflows` package, not pipelex.

## Related

- `mistral-workflows-plugin-extract.md` — extracting the integration into the standalone `pipelex-mistralai-workflows` distribution; the enabler for this floor decoupling.
- `mistral-workflows-sub-module.md` — in-tree build history (Phases 1.x–2.1) that produced `bridge.py` and the execution modes.
