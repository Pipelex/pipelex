---
status: draft
item: L-260919-9965d0
---

# Judgment family — implementation plan

The design is `design.md` beside this file. This plan builds it from the bottom up, and each phase must prove itself before the next one starts: a spike that calls the real API, then the cogt family with live tests, then the operator. The first two phases depend on nothing the design leaves open; the third does, and its gate says so.

**Conventions for every phase.** Tests are written before the code they cover. `make agent-check` runs after every code change, with changes staged first so the drift digest sees them, and `make agent-test` closes the phase. A phase's branch gets a `/rev` pass before its pull request opens, and the pull request targets `dev`. Each phase after the first has its own worktree, made with `wt add --for <item>` and claimed from inside.

**A trap already met.** `TYPESAFE_API_KEY` lives in the gitignored `.env`, which `wt add` copies into a worktree when it is made. `wt provision` does not overwrite a `.env` that already exists, so a worktree made before a key was added to the main checkout's `.env` needs the file copied by hand. Check with `grep -c '^TYPESAFE_API_KEY=' .env` before concluding that the API refuses the key.

## Phase 1 — Spike the async API

Item: L-260919-3aeab8, "Spike TypeSafe's async API and record what the judgment worker can rely on". Worktree: the epic's own, `_pipelex--judgment-family`, which also carries the campaign documents.

Everything the design says about the backend was read from its documentation. The spike replaces reading with observation, and its output is a findings note that phase 2 codes against. It is throwaway code: no `pipelex` imports, no abstractions, no tests.

- [x] Write `wip/judgment-family/spike/typesafe_async_spike.py` — and, for the questions its first run raised, `typesafe_followups_spike.py` beside it — run with `uv run --no-project --with typesafe-sdk --env-file .env python wip/judgment-family/spike/typesafe_async_spike.py`, so the dependency does not enter `pyproject.toml` while the question is still open. The script prints each finding and saves every raw response as JSON under `wip/judgment-family/spike/responses/`, with the key and any request header stripped; phase 2's unit tests replay these files.
- [x] **Shapes.** One request with a yes/no, a choice and a rating question over one named-object state, through `AsyncTypeSafeClient.system_one`. Record the exact answer fields and their types, in particular the key types of `probabilities` for a rating (the SDK reference says integers, the HTTP examples show strings), whether `legend` is always present, and whether the response names a versioned model id when the request names an alias.
- [x] **Usage.** Whether `input_tokens` and `output_tokens` are always reported, and whether they are per request or per question. The cost report depends on it.
- [x] **State value types.** The documentation says state holds text. Send a state containing a JSON number, a boolean, a nested object and an array, and record what is accepted and what changes the answers. The design maps a `Number` input to a JSON number and a `YesNo` to a boolean; if the API rejects or ignores them, the kernel's state builder renders them as text instead, and the design is corrected.
- [x] **Criteria edge cases.** An option with a null description, a yes/no question with and without criteria, the smallest legal option set and scale, and one request beyond the documented limits to see the refusal.
- [x] **Model pinning.** That the versioned id from the models page is accepted as `model`, since the deck will point at it and never at an alias.
- [x] **Errors.** A wrong key, a malformed question, an oversized state, and a very short timeout. Record the exception class, the status, the body and whether a `request_id` is present for each — this is what the worker's error classification is written from.
- [x] **Retries.** What the SDK retries by default, and that passing an explicit `RetryPolicy` can turn it off, so retry behaviour can be a Pipelex decision.
- [x] **Concurrency.** A batch of requests through `asyncio.gather` on one client: that one client is safe to share (the worker caches it in the `SdkClientRegistry`), the latency of one request, and the latency and token count of several questions in one request against the same questions sent separately.
- [x] **Stability.** The same request repeated several times: how much the probabilities move. This sets how wide the margins in the live tests must be.
- [x] **The same call without the SDK.** One request with the `httpx` already in the core, to measure what the SDK actually buys.
- [x] **The dependency in this repo.** On the branch, `uv add --optional typesafe typesafe-sdk`, then `make agent-check` and `make agent-test`. Record what the lock moved (the SDK's pydantic floor is above the core's), whether `httpx2` coexists with `httpx`, and whether `mypy` or `pyright` changed their reading of any unrelated import, which a new typed dependency has done in this repo before. Keep the change if the verdict is to use the SDK, and revert it otherwise.
- [x] Write `wip/judgment-family/spike-findings.md`: one section per question above with what was observed, then the verdict.

