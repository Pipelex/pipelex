# PipeFunc registrations outlive the library that registered them

Deferred out of PR #1076 (`refactor/Exec`), raised as a P1 by the Codex reviewer and independently by the pre-landing review pass. **This is a genuine narrowing introduced by that PR, not a pre-existing quirk** — recorded here rather than fixed because the only correct fix is a design change, and it is worth deciding on its own terms.

## The scenario

A long-lived process that loads bundles sequentially:

1. `open_library()` → `load_libraries(library_id=A, library_dirs=[…])` — registers `summarize` from project A.
2. `LibraryManager.teardown(library_id=A)` — tears down A's pipe/concept/domain libraries and its own `ClassRegistry`.
3. `open_library()` → `load_libraries(library_id=B, …)` — project B also defines `summarize`, at a different path.

Step 3 now raises `FuncRegistryError`. A's registration is still in the registry: `LibraryManager.teardown` does not touch `func_registry`, and only `RuntimeBoot.teardown` clears it. So the "collision" is with a **stale** entry from a library nobody can reach any more, not with a concurrently-live one.

Before #1076 the same sequence silently overwrote, and B won — which for the sequential case was the right outcome. So this path regressed from *works* to *fails until the process restarts*.

## Who this hits

**No first-party host can reach this today** — an earlier revision of this note named two victims, and tracing the code shows both are immune:

- A self-hosted, direct-mode `pipelex-api` cannot vary its PipeFunc directories within one process. `ApiRunner()` is constructed per request with `library_dirs=None`, which `resolve_library_dirs` resolves to instance defaults fixed at boot or `PIPELEXPATH` — both process-constant. The per-request variation is inline `.mthds` text, which registers no functions. Re-scanning the same constant dirs returns `sys.modules`-cached modules, so the same function objects re-register and the idempotent no-op absorbs them.
- The local MCP workshop (`pipelex-mcp`) is a TypeScript stdio *client* of the Pipelex API — it runs no pipelex in-process, and `.mthds` contents travel as text with no Python. It can only hit whatever server backs it, which is the previous (immune) case or the hosted runner.

Not the hosted runner either: `is_pipe_func_sandbox_hosted()` takes the source-capture branch and never registers in-process. The Temporal worker ignores `library_dirs` outright, and the transported-PipeFunc path is one-shot per process.

The exposed population is a **third-party embedder**: a long-lived Python process passing *different* `library_dirs` per call through the public surface (`PipelexMTHDSProtocol(library_dirs=…)`, `validate_bundles_in_process(library_dirs=…)`, `acquire_library(library_dirs=…)`), where two projects' Python files share a registration name. That is a legitimate use of a public parameter, so the narrowing is real — but when it fires, the failure is loud and typed (`FuncRegistryError` naming both origins and the `@pipe_func(name=...)` remedy), not silent corruption. This is why the narrowing was ruled non-blocking for PR #1076 (decision 2026-07-31): ship with the gap documented, fix ownership in its own PR.

Two loads of the **same** bundle are fine — `import_module_from_file` returns the module cached under its absolute-path key, so the second scan re-registers the identical object and the idempotent no-op absorbs it. The failure needs two *different* files that share a registration name.

## Why it was not fixed in #1076

There is no small correct fix. `func_registry` is a flat, process-global `dict[str, Callable]` with **no ownership dimension** — nothing records which library registered a name, so per-library eviction has nothing to key on. Note the asymmetry that makes this stand out: each `Library` already owns its own `ClassRegistry` (`Library.get_class_registry`, torn down with the library). Functions never got the same treatment.

The reviewer's proposed remedy — "registrations need library ownership and removal on teardown, including rollback after a failed scan" — is correct in substance and is a design change: a new ownership side-table, a `library_id` threaded through `FuncRegistryUtils` into `register_function`, eviction wired into `_pop_and_teardown_library`, and transactional rollback when a scan fails partway. That is not something to slip into a PR at bot-clean state.

## What doing it looks like

Give functions the ownership `ClassRegistry` already has:

1. Thread the owning library id into registration (`FuncRegistryUtils.register_funcs_in_folder` already runs inside `scoped_current_library`, but `func_registry` is runtime-layer and must not import the interpreter's `current_library` — pass the id in as a plain `str`).
2. Keep a `name -> library_id` side table; evict that library's names in `_pop_and_teardown_library`.
3. Roll back the names a scan registered when that scan raises partway, so a failed load does not leave half a library behind.
4. Then the collision check keys on live entries only, and the stale case disappears rather than being papered over.

Do **not** "fix" it by weakening the collision check back to a silent overwrite — that is the bug #1076 exists to remove.

## Related

- `wip/refactoring/structured-search-still-rebuilds-in-process.md`, `wip/refactoring/boundary-revalidation-round-trip-is-unaudited.md` — the other deferrals out of the same PR.
