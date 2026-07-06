# PR #1026 (Release v0.38.0) — deferred / declined review items

Cubic left 7 unresolved threads on the v0.38.0 release PR. Five were fixed in the PR (PipeCompose sigil double-rewrite, two caller-facing exception markers, `--inputs ~` expansion, non-string pipe-type guard). The two below were **not** changed — one deferred for a deliberate follow-up, one declined as a false positive. This file records the reasoning so neither gets re-litigated from scratch.

## Deferred — `validate_all` (builder) drops the `warnings` payload

- **Reporter:** cubic-dev-ai (confidence 9, P2)
- **Location:** `pipelex/builder/operations/validate_ops.py` — `validate_all` (the function around L24–53)
- **Thread:** left **open** on PR #1026 for follow-up.

### The finding (confirmed, but not a bug)

Builder `validate_all` returns `{success, is_valid, validated_pipes, total_pipes}` with **no `warnings` key**. Its three siblings in the same file (`validate_bundle_file`, `validate_bundle_content`, `validate_pipe_in_bundle`) all carry `warnings` via `build_optionality_warnings(collect_controller_taint_analyses(result.pipes))`, and the agent-CLI twin `validate_all_core` (`pipelex/cli/agent_cli/commands/validate/_validate_core.py`) already emits them. So the whole-library advisory lints (e.g. useless-`!` detection) are dropped **only** on the builder `validate_all` path.

### Why it was deferred rather than fixed on the release branch

- It is **not a correctness bug**: `is_valid` stays correct and warnings never flip the verdict.
- The change is **purely additive** (these functions return `dict[str, Any]`; `warnings` is just a key) — no contract/type change.
- The builder `validate_ops` dict surface has **no in-repo consumers** (only `validate_pipe` is imported, by one lifecycle test); it is a downstream-facing API for `pipelex-api` / the build assistant, and the same-shape agent-CLI `validate_all` already supplies warnings.
- `validate_all` carries an **explicit minimal-envelope design comment** (it deliberately omits `pending_signatures`/`is_runnable`). That rationale is about `pending_signatures`, not `warnings`, but it signals the envelope shape is a deliberate design decision the author should make — not something to fold silently into a release-branch fix pass.

### Fix recipe (when picked up)

Mirror `validate_all_core`'s inlined lifecycle instead of the `acquire_and_validate` shortcut (which tears the library down in its `finally` before returning, so warnings can't be computed post-hoc):

1. capture `prev_library_id`, `acquire_library(...)`;
2. in a `try`, call `BundleValidator().validate_current_library()`;
3. compute `warnings = build_optionality_warnings(collect_controller_taint_analyses(list(get_pipe_library().get_pipes_dict().values())))` **before** teardown;
4. restore prev library + teardown in `finally`.

The needed imports (`collect_controller_taint_analyses`, `build_optionality_warnings`) are already present at the top of `validate_ops.py`. **Decision for the author:** add `warnings` only (minimal), or fully align the envelope with the agent-CLI twin (also add `pending_signatures`/`is_runnable`) and update the minimal-envelope design comment accordingly. Recommend at least `warnings`.

**Test:** add an integration test under `tests/integration/pipelex/builder/operations/` that loads a library with a redundant-`!` flow (reuse the pattern in `tests/integration/pipelex/pipes/optionals/test_redundant_force_warning.py`), calls `validate_all(...)`, and asserts the returned dict's `warnings` contains the `optional_force_redundant` item — the analogue of the agent-CLI's existing validate-all warnings coverage.

## Declined (false positive) — `NodeSpec.skip_reason` validator

- **Reporter:** cubic-dev-ai (confidence 6, P3)
- **Location:** `pipelex/graph/graphspec.py` — `NodeSpec.skip_reason` field (around L256–260)
- **Thread:** replied + **resolved** (no code change).

Cubic proposed a `NodeSpec` model_validator enforcing `skip_reason` only when `status == NodeStatus.SKIPPED`. Declined because the invariant `skip_reason set ⟺ status == SKIPPED` is already **maintained by construction**:

- `NodeSpec` is built in exactly two internal builders (`graph_tracer.py` `_NodeData.to_node_spec`, `graphspec_assembler.py`), both of which copy `skip_reason` verbatim from a `_NodeData` builder whose `skip_reason` is initialized to `None` and only ever set in the same breath as `status = NodeStatus.SKIPPED` (`graph_tracer.py:901-902`, `graphspec_assembler.py:299-300`). No transition sets `skip_reason` on a non-skipped node.
- **No consumer reads the field on a non-skipped node** — no reactflow/mermaidflow renderer touches `skip_reason`; the one place that maps skip reasons already filters on `status == NodeStatus.SKIPPED`.
- `validate_graphspec` (the graph-level invariant home, where the analogous `_validate_failed_nodes_have_errors` lives) is **not wired into any production path** — even the on-disk `GraphSpec.model_validate_json` load in `graph_cmd.py` does not call it. So a model_validator would guard an internally-produced, already-consistent value — exactly the "don't guard impossible cases" case.

If symmetry with `_validate_failed_nodes_have_errors` is ever wanted purely for tidiness, the correct home is a `_validate_skipped_nodes_have_reasons` helper in `pipelex/graph/validation.py` (the presence direction only: `skip_reason` non-None ⇒ `SKIPPED`), **not** a pydantic `model_validator` on `NodeSpec`. Even that is optional cleanup, not a correctness fix.
