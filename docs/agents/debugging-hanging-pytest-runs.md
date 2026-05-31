# Playbook: debugging a hanging pytest run in one shot

**Audience.** Future-me (or any agent) the next time a `make agent-test` / `pytest -n auto` run hangs without finishing. Specific to this codebase, where the most common cause of a hang is Temporal integration-test infrastructure (in-process test servers, xdist worker crashes, fixture teardown), but the iteration loop generalizes to any hanging suite.

**Why this exists.** In a recent session (Issue 2 fix to `with_conditional_worker`), I burned ~30 minutes across multiple test runs that all hung or got killed, requiring the user to flag the hang each time. Every individual decision was defensible; the *iteration loop* was broken. Following the playbook below, the whole thing — code fix, verify unit, verify integration, find the real failure, fix it, verify again — should finish in one autonomous pass.

---

## What I did wrong (concrete, in order)

1. **`make agent-test` is silent on success.** I backgrounded it and waited for harness notification. The output file stayed 0 bytes for 14 minutes. The user had to flag it. → No progress signal at all.

2. **Re-ran with `-q` flag.** Even more aggressive buffering. Still 0 bytes for the whole run. → Same problem.

3. **Re-ran with `| tail -80`.** Pipe buffering means tail receives nothing until pytest exits. 0 bytes again. → Same problem.

4. **Set `--timeout=120 --timeout-method=thread`.** Believed this bounded the run. Wrong: per-test timeout doesn't catch **fixture teardown hangs** (which is what `boot_temporal`'s `manager.teardown()` was doing), and it doesn't catch xdist's **worker-crash-and-replace cycle** which can loop indefinitely retrying failed integration tests.

5. **Never killed zombie `temporal-sdk-python` processes between runs.** They accumulated (18+ at one point, PPID=1 after their parents died). Each holds a port and consumes resources. Compounding contention made each new run slower and more likely to crash, which spawned more zombies.

