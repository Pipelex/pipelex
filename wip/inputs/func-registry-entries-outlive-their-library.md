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

- A self-hosted, direct-mode `pipelex-api` serving `/validate` or `/execute` for more than one project.
- The local MCP workshop across bundles.

Not the hosted runner: `is_pipe_func_sandbox_hosted()` takes the source-capture branch and never registers in-process.

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

- `wip/inputs/structured-search-still-rebuilds-in-process.md`, `wip/inputs/boundary-revalidation-round-trip-is-unaudited.md` — the other deferrals out of the same PR.
