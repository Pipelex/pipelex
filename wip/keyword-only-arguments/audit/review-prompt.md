# Cold-start prompt — audit the positional-subject decisions

Paste the block below into a fresh session to run the review. It points the session at the audit file, fans out Sonnet 4.6 sub-agents per package, and produces a consolidated suspect list without touching any source.

---

We just finished a keyword-only-arguments refactor of the pipelex/ runtime. Exception 1 of the convention lets the first true parameter (the "subject") stay positional. I want to audit whether that exception was ever ABUSED — i.e. a first arg made positional just to satisfy the rule, when it isn't really the semantic object of the function and would read better keyworded.

The full population is enumerated in:
  wip/keyword-only-subject-positional-audit.md

Start by reading that file's "## Review strategy" section — it's the playbook. The headline points, so you don't re-derive them:

- This is a naming/API-taste call, not a reasoning task. Run the per-line judgments with SONNET 4.6 sub-agents (model: sonnet), fanned out one per package. Don't use Opus for the sweep.
- The bottleneck is CONTEXT, not model grade. Each sub-agent MUST have Read + Grep and is expected to open the function body (and a call site or two) whenever the signature alone is ambiguous. Do NOT just hand it the text line.
- Calibration matters: instruct each sub-agent to DEFAULT TO "fine" and emit ONLY the suspects, each as: file:line — function — current signature — why the positional reads wrong — suggested fix (usually "move the * before this arg too"). Cite the rubric in docs/contribute/keyword-only-arguments.md.

Triage (don't review all 1806 lines):

1. Section B (LONE_SUBJECT, ~1003) is mostly noise — one positional param means there was no subject choice to abuse. From it, keep ONLY primitive-typed lone subjects (bool/int/str/float, e.g. do_thing(True)); filter the rest mechanically. No LLM needed for the filter.
2. Fan out Sonnet 4.6 over Section A (SUBJECT_THEN_KEYWORDS, 797) + the primitive lone-subjects, one agent per package (the audit groups entries by package with counts).
3. Each sub-agent WRITES its package's shortlist to its own file:
     wip/keyword-only-audit-findings/<package>.md
   (disjoint paths, so parallel writes are safe; this preserves exact file:line citations that a returned chat message might truncate). Each entry:
     file:line — function — current signature — why the positional reads wrong — suggested fix
   An agent that finds nothing writes a file stating "no suspects".
4. After the fan-out, YOU (orchestrator) merge those into one consolidated report:
     wip/keyword-only-subject-positional-suspects.md
   grouped by package, ordered by confidence, with a top summary count. Then stop and show me — I'll adjudicate (or we point Opus at just that shortlist).

Scope of "don't change code": do NOT edit any pipelex/ source or tests in this pass — this is review only. Writing the findings/ files and the consolidated suspects report IS the deliverable, not a code change.