### Checkpoint 1 — reached

The full record is `spike-findings.md` beside this file; what the rest of the campaign has to obey is here.

**Go.** The API does what the design needs: the three question types map cleanly onto the three verdict shapes, every answer carries its uncertainty, one client served forty concurrent requests without a failure, and the model is stable enough to assert against live.

**The SDK, behind a `typesafe` optional extra**, which closes the design's open question on the vendor dependency. It supplies typed exception classes carrying `status`, `body`, `endpoint` and `request_id` — the whole input to the worker's error classification — and coerces a rating answer's string keys to integers; a bare `httpx` worker would rebuild both. `uv add --optional typesafe "typesafe-sdk>=0.7.0"` added five packages and moved nothing else in the lock, and `make agent-check` and `make agent-test` both passed in full, so the specific fear the phase opened with — a new typed dependency changing `mypy` or `pyright` on an unrelated import — did not materialise.

**Where the observed API differed from the design**, all corrected in `design.md` in this same change:

- Every validation failure returns `400`, not the documented `422`, and one status covers an illegal question, an unknown model and an oversized state. The error body has two shapes, a bare-string `detail` and an object `detail` carrying `error_type`, and the worker must branch on `error_type` where it is present. This is the correction that most changes phase 2's work.
- The SDK raises a bare `TypeSafeError`, with no status and no request id, for what it validates before sending. That is a second failure class, and a Pipelex defect rather than a vendor failure.
- A rating is capped at ten levels — a blueprint rule the design did not know it needed. The vendor's own minimum is one option and one level, so Part 1's two-member minimum is this language's rule and not the vendor's.
- An unknown yes/no criteria key is accepted and silently ignored, so only our validation catches a typo.
- `GET /v1/models` lists only the two aliases. `jev-1.13.0` is requestable and both aliases resolve to it, but a newer versioned id is found on the vendor's models page, never through the API.
- A rating answer's `probabilities` and `legend` are keyed by strings on the wire and by integers only after the SDK parses them. The replay fixtures hold the wire form.
- `usage` is per request, never per question, and output tokens are free — the cost report prices them at zero.
- An array state degrades answers badly; the kernel's state builder always sends an object, with numbers as JSON numbers and yes/no values as JSON booleans, which the design already intended.

**The margin the live tests must use.** Probabilities come back quantised to two decimals. An unambiguous case was bit-identical across eight repeats; a deliberately borderline one moved 0.01 across ten, with a standard deviation of 0.003. So live tests assert verdicts exactly — the chosen option, the side of the threshold, the rating level — and give a probability a margin of **±0.05**. What actually moves an answer is the question's wording: rewording one instruction moved the same case from 0.11 to 0.30, so live tests pin their exact instruction strings, and a failure after a wording edit is telling the truth.

**Two things for phase 2 to carry.** The three-questions-in-one-request saving is real — 506 input tokens against 1138, and 0.27 s against 0.66 s — so decision 6's batch-shaped contract earns itself. And ruff runs over `.` with `select = ["ALL"]`, so scratch scripts under `wip/` are linted like product code; the spike scripts carry a file-level ignore for the namespace-package rule and were otherwise written to pass.

Land the campaign documents and the spike through a pull request from this branch (`Closes` the spike item, `Advances` the epic), so that the next phase's worktree, cut from `dev`, has them.

## Phase 2 — The family at the cogt level, with live tests

Item: L-260919-502f36, "Serve judgment questions through a cogt worker family, with live tests under a test profile". Blocked by the spike. Design parts 3, 4 (the leaf and the dry run) and 5. No operator, no kernel entry point, no native concept: the family's answers are its own models, so nothing here waits on the standard.

The phase is done when `make ti PROF=typesafe TEST=judgment` runs the live tests green against the real API, and the same tests skip cleanly under a profile that lists no judgment model.

