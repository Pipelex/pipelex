# PR #1052 review notes — deferred items

Triage record for the SWE-agent review threads on [PR #1052](https://github.com/Pipelex/pipelex/pull/1052) (release v0.39.2, carrying the sandbox-hosted PipeFunc transport feature). All threads were verified against the code; confirmed important issues were fixed on a follow-up branch to `dev`. This file captures the items deliberately deferred — each is real (or partially real) but is a design decision or defensive hardening that a PR-review pass should not resolve unilaterally.

## 1. Hosted mode still executes colocated structure-class modules (codex P1 + cubic dup)

- **Reporters:** codex (thread `PRRT_kwDOOwmMFc6Rw8qf`), cubic (thread `PRRT_kwDOOwmMFc6RxFP1`), `pipelex/libraries/library_manager.py` (hosted branch of `load_libraries`).
- **Verdict:** confirmed as a code fact. In sandbox-hosted mode, `ClassRegistryUtils.import_modules_in_folder` still AST-selects files containing a `StructuredContent` subclass and then `exec_module`s the whole file, so module-top-level customer code in a file that colocates a structure class with a `@pipe_func` runs in the host process. The `@pipe_func` body itself never runs on the host (only defined, dispatched out-of-process).
- **Why deferred:** partially intentional — the code comment scopes the hosted invariant to "PipeFunc bodies, not the pydantic structure classes", because concepts declared `structure = "ClassName"` must resolve the real class at load/validate time on the host, and you cannot import a class without executing its module. Closing the residual leak is an isolation-boundary design decision, not a mechanical fix.
- **Recommendation:** decide whether to (a) document + lint a constraint "in hosted mode, structure classes must live in side-effect-free files, separate from `@pipe_func` and other executable code", or (b) build a hosted-safe class-extraction path. Option (a) is the pragmatic move; (b) is heavy machinery.

## 2. Hosted validate-time output-contract gap (cubic P1, remainder)

- **Reporter:** cubic (thread `PRRT_kwDOOwmMFc6RxFPK`), `pipelex/pipe_operators/func/pipe_func.py` (`validate_output_with_library` early return).
- **Verdict:** the P1 claim is largely a false positive — the full return-type/multiplicity cross-check DOES run in-box at library-load time (entrypoint boots in `direct` mode → `load_from_crate` → `validate_library` → `validate_output_with_library` with the real function registered), before the function executes. What remains: at hosted `/validate` (dry-run) time no box is spawned, so a return-type-vs-concept mismatch surfaces only at real execution instead of at pre-flight.
- **Why deferred:** closing the gap means invoking the sandbox during validation — a real design change for a diagnostics-freshness improvement, not a correctness hole.
- **Recommendation:** accept the weaker validate-time feedback as a documented hosted-mode limitation; revisit only if users hit confusing late failures.

## 3. Rehydration primitive: no scoping/teardown on the transported path (cubic ×2)

- **Reporter:** cubic (threads `PRRT_kwDOOwmMFc6RxFPS`, `PRRT_kwDOOwmMFc6RxFPW`), `pipelex/runtime_bridge/primitives/rehydration.py`.
- **Verdict:** confirmed-but-inert. A setup failure leaves the fresh library registered and the current-library ContextVar pointing at it, and the binding is never restored after the run. In the only shipped caller (the one-shot subprocess entrypoint) the process exits right after, and `open_fresh_library` pops-and-tears-down any stale same-id library on the next call, so nothing observable leaks today. The primitive itself must NOT scope-and-restore internally — the caller needs the binding live through `run_pipe_func` and output wrapping.
- **Recommendation if addressed:** in `DirectPipeFuncExecutor.run_pipe_func_transported`, wrap from rehydration through output-wrapping in `scoped_current_library(library_id=_TRANSPORTED_LIBRARY_ID)` plus a `finally` teardown of the library — matching the established pattern in `pipeline_run_setup.py` — so the documented "out-of-tree backends may reuse this" contract becomes safe for long-lived processes.

## 4. `JobMetadata` does not forbid extra fields on the wire (cubic)

- **Reporter:** cubic (thread `PRRT_kwDOOwmMFc6RxFPu`), `pipelex/pipe_operators/func/pipe_func_execution_dtos.py` nesting `pipelex/pipeline/job_metadata.py`.
- **Verdict:** partially confirmed. The request model forbids extras and `PipeRunParams` already forbids extras, but `JobMetadata` is a plain `BaseModel`, so a typoed key inside the `job_metadata` sub-object of a transported request validates silently.
- **Why deferred:** `JobMetadata` is a shared model threaded through the whole runtime (Temporal payloads, tracing, inference jobs). Bolting `extra="forbid"` onto it is a global contract change with wide blast radius, to be taken (and tested) deliberately — not as a transport-DTO tweak.
- **Recommendation:** decide once for all wire-facing shared models; if forbidding, do it in its own change with the full suite run.

## 5. Transport rebind path escapes raw hydration errors (cubic)

- **Reporter:** cubic (thread `PRRT_kwDOOwmMFc6RxFPj`), `pipelex/pipe_operators/func/pipe_func_execution_transport.py` (`pipe_func_execution_result_from_response`).
- **Verdict:** confirmed, minor. `hydrate_working_memory` + `get_main_stuff` on the sandbox response can raise hydration/working-memory errors, while `PipeFuncTransportError`'s docstring claims to cover "rebound from out-of-process execution". Asymmetric with the executor side, which classifies its failures.
- **Why deferred:** the response is produced by our own sandbox code, so a rebind failure is an internal contract bug; the one customer-triggered case (.py-only output class) is already documented as a known deferred limitation. Value is classification consistency, not recovery.
- **Recommendation if addressed:** wrap the two calls, `raise PipeFuncTransportError(...) from exc`, naming the function module/qualname.

## 6. `sys.path` insertion can cross-contaminate same-named bare helpers (cubic)

- **Reporter:** cubic (thread `PRRT_kwDOOwmMFc6RxFPO`), `pipelex/tools/typing/module_inspector.py` (`import_module_from_file`).
- **Verdict:** confirmed mechanism, narrow reach. The insert exists so customer bundle files can import sibling helpers (added with #1036). Two distinct library dirs each shipping a top-level module with the same bare name (`helpers.py`), both imported bare in one long-lived process, would have the second library execute against the first's helper — the poisoning vector is the persistent bare-name `sys.modules` entry, so a "scoped `sys.path` restore" would NOT fix it. The deployed isolated runner path (one-shot box per call) is unaffected.
- **Why deferred:** the correct fix is namespacing bundle imports (or isolating `sys.modules` per bundle), which is real design work; the bots' suggested revert doesn't close the hole.
- **Recommendation:** track as a known local-multi-library footgun; revisit alongside any bundle-import namespacing work.

## 7. `normalize_crate()` drops `python_sources` (cubic)

- **Reporter:** cubic (thread `PRRT_kwDOOwmMFc6RxFPD`), `pipelex/libraries/crate_normalization.py` / `library_crate.py`.
- **Verdict:** confirmed as a code fact, but the "breaks the transport contract" claim is a false positive: no transport path goes through `normalize_crate` — the sandbox/Temporal request is built from `get_crate()` directly, which threads `python_sources`. Normalization feeds the codegen/resolve/build projection pipeline, which has no need for customer `.py` text.
- **Why deferred:** latent inconsistency only; copying sources into the normalized crate would also raise the question of whether they belong in the normalized fingerprint (they deliberately do not today).
- **Recommendation if a normalized crate is ever transported:** pass `python_sources=crate.python_sources` through `normalize_crate` and state explicitly that sources stay outside the normalized fingerprint.

## 8. Crate cache published before the fingerprint idempotency check (cubic)

- **Reporter:** cubic (thread `PRRT_kwDOOwmMFc6RxFP2`), `pipelex/libraries/library_manager.py` (`load_from_crate`).
- **Verdict:** confirmed ordering fact, no exercised bug. A same-fingerprint crate with different/absent sources would overwrite `_crate_cache` and early-return, so `get_crate()` exposes the replacement. No current path produces two same-fingerprint crates with differing sources for one library id (fingerprint excludes sources by design; transported crates for a given structure always carry the same sources).
- **Why deferred:** defensive tightening against a scenario the architecture doesn't generate.
- **Recommendation if addressed:** don't overwrite an existing cache entry on a fingerprint hit, and publish the incoming crate only after `validate_library()` succeeds (next to the `loaded_set.add(fingerprint)`), with a two-load test asserting the first crate's sources survive.
