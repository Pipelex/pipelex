# The fall-through corpus, measured across the whole workspace

**Status.** Measured 2026-08-11 for Phase 0 of [implementation-plan.md](implementation-plan.md). This widens [README.md](README.md) §5, which scoped its scan to a hand-written list of ten sibling repos. It does **not** gate shipping — the repo's no-backward-compatibility principle stands and there is no deprecation period. It calibrates the changelog wording and how much to invest in the error message.

This is a dated snapshot with a reproduction command, which is why it carries raw counts. Other documents should point here rather than restate them.

## How this scan differs from README §5

README §5 passed a hardcoded list of roots. Enumerating the workspace instead finds `.mthds` files in far more places, and a repo in neither column of a hardcoded list looks checked when it was never opened. Reproduce:

```bash
cd .. && ROOTS=(); for d in */; do
    case "$d" in _*|pipelex/) continue;; esac   # _* are worktrees of this repo; pipelex/ is its main checkout
    n=$(find "$d" -name "*.mthds" -type f -not -path "*/node_modules/*" -not -path "*/.venv/*" | wc -l)
    [ "$n" -ne 0 ] && ROOTS+=("$d")
done; cd _refs
.venv/bin/python wip/pipe-refs/probes/classify-bare-refs.py "${ROOTS[@]/#/../}"
.venv/bin/python wip/pipe-refs/probes/classify-bare-refs.py .
```

Requires bash or zsh — the array syntax is not POSIX `sh`. Use `-ne 0`, not `!= "0"`: BSD `wc -l` pads its output, so a string comparison never filters anything and the roots list silently differs between macOS and Linux.

## Numbers

| | this repo | every other `.mthds` tree in the workspace | README §5's narrower scan (ten sibling repos) |
| --- | --- | --- | --- |
| bundles read | 124 | 506 | 90 |
| merge units | 57 | 336 | 36 |
| **bare in-body pipe refs** | **142** | **1360** | 158 |
| `own-only` | 136 | 1331 | 153 |
| **`sibling-only`** — the column that breaks | **0** | **2** | 1 |
| `both` | 6 | 16 | 1 |
| `nowhere` | 0 | 11 | 3 |
| **bare in-body concept refs** | **283** | **2389** | 367 |
| `own-only` | 255 | 2197 | 341 |
| **`sibling-only`** | **0** | **3** | 0 |
| `both` | 27 | 135 | 22 |
| `nowhere` | 1 | 54 | 4 |

Read the columns as scopes, not as a total: the whole workspace is **630 bundles and 1502 bare pipe refs** (this repo plus every other tree). Like for like, widening the scan takes the corpus from README §5's 300 bare pipe refs (its ten repos' 158, plus this repo's 142) to 1502. Of the bundles outside this repo, §5's ten-repo list reached 90 of 506 — under a fifth.

## What the denominator is, and is not

The caveats in README §5 ("What this measurement does not cover") all still apply — in particular, a directory is not always a merge unit, so `both` is an upper bound and **`sibling-only` is the robust column**. Two more apply to this wider scan specifically, both inflating the denominator:

- **Duplicates.** The enumerated roots hold 510 `.mthds` files with only 360 distinct contents: 256 files sit in one of 106 byte-identical groups, spread across roots (starters, demos and fixtures copy bundles wholesale). The scan counts files, not distinct bundles.
- **Scratch trees.** Enumeration reaches material README §5 deliberately fenced off — the workspace's internal scratch, demo, and container-session trees (none of them open core; the list lives in the workspace-level private notes) — 67 files in all. §5 called the demo bundles pathological and kept them out; enumerating by definition cannot.

So the denominator is an upper bound and the breakage *ratio* is a floor. That does not touch the finding: the two breaking references are named files in neither category, and no scratch tree or duplicate contributed one.

## The two pipe references that break

Both are real, and one of them is not in an examples directory:

1. `pipelex-cookbook/examples/wip/advisory_board/bundle.mthds` — `advisory_orchestrator.master_advisory_orchestrator` names a bare `present_as_markdown` declared only by the `presentation` domain. Already scheduled for qualification in Phase 4b.
2. `cocode/cocode/pipelines/swe_diff/changelog_enhanced.mthds` — `changelog_enhanced.write_changelog_enhanced` names a bare `format_changelog_as_markdown` declared only by the `changelog` domain, in `changelog.mthds` in the same directory. **`cocode` is a shipped CLI, not a sample**, and README §5 never scanned it. Fix by writing `changelog.format_changelog_as_markdown`.

   This one is not an artifact of the probe's directory grouping: `cocode/common.py` sets `PIPELINE_LIBRARY_DIRS = [<package>/pipelines]`, so the whole tree loads as a single library and the two domains genuinely coexist in one merge unit.

Two references, and the fix for each is one qualified spelling.

## The three concept references are not new breakage

All three are in `vscode-pipelex/test-data/mthds/` (`pipe-definitions.mthds` referencing concepts declared in `concept-tables.mthds`). They are editor fixtures for the extension's goto-definition tests, and they **already** fail to load under today's runtime: the concept side qualifies to the owner domain at build time (`_qualify_concept_ref`), and `PipeFactory.make_from_blueprint` rejects a bare non-native concept ref that the pipe's own domain does not declare. README §5 reported zero simply because `vscode-pipelex/` was not one of its ten roots — its classifier reads TOML and is resolver-independent, so it would have counted these fixtures too had it opened them. The concept side of this change tightens the *library lookup*, which these fixtures never reach.

## What this means for the changelog

Say what breaks, not that something might: **a bare in-body pipe reference no longer resolves into another domain**, and across every `.mthds` tree in this workspace that is two references, both fixed by qualifying the spelling. Name the resolution rule and point at the error message, which suggests the crate-wide candidate when one exists.
