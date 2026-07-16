# Deferred follow-ups from Checkpoint B (`strip-native-concept-redecl`)

The Phase B review fan-out (Sonnet-5 `/code-review` on the Phase B diff, no inherited context) surfaced two items. Neither is a defect; both are recorded here and closed for Phase B.

## 1. Comment reflow when deleting a `[concept.X]` table with a leading comment

**What it is.** `DELETE_KEY` on `["concept"]` removes the redeclared concept via tomlkit's `del`. When a *standalone comment line* sits directly above the deleted `[concept.X]` table, tomlkit reattaches that comment as leading trivia of the **next** surviving element (the successor table). `format_mthds` reflows spacing but does not reposition comments, so the comment ends up annotating unrelated content — a stale, potentially misleading comment describing removed illegal content now appears above legitimate content.

**Why it's not fixed.**

- The guarantee we make is that comments on *untouched* content survive; a comment sitting **on the deleted concept** is the only thing that can dangle.
- Repositioning/removing a deleted node's leading trivia is fiddly tomlkit container-body work, disproportionate to a purely cosmetic artifact.
- The autofix output is whole-file canonical MTHDS that the author reviews (and CI reformats). A leftover comment is visible in that review, not silently shipped.

**What we did instead.** Pinned the behavior with a characterization test (`test_leading_comment_on_deleted_table_reflows_onto_successor` in `tests/unit/pipelex/pipeline/fixes/test_fix_applier_native_concept.py`) so it is explicit and regression-caught rather than an undocumented surprise, and kept the golden fixtures clean (comments placed on surviving content, which is what the fix guarantees to preserve).

**If revisited.** A general "strip a deleted node's leading standalone comment(s)" pass in the applier would remove the artifact for every delete-shaped fix (this rule and any future one). Weigh it when a delete-shaped fix first ships to a human-facing surface (master-plan step 5), not before.

## 2. `_extract_wrapped_native_concept_redeclaration_error` shares the shape of `extract_wrapped_pipe_validation_error`

Both do the same three steps (check `error["type"] == "value_error"`, pull `ctx["error"]`, `isinstance`-narrow). The reviewer flagged a possible generic `TypeVar`-based unwrap helper serving both, then judged it "not a real problem — a small, readable, well-documented function."

**Decision: no action.** Two readable call sites do not justify a generic helper; the same "keep the house style, don't over-abstract the enum-match/unwrap duplication" call was made at Checkpoint A. Revisit only if a third structural-unwrap site appears.
