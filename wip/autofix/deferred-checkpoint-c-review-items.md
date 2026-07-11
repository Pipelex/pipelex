# Deferred follow-ups from Checkpoint C (`strip-namespace`)

The Phase C review fan-out (multi-agent `/code-review` on the staged strip-namespace diff) surfaced eight findings. Three were fixed immediately (applier crash on `OutOfOrderTableProxy`/`InlineTable`, the `main_pipe` retarget collision gate in the categorizer, the cross-file rename collision guard in the fix loop). The two below are confirmed limitations deliberately deferred for later review; the cleanup notes at the end are recorded for completeness.

## 1. `main_pipe` strip can rewrite to a pipe that does not exist

**What it is.** The `main_pipe` strip enrichment never verifies that the bare target pipe exists — the `main_pipe` field validator runs before `pipe` validates, and the categorizer gate we added only suppresses the *retarget* case (both dotted and bare declarations present). With `domain = "greetings"`, `main_pipe = "greetings.helo"` (typo'd tail, no `[pipe.helo]` anywhere), the tail is valid snake_case so the enrichment fires, the SAFE fix rewrites the file to `main_pipe = "helo"`, and re-validation fails with the model validator's "Main pipe 'helo' could not be found" — an unfixable error. The user's file was mutated by a fix advertised as SAFE, the bundle stays invalid with a *different* error, and the author's original over-qualified spelling (which pointed at what they meant) is gone from the file.

**Why it's deferred, not fixed.**

- The natural home for an existence check is the categorizer's document-level gate (it holds the raw bundle dict, same as the retarget gate). But "exists" is subtler than it looks: the raw `pipe` dict at that point may itself contain dotted keys that a *sibling* strip-namespace fix will rename in a later iteration — `main_pipe = "d.hello"` with only `[pipe."d.hello"]` declared is exactly the convergent happy path (both strip to `hello` across iterations), and a naive "bare target must already exist" check would kill it.
- The correct predicate is roughly "the bare tail exists as a key OR the dotted code itself exists as a key (its rename will materialize the bare target)". That needs deciding together with finding #5's one-error-per-pass behavior, since convergence order is what makes the second disjunct sound.
- The failure mode leaves a *loud* residual error naming the missing pipe, not silent wrong execution — bad UX, not a correctness trap like the retarget case was.

**If revisited.** Extend `_main_pipe_strip_would_retarget` in `validation_error_categorizer.py` into a broader `_main_pipe_strip_is_safe` gate implementing the two-disjunct predicate above, and pin the typo'd-tail scenario (enrichment suppressed, file untouched) plus the dotted-declaration happy path (still converges) in `test_strip_namespace_enrichment.py`.

**Related (PR #1031, cubic P2 — same defect, second site).** A second review flagged that the `main_pipe` strip `SET_KEY` is not filtered by the fix loop's cross-file sibling-collision gate (`_is_cross_file_colliding_rename` / `_split_cross_file_rename_collisions`, `fix_loop.py:112-141`), which only recognizes `RENAME_TABLE_KEY` ops. The *stated* impact — silently retargeting `main_pipe` to a sibling file's pipe — is a **false positive**: `validate_main_pipe` is bundle-local and runs per-file before any library merge, so a stripped `main_pipe` can never resolve to a sibling's pipe; it always fails loudly with "could not be found". But the underlying gap is real and benign: in a two-file same-domain library (file A `[pipe."d.hello"]` + `main_pipe = "d.hello"`, sibling B `[pipe.hello]`), iteration 1 drops the paired declaration rename (cross-file collision) yet keeps and applies the `main_pipe` `SET_KEY`, writing an orphaned `main_pipe = "hello"` to file A before iteration 2 bails loudly on the still-present dotted declaration. Same benign family as this item (pointless file mutation, loud residual — not silent corruption). **Key coupling for the fix:** the categorizer-only gate proposed above does **not** cover this case — its second disjunct ("the dotted code exists as a key, so its rename materializes the target") is satisfied here, but the categorizer can't see that the rename will be blocked cross-file. So the suppression must **also** live in the fix loop's `_split_cross_file_rename_collisions` (`fix_loop.py:120`), where `sibling_pipe_codes` is known — e.g. also drop a root `main_pipe` `SET_KEY` whose value is in `sibling_pipe_codes` (or whose paired declaration rename was just dropped as colliding). The clean fix therefore spans **both** the categorizer and the fix loop.

## 2. One declaration rename per iteration caps convergence at `max_iterations` dotted keys

**What it is.** `validate_pipe_keys` (a `mode="before"` field validator) raises on the *first* invalid pipe key, so each validation pass surfaces at most one strip-namespace declaration rename. A bundle with more over-qualified `[pipe."domain.xxx"]` keys than `max_iterations` (default 5) exhausts the loop and returns `is_valid=False` with bail_reason "max_iterations reached without convergence" and a partially-rewritten file — even though every remaining error was mechanically fixable by the same rule.

**Why it's deferred, not fixed.**

- It is a completeness limitation, not a misfix: every rename applied is individually correct, and the bail is loud and explains itself.
- The same one-error-per-pass shape is already an accepted convergence pattern in this codebase (`strip-native-concept-redecl` converges error-by-error the same way; pinned by `test_native_redeclarations_converge_error_by_error`).
- The clean fix is to collect *all* invalid pipe keys in one pass and raise an aggregate (or plan one fix with multiple rename ops, the way `sync-controller-inputs` repairs all input drift at once). That changes the raise-site contract (`InvalidPipeCodeSyntaxError` carries one offending code) and the categorizer/planner discrimination protocol with it — a coherent follow-up chunk, not a patch to sneak in during review triage.

**If revisited.** Either (a) make `validate_pipe_keys` accumulate offending keys and raise a multi-code error the planner turns into one multi-op fix, or (b) simply raise `max_iterations` for the declaration-rename rule. (a) is the solid fix; (b) is a stopgap that just moves the cliff.

## Cleanup notes recorded, no action taken

- The declaration-vs-`main_pipe` raise site is inferred implicitly twice (pydantic `loc[0]` in the categorizer, `pipe_code` None-ness in the planner) instead of riding the typed exception explicitly. An explicit marker on `InvalidPipeCodeSyntaxError` would remove both inference points.
- `_strippable_same_domain_pipe_code` re-implements dotted-ref parsing that `QualifiedRef.parse()` provides; two parsers for one grammar can drift.
- `existing_pipe_codes` in `validate_pipe_keys` is built eagerly on every bundle validation even when all keys are valid; a lazy build would keep the happy path allocation-free.