- [ ] **Family identity.** `JUDGMENT` in `InferenceFamily`, `ModelType` and `InferenceErrorFamily`, with the failure and not-found class tables; `JudgmentJobFailureError`, `JudgmentModelNotFoundError` and `JudgmentHandleNotFoundError` in `pipelex/cogt/exceptions.py`; `JobCategory.JUDGMENT_JOB`, `UnitJobId.JUDGMENT_ANSWER` and its display arm. Follow the type checker through every exhaustive match it flags.
- [ ] **The package** `pipelex/cogt/judgment/`: question and answer models (the `YesNoAnswer` at-least-one validator included), setting and model choice, usage and cost report, job, job factory, worker contract, worker factory. Unit tests drive the worker's template method through a fake worker: the answers' keys must equal the questions' keys, each answer's kind must match its question's, and reporting happens in `finally` on success and on failure. Mutation-test each guard by breaking it and watching the test go red.
- [ ] **Deck.** `JudgmentDeckBlueprint`, the flat fields on `ModelDeck`, `get_judgment_setting`, `validate_judgment_presets`, `check_judgment_choice_with_deck`, the suggestion arms, the model manager's handle collection and flattening, and `pipelex/kit/configs/inference/deck/5_judgment_deck.toml` with the default alias on a versioned handle.
- [ ] **Reporting and cost.** `JudgmentTokensUsage` and its report in both unions, the `ReportingManager` dispatch arm, and in `CostRegistry.compute_cost_report` a judgment arm, an explicit extract arm, and `assert_never` to close. Real token counts, priced per million like an LLM; update the `model_type` comment on `ModelUsageSpec`.
- [ ] **The leaf.** `JudgmentAssignment`, `pipelex/cogt/content_generation/judgment_generate.py` with the dry branch first, `dry_judgment_gen_answers` (deterministic, uncertainty absent), and `make_judgment_answers` on the protocol and the generator. A unit test pins the dry branch.
- [ ] **The backend.** `pipelex/providers/typesafe/`: plugin, worker, translation both ways, exceptions and error classification, written against the spike's findings and unit-tested by replaying its recorded responses. The plugin joins `KERNEL_BUILTIN_PLUGINS`; the client is cached through the `SdkClientRegistry`; retry and timeout are passed explicitly. Backend record in `backends.toml`, `backends/typesafe.toml`, a routing profile, and the `.pipelex/inference/` mirror with its kit manifest. Check that a boot with the backend enabled and the key unset behaves as it does for Linkup, and add the arm to the keyless boot test.
- [ ] **Plugin surface tests.** The expected-backends table in `tests/unit/pipelex/plugins/test_inference_backend_coverage.py`, and a missing-extra guard test mirroring Linkup's.
- [ ] **Model listing.** `ModelCategory.JUDGMENT` in `pipelex/builder/operations/models_ops.py` with its arms, so `pipelex-agent models` and `check-model` know the family.
- [ ] **Test infrastructure.** The `judgment` marker and its term in the default deselect expression in `pyproject.toml`; every family table in `preprocess_test_models_cmd.py`; a `[collections.judgment]` and a `judgment_models` key on every profile in `.pipelex-dev/test_profiles.toml`, empty everywhere except a new `[profiles.typesafe]` whose `backends` is `["typesafe"]`; `get_judgment_combos` with its skip, the `judgment_combo` fixture and its re-export; regenerate `_generated_model_sets.py`.
- [ ] **Live tests**, marked `inference` and `judgment`, in `tests/integration/pipelex/cogt/test_judgment.py` and `config_coverage/test_cc_judgment.py`: each question kind on an unambiguous case, several questions in one job, usage tokens present, a versioned model id reported, and an error case (an unknown model handle). Assertions are on verdicts and on wide margins set by checkpoint 1, never on an exact probability.
- [ ] **Docs.** `docs/under-the-hood/inference-backend-plugins.md` (the family comment, the "serves all four" sentence, the worker-contract table), the distributed content generation, dry-run and per-node usage pages, a new `docs/contribute/inference-family-surface.md` listing every site a family touches, and its `mkdocs.yml` entry. Regenerate the error pages and the identity snapshot (`make gep`, `make gei`). Changelog entry.
- [ ] `make agent-check`, resolving any drift contract it opens; `make agent-test`; `make ti PROF=typesafe TEST=judgment`; then `make rtm` to put the generated model sets back on the default profile before committing, since the `PROF=` run rewrites that tracked file.

### Checkpoint 2

