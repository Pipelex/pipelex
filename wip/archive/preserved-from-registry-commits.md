# Preserved changes from rolled-back commits

These are valuable additions from commits e23e5ffc and 799836e8 that should be
re-applied after the reset to 69a2c9e8.

---

## 1. CLAUDE.md additions

Two new sections to add back to CLAUDE.md under the Temporal testing section:

### Temporal Execution Model — ContextVar Boundaries

**ContextVars do NOT propagate across Temporal execution boundaries.** This is a critical constraint when writing workflows and activities that use `hub.get_class_registry()` or any ContextVar-based state:

- **Workflow -> activity:** Activities run in a fresh execution context (separate thread pool). A ContextVar set in a workflow's coroutine is invisible to activities dispatched by that workflow. Activities can also run on a **different worker** or even a **different server**.
- **Workflow -> child workflow:** Child workflows run in their own execution context. ContextVars from the parent workflow are not inherited.
- **Inline await (same coroutine):** ContextVars DO propagate. For example, `pipe.run_pipe()` called directly (as `await`) in `WfPipeRouter.run()` shares the workflow's ContextVar context.

**Practical rule:** Any state that an activity needs must be passed explicitly via its arguments (the assignment models). Never rely on ContextVars being visible in activities.

### Temporal E2E Testing — Clean Slate Rule

When running Mode 2 (3-process) E2E tests, **always start from a clean slate:**

1. Kill existing tmux sessions (`temporal-worker` first, then `temporal-server`)
2. Clear `__pycache__` under `pipelex/temporal/` (stale bytecode causes the worker to run old code)
3. **Start a fresh Temporal server** — this is what flushes workflow history. `temporal server start-dev` uses an **in-memory database** by default: killing and restarting the server process is all it takes to get a clean history. There is no persistent state to delete.
4. Start a fresh worker

**Why restarting the server matters:** Stale workflow history causes **nondeterminism errors** when workflow code has changed between runs. The server remembers the old workflow's event history, and when the new worker replays it, it detects that the code produces different decisions. Simply restarting the worker is NOT enough — the server holds the history, and it must be restarted too.

---

## 2. SKILL.md changes (temporal-e2e-validate)

### Added allowed-tools
```
  - Bash(lsof *)
  - Bash(find *)
```

### Mode 1 Step 1: added note
Mode 1 uses in-process workers (not the external tmux worker), so stale server history
is less of a concern here. But if tests fail with nondeterminism errors, kill and
restart the server — it uses an in-memory database, so restart = clean history.

### Mode 2: major rewrite
- Replaced "Step 1: Ensure Temporal server is running" + "Step 2: Start the worker process"
  with "Step 0: Clean slate (MANDATORY)" + "Step 1: Start fresh Temporal server and worker"
- Clean slate section: kill worker first, then server, clear __pycache__, sleep
- Startup section: start server first, verify, then start worker
- Added port conflict check hint (lsof)
- Fixed flag usage: removed `--pipe-run-mode live` (not a real flag), just remove `--dry-run --mock-inputs` for live mode
- Fixed tier 4 and 5 commands: removed `--pipe-run-mode live` flag

### Ask-the-user phrasing fix
Changed: "replace `--dry-run --mock-inputs` with `--pipe-run-mode live`"
To: "omit `--dry-run --mock-inputs` (there is no `--pipe-run-mode` flag)"
