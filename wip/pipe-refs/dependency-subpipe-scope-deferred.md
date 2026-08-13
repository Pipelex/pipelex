# Deferred: a dependency pipe's own sub-pipe refs resolve against the HOST library

**Status.** Measured 2026-08-11 while answering OQ1 of [build-time-qualification.md](build-time-qualification.md). Pre-existing, independent of the pipe-refs change, and deliberately **not** fixed on this branch — the fix needs package scope threaded through the lookup, which is the packaging project's design work. Reproduce with [`probes/dep-subpipe-scope.py`](probes/dep-subpipe-scope.py).

Code is cited by symbol, not by line: this note is written to outlive the branch, which itself edits several of these regions.

## What is broken

A dependency package is loaded into an isolated *child* `Library` and its pipes are **also** registered in the host library under aliased keys (`alias->domain.code`). When a dependency's own controller pipe names a same-domain sub-pipe, three readers disagree about which library to search:

| Reader | Where | Scope it searches |
| --- | --- | --- |
| dependency-dep loop | `Library.validate_pipe_library_with_libraries`, its first loop | the **child** library — explicitly special-cased for an aliased pipe key |
| per-pipe validation | same method's second loop → `PipeAbstract.generic_validate_inputs_with_library` → `PipeSequence.needed_inputs` | the **host** library, via `interpreter_hub.get_required_pipe` — no special case |
| execution | `SubPipe.run_pipe` | the **host** library, via the same hub accessor — no special case |

The child-library special case is neutralized by the second loop in the very same method. And the host lookup cannot reach the dependency's own pipe either: `PipeLibrary.get_optional_pipe` is a strict key lookup, so a bare code matches nothing there. (Before this branch it instead ended in a crate-wide bare-code fall-through that explicitly **skipped** `alias->` entries — same outcome, different mechanism; that fall-through is what row 2 of the baseline table below measured.)

## A second defect, in the shape a real package ships

The child library is built from the crate under an export filter (`if has_exports and pipe_code not in all_exported: continue`, in `LibraryManager._load_single_dependency`). It carves out *synthetic* helpers — the comment right above it states the hazard exactly: "When the parent is exported, its helpers must travel with it — otherwise the wrapping PipeSequence references unresolved pipe codes at runtime." It does **not** carve out **authored** ones. So a controller's own private helper is dropped from its own package's library, and the failure lands before the scope disagreement above can even be reached.

## Measured behaviour

The table below is the **pre-Phase-2 baseline** — measured before the qualification pass landed on the dependency load path. Re-running the probe on this tree shows the post-change verdicts the next section describes: shapes 1 and 3 still fail, and row 2's silent capture is now a deterministic load failure.

A dependency whose exported entry is a `PipeSequence` calling a bare same-domain helper, under three shapes:

| Shape | Load verdict | What the execution reader resolves the helper to |
| --- | --- | --- |
| no manifest exports; host declares nothing | **fails** in the *second* loop — `PipeNotFoundError: Pipe 'probe_helper' not found` | `None` |
| no manifest exports; host declares its own unrelated pipe under the same bare code | **valid** | the **HOST's** pipe — a silent cross-package capture |
| manifest `[exports]` names only the entry pipe — *the published shape* | **fails** in the *first* loop — `LibraryLoadingError: Error validating pipe 'probe_entry' dependency pipe 'probe_helper'` | `None`; the helper is absent from the child library too |

So today a dependency package that uses a controller internally either does not load at all, or loads and binds to whatever the host happens to have named the same way. Neither is the dependency's own helper. No fixture in `tests/data/packages/` exercises this — every dependency there exports a leaf `PipeLLM`, which is why it has never surfaced.

## Why the pipe-refs change does not fix it, and does not worsen it

Owner-domain qualification rewrites the authored bare `helper` to `dep_domain.helper`. Measured against the same host library, that ref also resolves to `None` — the host holds it as `alias->dep_domain.helper`. So:

- **not a regression, but only because the two edits co-landed.** Reader row 1 *was* served by the bare fall-through: the child library's keys are `dep_domain.helper`, and the first loop looked up a **bare** code against it, which only succeeded via that fall-through. Deleting the fall-through alone would have broken row 1. Both edits landed in the same phase — the qualification pass on the dependency load path (`LibraryManager._load_single_dependency`) and the strict lookup — so the first loop's lookup is qualified now that the fall-through is gone. That co-landing was load-bearing, not incidental — it is also what makes "`library` validation needs no edit" true.
- **strictly better on the capture.** The silent host-capture in row 2 becomes a deterministic not-found. A bundle that loads today and runs the wrong pipe will stop loading — loudly, naming `dep_domain.helper`, which points at the scope that should have been searched.
- **it moves the eventual fix closer.** The child library's own keys are exactly `dep_domain.helper`. Once the lookup is package-scoped, a qualified ref is a direct key hit in the child library; a bare one would still need a search.

## What the fix requires (packaging project)

Two independent pieces, both needed:

1. **Scope.** The caller's **package** must reach the lookup, the way its domain now does. Either the resolved sub-pipe ref carries its alias (`alias->dep_domain.helper`) when the referring pipe came from a dependency, or the run scopes the current library to the child while executing inside that package. Both are contract decisions about cross-package reference form, which [build-time-qualification.md](build-time-qualification.md) explicitly defers ("No cross-package resolution design"). Whichever is chosen, the two validation readers and the execution reader must end up on the same one — that is the parity requirement this note exists to preserve.
2. **Export filtering.** A pipe an exported pipe depends on must travel with it, whether the helper is synthetic or authored. Scope alone does not fix the published shape: the helper is not in the child library to be found.
