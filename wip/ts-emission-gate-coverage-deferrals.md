# Deferred: two coverage gaps in the TypeScript emission gates

Deferred from the pre-landing review of PR [#1184](https://github.com/Pipelex/pipelex/pull/1184) (2026-09-02). Both are defense-in-depth rather than defects: the gate that decides whether a branch merges runs, and runs correctly.

## The release gate to `main` does not run the emission gates

`.github/workflows/tests-check.yml` grew the `Tests (ts emission gates)` job, and `Tests (all)` requires it. `.github/workflows/tests-full-check.yml` — the gate on PRs targeting `main`, i.e. the release PRs — has only `matrix-test-full` and its aggregator, so the emission gates do not run there.

Left alone because a `dev -> main` release PR carries only commits that already passed the gate on their own PR into `dev`, so the second run would re-prove what the first proved. It becomes worth adding the moment anything can reach `main` without having passed through `tests-check.yml`.

## `AGENTS.md` does not carry the `make test-ts-gates` warning

The warning was added to `pipelex/kit/agent_rules/commands.md`, which `index.toml` merges into `CLAUDE.md`. `AGENTS.md` is built from a different set, headed by `codex_commands.md`, which the change did not touch — `pipelex-dev check-rules` passes, so this is the sets working as declared, not drift.

The gap that leaves: an agent working from `AGENTS.md` and editing `pipelex/codegen/emitters/` is told to verify with `make agent-test`, and is not told that `make agent-test` does not read the emitted TypeScript at all. That is the environment class the three original defects came from.

Left alone because `codex_commands.md` is deliberately the slimmer variant — it already omits the hang-debugging section and the with-prints section — and because a cloud sandbox may have no npm reach, which makes the provisioning half of the instruction useless there. The right shape is probably the warning without the provisioning command: *"`make agent-test` does not cover the TypeScript emission; a change under `pipelex/codegen/emitters/` is verified by the `Tests (ts emission gates)` CI job, not by the suite you can run here."* Worth writing the next time that file is edited for another reason.
