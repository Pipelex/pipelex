# Resume & verify state — orchestrator-agnostic runner effort

Paste-ready orientation for picking up this multi-repo effort in a fresh session. It tells a new agent **what is true**, **how to verify it against the repos** (don't trust this doc over `git`), and **what's next**. Keep it current when the effort's state changes (it's a companion to `TODOS.md`, not a replacement).

The workspace is multi-repo under `/Users/lchoquel/repos/Pipelex/` (`_plugins` is the `pipelex` core worktree).

---

## 1. Read the trackers first (source of truth)

- [`TODOS.md`](../../TODOS.md) — the execution tracker (Phases A–F + a "Follow-on extensions" section). Read the **Status** block, **Follow-on extensions**, and the **Cold-start primer**.
- [`orchestrator-agnostic-runner-and-flavors.md`](orchestrator-agnostic-runner-and-flavors.md) — the decision-locked plan (the *why/how*; locked decisions D1/D2/F1/F2/F3 — don't re-litigate).
- [`execute-per-request-mode-deferred.md`](execute-per-request-mode-deferred.md) — deferred/flagged items from the two follow-ons. **Read before touching `/execute`, `/start`, or the OpenAPI generation.**

## 2. Expected state — verify each, flag any mismatch

```
for r in _plugins pipelex-api pipelex-temporal; do d=/Users/lchoquel/repos/Pipelex/$r; \
  echo "== $r =="; git -C "$d" branch --show-current; git -C "$d" log --oneline -1; \
  git -C "$d" status -sb | head -1; echo "unpushed: $(git -C "$d" log --oneline @{u}..HEAD | wc -l)"; done
```

Expected (the exact tips drift as docs land; the load-bearing checks are *branch*, *clean tree*, *0 unpushed*):

- **`_plugins`** (core, `Pipelex/pipelex`): branch `feature/Orchestrator-dispatched-validate`, clean, 0 unpushed (tip at/after `db4194a98`).
- **`pipelex-api`**: branch `feature/Execute-per-request-mode`, clean, 0 unpushed (tip `191c900`). Stack: `a39841e` (Phase C) → `72c0efc` (validate) → `191c900` (execute).
- **`pipelex-temporal`**: branch `feature/Orchestrator-dispatched-validate`, clean, 0 unpushed (tip `459e04d`).

PR #27 (the `/execute` follow-on) still merge-ready:

```
cd /Users/lchoquel/repos/Pipelex/pipelex-api && \
  gh pr view 27 --json state,mergeable,baseRefName,headRefName && \
  (gh pr checks 27 | grep -viE 'pass|skipping' || echo '(CI all green)')
```

Expected: `OPEN`, `MERGEABLE`, base `feature/Orchestrator-dispatched-validate`, CI all green, 0 open review threads.

Optional gate sanity (proves `pipelex-api` builds against the git-pinned core):

```
cd /Users/lchoquel/repos/Pipelex/pipelex-api && make agent-test   # silent on success
```

## 3. What's DONE

- **Phases A + B + C** — `pipelex-api` is the orchestrator-agnostic base (MAJOR GATE 2 / "THE gate"). Committed + pushed.
- **Follow-on 1** — orchestrator-dispatched `/validate` (reverses/extends F2; new per-call `BundleValidatorRegistry` seam). Done across all 3 repos.
- **Follow-on 2** — per-request `execution_mode` on `/execute` (extends F1). PR #27, merge-ready, **NOT merged** (user merges).

## 4. What's NEXT — confirm go/no-go before starting

**Phase D** = `pipelex-api-hosted` Temporal flavor (MAJOR GATE 3): flavored base image (`FROM pipelex/pipelex-api` + `pipelex-temporal` via `git+ssh`), config migration (`[plugins] boot_orchestrator = "temporal"`, `[api] execution_mode`, connection tree → `temporal_{env}.toml`). See `TODOS.md` → "Phase D" + its checkpoint. **This is where outward-facing / deploy-breaking work begins — confirm with the user before any actual deploy.**

## 5. Open threads to keep in mind (not blocking)

- PR #27 and the validate branch are **stacked and unmerged to `dev`**; merging is the user's call.
- `pipelex-api`'s `pipelex` dep is pinned to a **core git SHA** (`51ff09417`) so CI resolves (the editable `../_plugins` path can't resolve on a CI runner). Both the SHA pin and the validate-branch stacking flip to PyPI `==` pins **at release**.
- A pre-existing **`/start` DIRECT-path resource leak** is flagged (deferred) in `execute-per-request-mode-deferred.md` — fix it on its own surface, not as part of Phase D.

---

**On resume:** run §2, then give a one-paragraph status confirmation (or a list of mismatches), and wait for the user to pick the next task.
