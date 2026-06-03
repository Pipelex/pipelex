# SWE-agent handoff — update MTHDS skills for the namespaced `validate` pipe identity

**For:** a SWE agent working in the **skills repo** (`../skills/skills/` relative to the pipelex project root — a separate checkout, not present in the pipelex worktree where this change landed).

**Why you're here:** the `pipelex` runtime changed the identity carried in the agent-CLI `validate` JSON envelope. Skills that consume that JSON may still assume the old form. This handoff tells you exactly what changed, what to hunt for, and how to verify. You can complete it without reading the pipelex diff, but pointers are included so you can confirm the contract yourself.

## The one-sentence change

`pipelex-agent validate pipe <code>` (and `validate pipe --bundle … <code>`) now report each pipe in `validated_pipes` by its **namespaced `pipe_ref`** (`domain.code`) instead of the **bare** `code`.

## What did NOT change (so you don't chase ghosts)

- **`validate all` and `validate bundle` are unchanged.** Those whole-set surfaces *already* emitted namespaced `domain.code` refs before this change. Any skill example or instruction tied to `validate all` / `validate bundle` was already correct — leave it.
- **The JSON shape is identical.** Still `{"success", "validated_pipes": [{"pipe_code", "status"}], "total_pipes"}`. The `pipe_code` **key name is unchanged** — only its **value** for the single-pipe surfaces changed from bare to namespaced.
- **`status` values are unchanged** (`SUCCESS` / `FAILURE` / `SKIPPED`).
- **Namespaced refs are still valid CLI inputs.** `get_required_pipe` resolves a `domain.code` ref directly, so any skill that feeds an emitted `pipe_code` back into a follow-up `validate pipe` / `run pipe` command keeps working.

So the entire blast radius is: **places that assume `validate pipe` echoes the bare code.**

## Concrete before/after

For `pipelex-agent validate pipe extract_invoice --format json`, where `extract_invoice` lives in domain `invoices`:

Before (what a skill may still assume):

```json
{
  "success": true,
  "validated_pipes": [{ "pipe_code": "extract_invoice", "status": "SUCCESS" }],
  "total_pipes": 1
}
```

After (current behavior):

```json
{
  "success": true,
  "validated_pipes": [{ "pipe_code": "invoices.extract_invoice", "status": "SUCCESS" }],
  "total_pipes": 1
}
```

## The highest-risk pattern to find

Skills are `SKILL.md` prose (plus optional `references/`) consumed by an LLM agent, so "breakage" is usually a **stale instruction or a stale example**, not compiled code. The single dangerous pattern is:

> **Exact-matching a bare code the skill itself passed in against the returned `pipe_code`.**

For example, an instruction like *"after `validate pipe <code>`, find the entry whose `pipe_code` equals `<code>` and read its `status`."* That equality now fails, because the skill passed a bare `<code>` but the entry reports `domain.<code>`. Rewrite such instructions to either:

- read the status from the **single** returned entry directly (these single-pipe surfaces return exactly one entry), or
- match by **suffix** (`pipe_code == code or pipe_code.endswith("." + code)`) when a bare code must still be reconciled.

Lower-risk, usually-fine cases (verify, but likely no change): displaying the code to the user (namespaced is clearer), keying an internal status map, or passing the code into a follow-up command.

## Where to look

The consuming skills and shared docs (paths relative to the skills repo root):

- Skill bodies most likely to read validate output: `mthds-check`, `mthds-fix` (they validate and report per-pipe status). Also scan `mthds-build`, `mthds-run`, `mthds-edit` for embedded validate examples.
- Shared reference docs: `shared/` — especially anything documenting the agent-CLI `validate` JSON shape (e.g. `mthds-agent-guide.md`).

Grep starting points:

```bash
grep -rn "validated_pipes" .
grep -rn "validate pipe" .
grep -rn "pipe_code" .
```

For each hit, ask: *does this assume the value is the bare code, specifically for a single-pipe `validate pipe` call?* If yes, update the prose and any embedded example JSON to the namespaced `domain.code` form. If it's a `validate all` / `validate bundle` context, leave it.

## How to verify

1. Run a single-pipe validate against any bundle and confirm the emitted `pipe_code` is namespaced:

   ```bash
   pipelex-agent validate pipe <some_pipe> --format json
   ```

   Expect `validated_pipes[].pipe_code` to be `domain.<some_pipe>`.

2. Walk each updated skill's instructions against that real output and confirm no step relies on a bare match.
3. If the skills repo has its own test/lint/CI, run it.

## Provenance (pipelex side — for confirming the contract)

Landed on branch `feature/Validate-with-signatures-4-fix-dry-run`.

- Source of truth: `pipelex/pipeline/validate_bundle.py::build_validated_pipes` → returns `ValidatedPipeEntry` whose `pipe_code` is `output.pipe_ref` (namespaced) on every surface.
- Contract doc: the `validate` output section in `pipelex/cli/agent_cli/CLAUDE.md`.
- Rationale + full in-repo change list: `wip/dry-run-refactor-draft/followup-validate-result-projection.md` (the "RESOLVED" record this handoff is the cross-repo tail of).
- Changelog: the `[Unreleased] → Changed` entry naming the `validated_pipes` identity unification.

The decision was to **unify on `pipe_ref`** so the same pipe is never reported under two identifiers by different `validate` commands. This handoff exists because the skills repo could not be inspected or edited from the pipelex worktree where the change was made.