6. **Two pytest sessions ran concurrently** (mine + a leftover from the user's earlier attempt). I assumed `pkill` of one PID killed the tree; it didn't. Contention multiplied. Should have done a blanket `pkill -9 -f pytest` first.

7. **Wrapped wait loops in `while kill -0 $PID; do sleep 10; done`.** Bounded by pytest's own runtime — i.e., not bounded at all when pytest hangs. No outer wall-clock cap.

8. **When pytest finally produced output, grep'd for "FAILED tests/" but missed the actual error.** The smoking gun (`failure-message="Asynchronous pipeline execution is not enabled..."`) was buried at line ~1490 of a 1497-line log, inside a Temporal server log line — not in a pytest FAILED line. Should have grep'd for the error class name directly from the start.

9. **Trusted xdist output as the source of truth.** Worker crashes ("node down: Not properly terminated") + worker replacement made it impossible to tell whether a failure was a real bug or xdist flakiness. The truth came from running serially.

---

## The right iteration loop

### Before any test run

```bash
pkill -9 -f "pytest" 2>/dev/null
pkill -9 -f "temporal-sdk-python" 2>/dev/null
sleep 1
ps -ef | grep -E "pytest|temporal-sdk" | grep -v grep | wc -l   # must print 0
```

If that doesn't print 0, escalate (one of those processes is hung in uninterruptible I/O — investigate before continuing).

### For first-pass change verification

Run *only the tests directly touched by the change*, serially, with `-x` (stop at first failure) and a short per-test timeout:

```bash
.venv/bin/pytest -x --timeout=30 -v tests/path/to/specific_test.py
```

Fast, fail-loud, no buffering questions. This is what verified the unit-test fix in 0.55s.

### For broader verification

Run unit-only (no integration) with a per-test timeout and direct file redirect (no pipe):

```bash
.venv/bin/pytest --timeout=120 --timeout-method=thread -q \
  -m "not (inference or llm or img_gen or extract or search) and not pipelex_api" \
  tests/unit/ > /tmp/pytest_unit.log 2>&1 &
PID=$!
```

Then either `wait $PID` in a bash backgrounded with `run_in_background: true` so the harness notifies on exit, OR — if Temporal integration tests are in scope — wrap in an outer shell `timeout` so even a fixture-teardown hang gets killed:

```bash
timeout 480 .venv/bin/pytest ... > /tmp/pytest_full.log 2>&1
echo "exit=$?"   # 124 = timeout fired
```

The 5555-test unit suite runs in ~52s serially. So 480s (8 min) is a generous outer bound that lets you see "did it finish" without ambiguity.

### When the run hangs anyway

- **Read the live log** (`tail -50 /tmp/pytest_full.log`) — direct-redirect means progress is visible as it happens. If `-v` was used, you see the last test name that started.
- **Check active processes** — `ps -ef | grep -E "pytest|temporal-sdk"` shows which xdist worker is alive and how long it's been running.
- **Don't poll.** If you've already wrapped in `timeout`, the outer cap will kill it; let the harness notification fire.

### When the run completes with FAILED

Grep for the **error class name**, not the formatted message:

```bash
grep -B 2 -A 10 "AsyncExecutionNotEnabledError\|YourSpecificErrorClass" /tmp/pytest_full.log
```

The formatted message can show up anywhere — including inside Temporal server log lines that aren't pytest FAILED markers. The error class name is greppable, stable, and points straight at the cause.

If the failures look infrastructure-related (worker crashes, "node down", "replacing crashed worker"), **re-run the failing slice serially** with no xdist:

```bash
.venv/bin/pytest --timeout=60 --tb=short -q tests/integration/path/that/failed/
```

If serial passes, the original failure was xdist contention — not your code. If serial fails, it's a real bug, and you now have a clean traceback to read (no xdist obscuring it).

---

## Iteration template (the whole thing in one go)

```bash
# 0. Clean state
pkill -9 -f "pytest" 2>/dev/null
pkill -9 -f "temporal-sdk-python" 2>/dev/null
sleep 1

# 1. Fast verification of the change
.venv/bin/pytest -x --timeout=30 -v tests/unit/path/touched/ 2>&1 | tail -20

# 2. Broad unit verification, direct redirect, outer wall-clock cap
timeout 480 .venv/bin/pytest --timeout=120 --timeout-method=thread -q \
  -m "not (inference or llm or img_gen or extract or search) and not pipelex_api" \
  tests/unit/ > /tmp/pytest_unit.log 2>&1
echo "exit=$?"  # 0=pass, 1=fail, 124=outer timeout

# 3. If any failures, grep by error class name
grep -B 2 -A 10 "YourErrorClass" /tmp/pytest_unit.log

# 4. If integration temporal tests are in scope, run them serially with shorter timeout
timeout 240 .venv/bin/pytest --timeout=60 --timeout-method=thread -q \
  tests/integration/pipelex/temporal/ > /tmp/pytest_temporal.log 2>&1
echo "exit=$?"
```

Total worst-case wall clock: ~13 minutes (30s + 8min + 4min). If anything exceeds that, the outer `timeout` kills it.

---

## Why each tool choice matters

| Choice | Why |
|---|---|
| Direct file redirect (`> file 2>&1`) | No pipe buffering; progress is visible live. |
| `-q` only for final accepted runs, NOT debug runs | `-q` buffers everything until session-end. Use `-v` for debug. |
| `--timeout=N --timeout-method=thread` | Per-test cap. `thread` method works in async contexts where `signal` doesn't. |
| Outer shell `timeout N` | Catches **fixture teardown hangs** and **xdist worker-replace loops** that `--timeout` cannot. |
| `-x` for first-pass debug | Stops at first real failure; gives you a clean traceback fast. |
| Serial (no `-n auto`) for verifying flaky integration tests | xdist worker crashes mask real failures and add runtime via replacement cycles. Serial is honest. |
| `pkill -9 -f temporal-sdk-python` before every run | Zombie test servers compound contention across runs. |
| Grep for error **class name**, not message | Messages get embedded in non-pytest log lines; class names don't. |

---

## When to stop iterating and surface to the user

Bail out and ask for help (don't burn more time) when:

- After clean-state + outer-timeout run, the suite still doesn't terminate within 2× its expected duration.
- After serial re-run of the failing slice, you still can't tell whether the failure is your code or pre-existing flake.
- You've made a code change to fix a test failure and the same test now fails differently — pause and read the new failure carefully before changing more code.
- The error message points at sandbox / determinism / serialization issues you can't reason about from the surface (this is the Temporal sandbox class of bug — the one I hit).

In all four cases, write up what you know in 3–4 sentences and surface to the user. Better than spending another 20 minutes on dead ends.

---

## Codebase-specific notes (Pipelex / Temporal)

- `make agent-test` uses `-n auto -q` — both buffer output and obscure progress. For debug runs, invoke pytest directly with `-v` and direct file redirect.
- `boot_temporal` fixture teardown (in `tests/integration/pipelex/temporal/conftest.py`) is the known fixture-teardown hang point. If a hang traceback mentions `manager.teardown()` or `temporal_hub.reset()`, it's this.
- xdist worker crashes on integration temporal tests often show as `[gw N] node down: Not properly terminated` followed by `replacing crashed worker`. Treat as infrastructure flake until you've proven otherwise serially.
- `is_in_temporal_workflow()` is the right gate for code that might be invoked from inside a Temporal sandbox — `get_config()` is unsafe to read from inside, and many singletons return sandboxed-empty copies. This was the actual bug I hit; it would have been caught instantly by the playbook above if I'd run the integration tests serially on first iteration instead of trusting the xdist run.
