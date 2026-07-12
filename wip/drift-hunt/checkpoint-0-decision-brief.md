# Checkpoint 0 — decision brief for Louis

Where we are: Stage 0 (the mechanical pre-screen) is done and its confirmed defects are already fixed and committed. The campaign is paused before Stage 1, which is the expensive part — a fleet of review agents reading every in-scope doc page and checking its claims against the code. Three decisions are yours before that fleet launches. This brief explains each one; the underlying data lives in `suspects.md` and `inventory.md` (same folder) and the live tracker is the repo-root `TODOS.md`.

## Decision 1 — bless the triage in `suspects.md`

**What it is.** The pre-screen script produced 45 raw "this claim looks wrong" hits. I verified each one against the real surface (running the CLI, parsing scratch bundles with the real MTHDS parser, checking the tree) and sorted them into three buckets: confirmed defects (5 — already fixed, nothing for you to do there), needs-judgment questions (3 — parked as seeds for Stage 1), and false positives (the rest, distilled into 8 named patterns).

**Why your eyes matter here.** The 8 false-positive patterns become standing instructions to every Stage 1 agent — literally "do not flag X". If one of those patterns is wrong (something I called a false positive that you actually consider drift), Stage 1 will be systematically blind to it, across all pages. The reverse also costs: a pattern I missed means every agent re-reports the same noise and the verify pass burns tokens killing it page after page.

**What to do.** Read the "False positives" and "Needs judgment" sections of `suspects.md` (~5 minutes). Two of the patterns are worth a deliberate opinion rather than a rubber stamp:

- *MTHDS-dialect leniency*: doc examples use multi-line inline tables, trailing commas, comments inside inline tables — invalid vanilla TOML, but the real parser accepts them (I verified live). I classified these as fine-as-is. If you'd rather docs stick to strict-TOML shapes anyway (portability, tooling), say so and it becomes a Stage 2 fix class instead.
- *Shortcut command forms*: `pipelex validate --all` looks dead in `--help` but works via a hidden forwarding layer. I treated the docs as correct. If you consider the `--help` invisibility itself a defect, that's a code/CLI issue to file, not a doc fix.

**Outcome of this decision:** possibly a couple of reclassified rows, and the final wording of the "do not flag" list baked into Stage 1 prompts.

## Decision 2 — settle the scope edges the plan didn't name

**What it is.** D2 (in `TODOS.md`) defines scope as "hand-written pages under `docs/`", lists the sections, and excludes generated pages and the freshly-reviewed config/CLI docs. Building the inventory surfaced pages that D2's list simply never mentioned — they need an explicit in-or-out call so the defect-density denominator is honest.

**The pending items and my proposal:**

- `docs/agents/debugging-hanging-pytest-runs.md`, `docs/analytics/data-extraction.md`, `docs/distributed-execution/index.md`, `docs/CLAUDE.md` — all four are hand-written and full of claims the code can contradict; none is generated or freshly reviewed. **Propose: IN** (adds 4 pages to the 119, negligible cost).
- Root-level `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` — published on the docs site through include-stubs, but they live outside `docs/`. CODE_OF_CONDUCT has essentially nothing code-contradictable; CONTRIBUTING may carry stale commands. **Propose: OUT**, unless you want CONTRIBUTING swept (then it's +1 page).

**What to do.** A one-liner suffices — "in as proposed", or name exceptions.

## Decision 3 — Stage 1 shape and budget (the real go/no-go)

**What Stage 1 is.** Per page: one review agent reads the page, extracts every checkable claim (commands, config keys, paths, described behaviors, code snippets), verifies each against the current code — cookbook pages verify against `../pipelex-cookbook` — and reports findings with severity and `file:line` evidence. Then, per D6, every finding goes to an independent verifier agent prompted to refute it; only confirmed findings survive. Stage 1 produces **findings only** — no fixes. Fixes happen in Stage 2, after you triage the findings at Checkpoint 1.

**The cost.** ~123 pages, ~855 words average (heaviest: under-the-hood, up to ~4.4k words/page). Each review agent also greps and reads source, which dominates its token use. Estimate: **roughly 8–15M tokens** for the full review + verify fleet. That's an order-of-magnitude estimate, not a quote — the verify pass scales with how many findings the review pass surfaces.

**The options:**

1. **Full fan-out, worst-sections-first ordering (my recommendation).** All in-scope pages, run as section waves ordered by expected yield (building-methods → under-the-hood → cookbook → the rest). You get the complete per-section defect-density table — which is the campaign's stated point, the evidence base for deciding which sections earn a drift contract later (D5). The wave ordering gives you a kill switch: after each wave I report findings-so-far and burn rate, and you can stop the remainder if the tail sections look like a waste.
2. **Worst-sections-first, stop-and-decide.** Same ordering, but only building-methods + under-the-hood + cookbook are authorized now (~75 pages, roughly half the budget); we re-decide the rest on the evidence. Cheaper start, but the cross-section density comparison — the deliverable — stays incomplete until the rest runs eventually anyway.
3. **Don't run Stage 1 at scale.** Keep only the 3 needs-judgment seeds as targeted checks. Cheapest; abandons the density evidence.

**What to do.** Pick an option (and a budget cap if you want one — e.g. "option 1, cap at 10M"; the Workflow budget mechanism enforces caps hard).

## What happens after you answer

1. I fold your rulings into `TODOS.md` (scope, FP list, Stage 1 authorization) and adjust `inventory.md` if the scope changed.
2. Stage 1 launches as a Workflow per your chosen shape — review agents seeded with each page's Stage 0 suspect rows and the blessed do-not-flag list, verify agents refereeing every finding.
3. **Checkpoint 1 (next stop for you):** findings committed under `wip/drift-hunt/findings/`, ranked by severity, with a rejected-findings list. You triage: confirm severity order, kill anything that smells editorial, agree fix order. No fixes before that.
4. Stage 2 fixes land as one commit per section (separate PRs if a batch grows), each fix re-verified against code at fix time; Checkpoint 2 closes the campaign with the density table and the contract-candidate shortlist.

**Side note, independent of the hunt:** the drift-tool hardening (auto-staged acks + the verify-contract escalation) sits on this branch but is functionally unrelated to the doc sweep. If you want it on `dev` sooner, say so and I'll carve it into its own PR; otherwise it rides along.
