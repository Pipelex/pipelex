# MTHDS Documentation — Authoring Tactic

## Context

The strategy doc (`refactoring/mthds-documentation-website-strategy.md`) is done. Now the question: **how should we actually write the documentation content?** The MkDocs repo exists separately. This Pipelex repo has all the source material (design docs, implementation briefs, actual codebase). We need to decide where and how to author content before it moves to MkDocs.

## The Problem

The sitemap has ~30 individual pages. Writing them one-by-one across many Claude Code sessions has two major issues:

1. **Context loss between sessions.** Each new session starts fresh. The standard has deep internal coherence — concepts reference pipes, pipes reference domains, the package system builds on the language. Writing page-by-page fragments this.

2. **This repo is the source of truth.** The design docs, implementation brief, and actual Python code define what the `.mthds` format really is. Claude Code needs to grep the codebase to verify documentation accuracy. Working in the MkDocs repo means losing that access.

## Approach: Pillar-Level Source Documents in This Repo

Instead of 30 individual pages, write **6 comprehensive source documents** in `docs/mthds-standard/` within this repo. Each document covers an entire section of the sitemap, maintaining internal coherence. Later, splitting into individual MkDocs pages is mechanical.

### The 6 Documents (mapped to strategy phases)

| # | Document | Covers (from sitemap) | Phase |
|---|----------|----------------------|-------|
| 1 | `00-home-and-overview.md` | Landing page + "What is MTHDS?" + Two Pillars + Progressive Enhancement | A |
| 2 | `01-the-language.md` | Bundles, Concepts (all), Pipes — Operators (all 5), Pipes — Controllers (all 4), Domains, Namespace Resolution | A |
| 3 | `02-the-package-system.md` | Package Structure, Manifest, Exports, Dependencies, Cross-Package Refs, Lock File, Distribution, Version Resolution, Know-How Graph | B |
| 4 | `03-specification.md` | `.mthds` format (normative), `METHODS.toml` format, `methods.lock` format, Namespace Resolution Rules (formal) | A+B |
| 5 | `04-cli-and-guides.md` | CLI Reference (all commands), all 5 Guides (First Method, Create Package, Use Deps, Publish, Discover) | B+C |
| 6 | `05-implementers-and-about.md` | Building a Runtime, Validation Rules, Package Loading, Design Philosophy, Agent Skills Comparison, Roadmap, Contributing | C+D |

### Why This Works

- **Coherence.** Writing the entire Language pillar in one document means concepts, pipes, and domains can cross-reference naturally. No risk of inconsistency between pages.
- **Codebase access.** Each document is written in this repo, where Claude Code can grep `pipelex/core/` to verify field names, validation rules, pipe types, etc.
- **Efficient sessions.** One document per session (or two if small). Much better than 5-6 pages per session with constant context-switching.
- **Easy migration.** Each document uses `## Page: <title>` markers. Splitting into individual `.md` files for MkDocs is a 5-minute scripting task.
- **Reviewable.** You can read an entire pillar end-to-end before committing to the MkDocs repo.

### Writing Order

1. **`03-specification.md`** first — the normative reference. Everything else derives from it. If the spec is right, the teaching content will be right.
2. **`01-the-language.md`** — teaches Pillar 1 using examples from the spec.
3. **`02-the-package-system.md`** — teaches Pillar 2, including the Know-How Graph.
4. **`00-home-and-overview.md`** — the overview is easier to write after the substance exists.
5. **`04-cli-and-guides.md`** — tutorials and reference, grounded in everything above.
6. **`05-implementers-and-about.md`** — last, since it's the most contextual.

### Document Internal Structure

Each source document uses this pattern:

```markdown
# Section Title (e.g., "The Language")

<!-- Source document for the MTHDS docs website.
     Each "## Page:" section becomes an individual MkDocs page. -->

## Page: Bundles

[content for the Bundles page]

---

## Page: Concepts

[content for the Concepts page]

---
```

This makes the eventual split trivial while keeping everything reviewable as a single document.

## Verification

- After each document is written, read it end-to-end for coherence
- Grep the codebase to spot-check any technical claims (field names, pipe types, validation rules)
- Cross-reference between documents to verify consistency
- When all 6 are done, do a final pass for tone consistency (per strategy doc guidelines)
- Test the split: extract one section into a standalone `.md` and verify it reads well independently
