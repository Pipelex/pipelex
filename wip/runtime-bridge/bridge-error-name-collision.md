# Bridge error name collision — `PipelexRuntimeBridgeError` vs `PipelexBridgeRuntimeError`

**Status:** ✅ **RESOLVED — leaf renamed to `PipelexBridgeDispatchError`.** (Option A.) Applied: renamed the class in `exceptions.py`; updated the import + raise sites in `bridge.py` and the `pytest.raises` references in `test_validation.py`; regenerated `docs/errors/` (`pipelex-bridge-runtime-error.md` removed, `pipelex-bridge-dispatch-error.md` written, `index.md` updated — no spurious mistral-page churn); updated the `TODOS.md` prose. `make agent-check` + `make agent-test` green. Original triage retained below.

**Spotted:** during the `dev` → `feature/Runtime-bridge-extraction` merge triage. Not a merge regression and not a stale duplicate — verified both classes are live and their docs are in sync (`pipelex-dev generate-error-pages` reports `Removed: 0`, no orphans).

## The smell

`pipelex/runtime_bridge/exceptions.py` declares two classes whose names differ **only by word order**:

```python
class PipelexRuntimeBridgeError(PipelexError):           # :4  — base for the whole runtime-bridge surface
class PipelexBridgeRuntimeError(PipelexRuntimeBridgeError):  # :16 — concrete leaf: a bridge-dispatched pipe execution failed
```

"Runtime Bridge" vs "Bridge Runtime". They are genuinely distinct — the base also parents `MissingPipelexTemporalExtraError` and `MissingMistralWorkflowsPluginError` — but the near-mirror names are easy to misread, mistype, and mis-`except`. The leaf reads almost like its own base, which is exactly backwards. The two also generate two almost-identical doc-page slugs (`pipelex-runtime-bridge-error` / `pipelex-bridge-runtime-error`) that a reader can't tell apart at a glance.

This is a readability/API-clarity issue only: the kebab slugs are distinct (no `type_uri` collision), and nothing is functionally wrong.

## The fork

- **(A) Rename the concrete leaf** to a self-evident name decoupled from the base's word-order — e.g. `BridgeDispatchError`, `BridgePipeExecutionError`, or `BridgeRunError`. The base `PipelexRuntimeBridgeError` (the namespace error) stays. This is the recommended direction: the leaf is the one at the call sites and the one whose meaning ("a pipe dispatched through the bridge blew up") should be obvious from its name.
- **(B) Rename the base** instead (e.g. `BridgeError` as the family root) and keep the leaf — less compelling, since the base is rarely referenced directly and the family-prefix convention (`Pipelex…`) is intentional.
- **(C) Leave it.** Zero churn; the confusion persists for every future reader and `except` site.

## Recommendation

Take **(A)**. Pick a leaf name that states what failed, not where it sits in the hierarchy. Per project policy there's no back-compat to preserve, so it's a clean rename.

## Blast radius (small, contained)

- `pipelex/runtime_bridge/exceptions.py` — the class definition.
- `pipelex/runtime_bridge/bridge.py` — one import + the `raise` sites.
- `tests/unit/pipelex/runtime_bridge/test_validation.py` — the `pytest.raises(...)` references.
- `docs/errors/pipelex-bridge-runtime-error.md` — regenerated, old slug page removed (it's `<!-- pipelex:generated -->`, safe to delete).
- `TODOS.md` mentions the name in prose — update if still relevant.

## How to apply

1. Rename the class in `exceptions.py`; update the import + raises in `bridge.py` and the references in `test_validation.py`.
2. `pipelex-dev generate-error-pages` to refresh `docs/errors/` (writes the new slug page, removes the old one) and the `docs/errors/index.md` entry. ⚠️ This worktree runs `mistralai==2.4.4`; the generator's import-walk has tolerated it so far, but eyeball the diff for spurious mistral-page churn.
3. `make agent-check` + `make agent-test`.
