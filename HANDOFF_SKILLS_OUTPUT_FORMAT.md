# Handoff: Agent CLI Output Format Changes → Skills Repo

**Date**: 2026-03-23
**PR**: #778 (feature/Output-text-for-agents → dev)
**Scope**: `../skills/skills/` (the published MTHDS marketplace plugin)

## What changed

The `pipelex-agent` CLI changed its output format for several commands:

| Command | Before | After |
|---------|--------|-------|
| `concept` | JSON with `toml` field | Raw TOML to stdout |
| `pipe` | JSON with `toml` field | Raw TOML to stdout |
| `models` | JSON | **Markdown by default**, JSON with `--format json` |
| `doctor` | JSON | **Markdown by default**, JSON with `--format json` |
| `assemble` | JSON | **Removed entirely** |

## What the skills should do

**Do NOT add `--format json` to `models` or `doctor` calls.** The markdown default is intentional — LLM agents consume markdown more naturally than JSON. The skills should expect and work with the markdown output as-is.

The `concept` and `pipe` commands now return raw TOML directly. Any skill that was parsing JSON to extract the `toml` field should read stdout directly instead.

## Files to update

### `skills/shared/mthds-agent-guide.md`

- **Line 47**: "outputs structured JSON (stdout=success, stderr=error with exit code 1)" → Update to reflect the three output modes: JSON for run/validate/inputs/init, raw TOML for concept/pipe, markdown for models/doctor. Errors are always JSON on stderr.
- **Lines 281-282**: Command table entries for `models` and `doctor` — note markdown default output.

### `skills/mthds-build/SKILL.md`

- **Lines 254-257**: `mthds-agent pipelex models --type ...` — these calls now return markdown. No code change needed, but any surrounding text that says "parse the JSON" should be updated.

### `skills/mthds-build/references/talents-and-presets.md` and `skills/mthds-edit/references/talents-and-presets.md`

- **Line 7**: References `mthds-agent pipelex models` — output is now markdown.

### `skills/mthds-pipelex-setup/SKILL.md`

- **Lines 57, 119**: References `mthds-agent pipelex doctor` — output is now markdown.

### `skills/mthds-run/SKILL.md`

- **Line 62**: References `mthds-agent pipelex doctor` — output is now markdown.

### `skills/shared/error-handling.md`

- **Lines 105-106, 115**: These reference `doctor` in error hints/instructions — no change needed, they just tell the agent to run the command.

## Summary

The key message: **models and doctor now speak markdown to the agent, not JSON. This is by design. Do not revert to JSON.**