Record here: what the live tests cover and the command that ran them; any contract change against the design, with the design corrected; the measured cost of a test run. File the follow-up for `pipelex-server/temporal/` (an activity and a queue for the new leaf), which can be written as soon as the leaf exists. Confirm the gate below before starting phase 3.

## Phase 3 — `PipeJudge`

Item: L-260919-406599, "Run judgments from a bundle with the PipeJudge operator". Blocked by phase 2 and by L-260919-178ad6, the standard change in `mthds`. Design parts 1, 2, 4 and 7.

**Gate.** Two things must be true first. The design is ratified — the native names, how much optional surface to pin, and `question` against `prompt` are its open questions — and its `status` is `active`. And the standard change has merged in `mthds` and the sibling `mthds/` checkout has been refreshed: `tests/unit/pipelex/core/concepts/test_pinned_natives_vs_standard.py` reads the spec page from that checkout, so the engine's natives cannot go green before the page moves.

- [ ] **Natives in the engine.** `NativeConceptCode` members and every exhaustive match over them, `ChoiceContent` and `RatingContent` with their renderers, the optional `probability` on `YesNoContent` (strict, like `yes_no`), the pinned blueprints and `PINNED_NATIVES_MTHDS_VERSION`, the concept factory, `CoreRegistryModels.STUFF`, the input shaper and the out-of-matrix set as the standard decided, codegen's native expansion, and `docs/building-methods/concepts/native-concepts.md`. Run `make test-ts-gates` if an emitter moved, and `trace-input-semantics` since the structure side changed. If this step alone makes a reviewable diff, land it as its own pull request under the same item.
- [ ] **Kernel.** `pipelex/kernel/judgment_ops.py` (`resolve_judgment_setting`, `run_judgment`) and `judgment_results.py`: render the question, build the state from the inputs by name as checkpoint 1 settled it, send a batch of one, apply the threshold, warn when a threshold has no probability to apply to, build the native content, store it. Tests cover state building per content kind and the threshold at and around its boundary. Add the arm to `tests/unit/pipelex/kernel/test_kernel_boot_contract.py` and the row to `docs/under-the-hood/pipelex-kernel.md`, and acknowledge the `pipelex-kernel-docs` drift contract.
- [ ] **Operator.** `pipelex/pipe_operators/judge/`: blueprint with kind resolution and its error messages, pipe, factory with the output agreement (refinements admitted), exceptions, execution data for the trace. Then the registration surface from `docs/contribute/registration-surface.md`: `PipeType.PIPE_JUDGE` and its category arm, `PipeBlueprintUnion`, `registry_models.py`, the output renderer's match. Regenerate the schema (`make gms`).
- [ ] **Builder.** `PipeJudgeSpec`, the spec map and the spec union, the TOML emission branch in `pipe_ops.py` and its twin in the agent CLI's `pipe_cmd.py`, with their tests; `pipelex/builder/CLAUDE.md`, adding the missing `PipeStructure` while there.
- [ ] **Corpus and end to end.** The `[operator.judge]` vocabulary entry and the urgent-message scenario re-cut with `PipeJudge` as a new corpus entry, leaving `native_yes_no_urgent_message` as it is; an e2e bundle under `tests/e2e/pipelex/pipes/pipe_operators/pipe_judge/` covering the question kinds, a threshold, and a `Choice` driving a `PipeCondition`; the error-report parity fixture beside search's in `pipelex/test_extras/error_report_parity.py`; a dry-run test.
- [ ] **Docs.** `docs/building-methods/pipes/pipe-operators/PipeJudge.md` carrying the authoring guidance from the design's part 4, a feature page, the operator round-ups, `mkdocs.yml`. Regenerate the error pages and the identity snapshot. Changelog entry.
- [ ] `make agent-check`, `make agent-test`, `make ti PROF=typesafe TEST=judge`, `make rtm`.

### Checkpoint 3

Record here: the version `pipelex` shipped the operator in, and the follow-ups filed for what waits on that release — the schema copies (`mthds-schema-sync`), the corpus (`mthds-corpus-sync`), the projection corpus in `mthds-js` and `mthds-python`, a node rendering in `mthds-ui`, the operator lists the authoring skills teach from in `pipelex-plugins` and `mthds-plugins`, and the decision on serving the family from the hosted plane.
