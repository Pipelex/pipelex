# PR #1093 review notes — deferred items

Triage record for the SWE-agent review of [PR #1093](https://github.com/Pipelex/pipelex/pull/1093), the `release/v0.43.0` → `main` promotion.

Three bots were invoked; two declined outright — Greptile on size (277 files against a 200-file limit) and cubic on quota (its check run reports `NEUTRAL`). Only **Codex** produced findings: **two P1s**, both against `1/2 Flat topology — core seam: batch-branch router hook + frozen fan-out bound` (#1088). Codex posted them in the review body rather than as inline threads, so there are no review threads to resolve.

Both were verified against the code. **Neither is a live bug** — one is a false positive outright, the other is a false positive as reported but sits on top of a real latent-invariant weakness, captured below as the one **deferred** item.

## Deferred — `batch_max_concurrency` should be required, not defaulted

- **Origin:** surfaced while verifying Codex's second P1 on `pipelex/pipe_run/pipe_run_params.py:160`. It is *not* the defect Codex described (see "Not deferred" below for why that one is a false positive) — it is the weakness underneath it.
- **Where:** `pipelex/pipe_run/pipe_run_params.py`, the `batch_max_concurrency: int | None = Field(default=None, frozen=True)` field.

### The defect

`None` is not only the field's default — it is also the resolved value of an authored `max_concurrency = "unbounded"`. The config types it `Annotated[int, Field(ge=1)] | Literal["unbounded"]` (`pipelex/system/configuration/configs.py:151`), and `resolve_batch_max_concurrency` maps the literal to `None` (`pipelex/pipe_run/pipe_run_params_factory.py:22`). So **"unset" and "authored unbounded" are indistinguishable**, and the default points at the dangerous direction: a value that never got written means *launch every branch at once*.

That contradicts the discipline the file states two fields above, on `run_mode`:

> REQUIRED (no default): a payload missing the run mode must fail loud instead of silently running LIVE (the spending direction) or DRY (the mock direction).

`pipe_stack_limit` is required for the same reason. `batch_max_concurrency` is the odd one out.

### The trap has already been sprung

`PipeRunParamsFactory.make_run_params` always writes the field (`pipe_run_params_factory.py:57-66`), and it is the only construction site in shipped code — which is why this is a latent weakness and not a live bug. But the tree already has direct constructions that bypass it, and one of them is exactly where it hurts:

`tests/integration/pipelex/pipes/controller/pipe_batch/test_pipe_batch_compaction.py:44`

```python
return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)
```

A **PipeBatch** test fanning out unbounded, silently not exercising the configured bound. The tell is right there in the same expression: the fixture bothers to read `pipe_stack_limit` from config *because that field is required*, and drops the one that isn't. The same shape recurs across roughly nineteen direct constructions — `pipe_parallel/test_pipe_parallel_absence.py:72`, `pipe_condition/test_pipe_condition_continue_delivery.py:60`, the four `tests/integration/pipelex/pipes/optionals/*` fixtures, `tests/integration/pipelex/pipeline/test_optional_method_inputs.py:153`.

An invariant held by convention rather than by the type, already broken in the two places that matter most (a batch test and — see below — the wire test), is enough to tighten.

### Recommended fix — delete one word

```python
batch_max_concurrency: int | None = Field(frozen=True)
```

Keeps `int | None`, so authored `"unbounded"` still resolves to `None`; keeps `frozen=True`; keeps the factory as single writer; turns any omission — constructor or payload — into a loud `ValidationError`. Carry the `run_mode` rationale into the field comment so the three invariant-bearing fields read as one convention.

**Reject the sentinel** that Codex proposed: a third state in a two-state domain, existing only to serve a migration story the workspace policy rules out.

### Why it was deferred rather than done here

The source change is one word, but the fixtures are not: ~19 direct constructions in this repo plus one in `pipelex-server` must supply the field. The integration fixtures should route through `PipeRunParamsFactory.make_run_params` instead — a net simplification, since they already hand-duplicate the factory's config read — but that is a ~20-file change with a cross-repo tail, landing on a release branch whose CI is green and which is about to merge to `main`. It belongs on `dev` immediately after the promotion.

### Execution notes for the follow-up

- **Tests:** add `pytest.raises(ValidationError)` coverage for both the constructor and `model_validate({...})` with the key absent, mirroring the required-`run_mode` coverage already in `tests/unit/pipelex/pipe_run/test_cogt_run_params_carrier.py:72-92`.
- **Mutation-check it.** Temporarily restore `default=None` and confirm the new test goes red. A test green on first run proves nothing here.
- **Fix the compaction fixture** to build via the factory and assert the observed bound — that is the one place where an accidentally-unbounded fan-out actually changes behavior.
- **Cross-repo, gated on the `pipelex` pin moving:** `pipelex-server/temporal/tests/integration/pipelex_temporal/data_converter/test_data_conv_pipe_run_params.py:22` round-trips `None`, so it asserts `None == None` and would not catch the field being dropped on the wire. Make it round-trip a real int bound.
- **Honest caveat to keep in view:** making the field required converts a legacy-history decode into a `ValidationError`, and a workflow-task converter exception retries forever — it hangs rather than fails. Both states are non-events while Temporal is pre-production, and neither is fixed by a field default. It reconfirms that deploy discipline, not this field, is the real control over version skew under live histories.

## Not deferred — the two P1s as Codex reported them

Recorded so both findings stay traceable. Neither produced a code change.

### 1. `run_batch_branch` on a structurally-conforming router — false positive

Codex argued that `Pipelex.make` given a router that satisfies `PipeRouterProtocol` structurally without inheriting from it would `AttributeError` at `pipelex/pipe_controllers/batch/pipe_batch.py:164`, because Python does not install a protocol's default method bodies on structural implementers.

The language claim is correct. Everything downstream of it is not:

- **No such router exists.** Every implementer in the workspace inherits nominally — `PipeRouter` (`pipelex/pipe_run/pipe_router.py`), `TemporalPipeRouter` in `pipelex-server/temporal/`, `MistralWorkflowsPipeRouter`, and every test stub. `pipelex-api` and `pipelex-server/transport/` contain no router at all.
- **The failure mode is static, not runtime.** The protocol is not `@runtime_checkable`, and injection performs no isinstance check — but pyright rejects a structural non-conformer at the injection boundary with `"run_batch_branch" is not present (reportArgumentType)`. Every consumer in this workspace is type-checked.
- **Structural conformance was never viable here.** `PipeRouterProtocol` declares an attribute, three concrete observer hooks, a concrete template-method `run`, and an `@abstractmethod _run_pipe_job`. Conforming without inheriting would mean reimplementing `run`'s entire error-wrapping template. Inheritance is not one supported pattern — it is the only one.
- **The cited convention says the opposite.** Codex referenced `AGENTS.md:255-258`; that section actually reads *"When extending the `Protocol`, also update every implementation (including no-op / null implementations) so structural typing is satisfied"* — a rule pointing away from the claim it was cited for.

**The proposed fallback was rejected on the merits, not just as unnecessary.** A `getattr(router, "run_batch_branch", router.run)` at the dispatch site would defeat the pyright check that currently catches this, and would make the batch-branch signal silently unreliable: a distributed router whose override is renamed or misspelled would fall back to `run` and lose per-branch isolation — precisely the failure the hook exists to prevent. That trades a loud, checked, one-line-to-fix `AttributeError` for a silent behavioral downgrade in the distributed path.

No test was added either. A test injecting a non-inheriting router would assert that Python raises on a missing attribute — a test of the language — and would enshrine an extension pattern the codebase deliberately does not support. The existing coverage is the right coverage: `tests/unit/pipelex/pipe_run/test_run_batch_branch_hook.py` pins that the default delegates to `run` rather than to `_run_pipe_job`, so observers still see every branch, and `tests/integration/pipelex/pipes/controller/pipe_batch/test_pipe_batch_branch_dispatch.py` pins one hook call per item.

**What did change:** two clauses of documentation precision, because a competent reviewer misread the extension contract and that is evidence the text was ambiguous. `CHANGELOG.md` now names the mechanism behind "every existing router keeps working untouched" (they subclass, so they inherit it), and `docs/advanced/index.md` § "Protocol Compliance" now leads with subclassing — it was the one sentence a reader could take as blessing structural-only implementation.

### 2. Legacy payloads losing the fan-out bound — false positive

Codex argued that a worker resuming a `PipeRunParams` serialized before `batch_max_concurrency` existed would decode it as `None`, read as unbounded, changing both concurrency and replay grouping mid-flight.

The mechanism is real: `PipeRunParams` does ride a Temporal workflow argument (`pipelex-server/temporal/pipelex_temporal/tprl_pipe/wf_pipe_router.py:204`), workflow arguments are recorded in history and re-decoded on replay, and `gather_bounded`'s chunk size does determine command grouping — which `pipelex-server/temporal/docs/temporal-replay-determinism.md` places on the replay-unsafe side of its own table.

The scenario is not:

- **The Temporal integration is not in this package.** `pipelex/temporal/**` was removed in *Refactor/plugins 5* (#1006) and lives in the private `pipelex-server/temporal/` plugin; `pyproject.toml` carries no `temporalio` dependency. No OSS consumer of `pipelex` can have an in-flight durable batch.
- **The only exposed party is our own hosted plane, which is pre-production.** Temporal has never shipped to prod.
- **A field default cannot fix the general case.** Bumping `pipelex` on a Temporal worker is a workflow-code change, and this same release lands the kernel extraction and the plugin entry-point-group split. There is no `workflow.patched` or worker-versioning machinery. Hot-swapping any pipelex version under live histories is unsafe with or without this field; the control is deploy discipline (drain, build IDs).
- **The remedy is what the workspace rules out.** "No backward compatibility… no deprecation transition period." A legacy-payload sentinel is exactly the speculative back-compat machinery that policy exists to prevent, and the change is already recorded as breaking in the changelog.
