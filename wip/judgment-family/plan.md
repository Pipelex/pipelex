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
- A rating is capped at ten levels, probed at the boundary: ten accepted, eleven refused. It is the vendor's limit and not the language's, so by the design's own rule in Part 5 the **worker** enforces it and the blueprint does not — an eleven-level method stays legal MTHDS that this backend refuses. The vendor's own minimum is one option and one level, so Part 1's two-member minimum is this language's rule, and that one is the blueprint's.
- An unknown yes/no criteria key is accepted and silently ignored, so only our validation catches a typo.
- `GET /v1/models` lists only the two aliases. `jev-1.13.0` is requestable and both aliases resolve to it, but a newer versioned id is found on the vendor's models page, never through the API.
- A rating answer's `probabilities` and `legend` are keyed by strings on the wire and by integers only after the SDK parses them. The replay fixtures hold the wire form.
- `usage` is per request, never per question, and output tokens are free — the cost report prices them at zero. One state asked 1, 5, 20 and 50 questions cost 323/22, 387/94, 637/364 and 1147/904 input/output tokens.
- On a *response*, `request_id` and `raw_http_response` are properties that **raise `TypeSafeError`** rather than returning `None`; on a `TypeSafeAPIError` the same attribute is `str | None` and safe to read plainly. The worker therefore needs two different accessors for the success and error paths.
- An array state degrades answers badly; the kernel's state builder always sends an object, with numbers as JSON numbers and yes/no values as JSON booleans, which the design already intended.

**The margin the live tests must use.** Probabilities come back quantised to two decimals. An unambiguous case was bit-identical across eight repeats; a deliberately borderline one moved 0.01 across ten, with a standard deviation of 0.003. So live tests assert verdicts exactly — the chosen option, the side of the threshold, the rating level — and give a probability a margin of **±0.05**. What actually moves an answer is the question's wording: rewording one instruction moved the same case from 0.11 to 0.30, so live tests pin their exact instruction strings, and a failure after a wording edit is telling the truth.

**The `typesafe` extra ships now, and the repo does not release until the integration is real.** The extra is published by `pyproject.toml` while nothing under `pipelex/` imports `typesafe-sdk`, so a release cut before phase 2 would put `pipelex[typesafe]` on PyPI installing an SDK that does nothing. The decision is to keep the extra and write no changelog entry for it, on the condition that **no release goes out until the TypeSafe integration is actually in** — phase 2's changelog entry is the one that announces both. Anyone cutting a release before then must revert the extra first.

**Two things for phase 2 to carry.** The three-questions-in-one-request saving is real — 506 input tokens against 1138, and 0.27 s against 0.66 s — so decision 6's batch-shaped contract earns itself. And ruff runs over `.` with `select = ["ALL"]`, so scratch scripts under `wip/` are linted like product code; the spike scripts carry a file-level ignore for the namespace-package rule and were otherwise written to pass.

Land the campaign documents and the spike through a pull request from this branch (`Closes` the spike item, `Advances` the epic), so that the next phase's worktree, cut from `dev`, has them.

## Phase 2 — The family at the cogt level, with live tests

Item: L-260919-502f36, "Serve judgment questions through a cogt worker family, with live tests under a test profile". Design parts 3, 4 (the leaf and the dry run) and 5. No operator, no kernel entry point, no native concept: the family's answers are its own models, so nothing here waits on the standard.

The phase is done when `make ti PROF=typesafe TEST=judgment` runs the live tests green against the real API, and the same tests skip cleanly under a profile that lists no judgment model.

**The phase lands as two pull requests, and the first does not mention the vendor.** The design says the family is testable with a fake worker before any vendor code exists, and that is worth taking literally: bundling the two makes one diff where a reviewer cannot separate "is the family wired in correctly" from "did we read TypeSafe right", and the first half alone walks the type checker through a dozen exhaustive matches.

- **2a, the family.** Family identity, the package, the deck, reporting and cost, the leaf, model listing, and the test infrastructure with an empty `judgment_models` on every profile. Its proof is unit tests through a fake worker, plus `make agent-check` and `make agent-test`; no live call happens in it, and no `typesafe` name appears outside `pyproject.toml`'s already-landed extra.
- **2b, the backend.** `pipelex/providers/typesafe/`, the plugin surface tests, the `[profiles.typesafe]` arm, the live tests, and the docs for both halves. Its proof is `make ti PROF=typesafe TEST=judgment`.

Both carry the same item; 2a is `Advances` and 2b is `Closes`. Whether 2b stacks on 2a or waits for its merge is the call of whoever starts, and stacking is the reason both are named here rather than filed as separate items.

**Where the spike's findings bite.** The backend bullet says "written against the spike's findings", and these are the four the worker cannot be written without — the rest are in `spike-findings.md`.

- **Error classification branches on the body, not the status.** Every validation failure is a `400`, so the status alone cannot separate three unrelated causes. The mapping: `401` → credentials; `400` with `error_type: "authentication_error"` → credentials; `400` with `"max_tokens_exceeded"` → content; `400` with `"api_usage_error"` naming an unknown model → configuration; `400` whose `detail` is a bare string (the question-shape errors) → a Pipelex defect, since blueprint validation should have caught it; `429` and `529` → transient. A bare `TypeSafeError`, raised client-side before any call, is always a Pipelex defect.
- **Two accessors for one request id.** On a response, `request_id` and `raw_http_response` are properties that **raise `TypeSafeError`** when the header was absent rather than returning `None`; on a `TypeSafeAPIError` the same attribute is `str | None` and reads plainly. The success path needs a guarded read and the error path does not.
- **The rating answer's keys change type across three layers**, and each conversion is somebody's job: strings on the wire, integers after the SDK parses, `dict[int, float]` on `RatingAnswer` per part 3 — and then text keys again on the `Rating` native per part 2, because the language's dict keys are text. The worker owns the first hop and the kernel the last; phase 3 inherits the last one.
- **The deck's versioned handle is `jev-1.13.0`**, and `GET /v1/models` will not confirm it: the endpoint lists only `jev-latest` and `jev-preview`. The deck TOML carries a comment saying a newer id is found on the vendor's models page, so the next person does not go looking for an API that has it.

- [x] **Family identity.** `JUDGMENT` in `InferenceFamily`, `ModelType` and `InferenceErrorFamily`, with the failure and not-found class tables; `JudgmentJobFailureError`, `JudgmentModelNotFoundError` and `JudgmentHandleNotFoundError` in `pipelex/cogt/exceptions.py`; `JobCategory.JUDGMENT_JOB`, `UnitJobId.JUDGMENT_ANSWER` and its display arm. Follow the type checker through every exhaustive match it flags.
- [x] **The package** `pipelex/cogt/judgment/`: question and answer models (the `YesNoAnswer` at-least-one validator included), setting and model choice, usage and cost report, job, job factory, worker contract, worker factory. Unit tests drive the worker's template method through a fake worker: the answers' keys must equal the questions' keys, each answer's kind must match its question's, and reporting happens in `finally` on success and on failure. Mutation-test each guard by breaking it and watching the test go red.
- [x] **Deck.** `JudgmentDeckBlueprint`, the flat fields on `ModelDeck`, `get_judgment_setting`, `validate_judgment_presets`, `check_judgment_choice_with_deck`, the suggestion arms, the model manager's handle collection and flattening, and `pipelex/kit/configs/inference/deck/5_judgment_deck.toml` with the default alias on a versioned handle.
- [x] **Reporting and cost.** `JudgmentTokensUsage` and its report in both unions, the `ReportingManager` dispatch arm, and in `CostRegistry.compute_cost_report` a judgment arm, an explicit extract arm, and `assert_never` to close. Real token counts, priced per million like an LLM; update the `model_type` comment on `ModelUsageSpec`.
- [x] **The leaf.** `JudgmentAssignment`, `pipelex/cogt/content_generation/judgment_generate.py` with the dry branch first, `dry_judgment_gen_answers` (deterministic, uncertainty absent), and `make_judgment_answers` on the protocol and the generator. A unit test pins the dry branch.
- [x] **The backend.** `pipelex/providers/typesafe/`: plugin, worker, translation both ways, exceptions and error classification, written against the four findings above and unit-tested by replaying the recorded responses in `spike/responses/` — the successes are wire bodies and the refusals are `describe_exception` envelopes with the wire body under `body`, which is what the classification tests read. The vendor's ten-level cap and its option-count limits are enforced in this translation, not in the blueprint. The plugin joins `KERNEL_BUILTIN_PLUGINS`; the client is cached through the `SdkClientRegistry`; retry and timeout are passed explicitly. Backend record in `backends.toml`, `backends/typesafe.toml`, a routing profile, and the `.pipelex/inference/` mirror with its kit manifest. Check that a boot with the backend enabled and the key unset behaves as it does for Linkup, and add the arm to the keyless boot test.
- [x] **Plugin surface tests.** The expected-backends table in `tests/unit/pipelex/plugins/test_inference_backend_coverage.py`, and a missing-extra guard test mirroring Linkup's.
- [x] **Model listing.** `ModelCategory.JUDGMENT` in `pipelex/builder/operations/models_ops.py` with its arms, so `pipelex-agent models` and `check-model` know the family.
- [x] **Test infrastructure.** The `judgment` marker and its term in the default deselect expression in `pyproject.toml`; every family table in `preprocess_test_models_cmd.py`; a `[collections.judgment]` and a `judgment_models` key on every profile in `.pipelex-dev/test_profiles.toml`, empty everywhere except a new `[profiles.typesafe]` whose `backends` is `["typesafe"]`; `get_judgment_combos` with its skip, the `judgment_combo` fixture and its re-export; regenerate `_generated_model_sets.py`.
- [x] **Live tests**, marked `inference` and `judgment`, in `tests/integration/pipelex/cogt/test_judgment.py` and `config_coverage/test_cc_judgment.py`: each question kind on an unambiguous case, several questions in one job, usage tokens present, a versioned model id reported, and an error case (an unknown model handle). Verdicts are asserted exactly and probabilities within ±0.05, per checkpoint 1; the exact instruction strings are pinned, since rewording moved one case from 0.11 to 0.30 while repetition moved it 0.01.
- [x] **Docs.** `docs/under-the-hood/inference-backend-plugins.md` (the family comment, the "serves all four" sentence, the worker-contract table), the distributed content generation, dry-run and per-node usage pages, a new `docs/contribute/inference-family-surface.md` listing every site a family touches, and its `mkdocs.yml` entry. Regenerate the error pages and the identity snapshot (`make gep`, `make gei`). Changelog entry.
- [ ] `make agent-check`, resolving any drift contract it opens; `make agent-test`; `make ti PROF=typesafe TEST=judgment`; then `make rtm` to put the generated model sets back on the default profile before committing, since the `PROF=` run rewrites that tracked file.

### What 2a changed against the design

Two things, both recorded in `design.md` in the same change.

**The judgment deck has no `choice_default`, and the blueprint makes it optional.** Shipping one broke every boot: `ModelManager._enforce_gateway_model_membership` walks every handle a deck's presets and choice defaults name, the default routing profile sends an unmatched handle to the Pipelex Gateway, and the gateway does not serve Jev — so `GatewayUnknownModelError` fired in `tests/unit/pipelex/test_hub_lifecycle.py` before any judgment was ever asked for. `JudgmentDeckBlueprint.choice_default` is therefore `JudgmentModelChoice | None = None`, alone among the families. **This is phase 3's to carry**: `@default-judgment` cannot be `PipeJudge`'s default until the hosted plane serves the family, so the operator must require an explicit model, and the design's "hosted serving" open question now has a consequence attached to it.

**`CostRegistry.compute_cost_report` became a `match` rather than an `if`-chain.** With an explicit extract arm the trailing `isinstance` was provably true, which pyright refuses as `reportUnnecessaryIsInstance`, so the dispatch is a match over the usage classes closed by `case _: assert_never(...)`. The guarantee the design asked for is unchanged and now has a runtime test beside the static one (`test_every_family_gets_its_own_cost_report`).

**The MTHDS protocol has no word for the family, and `PipelexMTHDSProtocol.models()` would have raised on it.** `mthds.protocol.models.ModelCategory` carries `llm`, `extract`, `img_gen` and `search`; the runner builds one `ModelInfo` per preset and types it by calling that enum on our own category key, so the first judgment preset in a deck turns `models()` into a `ValueError` for every caller, not just for judgment. The runner now skips a category the protocol cannot name, leaving the judgment aliases and waterfalls on the string-keyed routing extensions, and L-260919-afb6c0 asks `mthds` for the member. Nothing is broken today only because the kit deck ships no judgment preset. 2b was expected to make it live and did not: it ships an alias and no preset (see checkpoint 2), so the gap stays dormant until a deck gains a judgment preset.

**One pre-existing test was loosened, and it is worth knowing why.** `test_parity_with_aggregate_run_total` compared two float sums for bit-for-bit equality; they are the same per-record costs added in different orders, and a fifth record made the last bit diverge. It now compares to within `1e-12`, which is still many orders of magnitude tighter than any real drift between the two cost paths.

### Checkpoint 2a — the family, handed off

**Where the work is.** Worktree `_pipelex--judgment-cogt-family`, branch `feature/Judgment-cogt-family`, which is **stacked on `feature/Judgment-family`** (phase 1, open as PR #1214). Its first three commits are phase 1's; everything after them is 2a. The pull request for 2a therefore targets `feature/Judgment-family`, not `dev`, until phase 1 merges — per the workspace's stacked-PR rule — and its body carries `Advances L-260919-502f36`, because 2b is what closes the item.

**What is done.** Every box in the 2a half of the list above, and nothing from 2b. Concretely: the family enums and their failure/not-found tables, `pipelex/cogt/judgment/` entire, the deck (blueprint, flat fields, `get_judgment_setting`, `validate_judgment_presets`, `check_judgment_choice_with_deck`, the ambiguity warner, the model manager's collection and flattening, `5_judgment_deck.toml` and its `.pipelex/` mirror), reporting and cost, the leaf with its dry branch and its protocol method, `ModelCategory.JUDGMENT`, and the test infrastructure. `make agent-check` passes, including the `cli-docs` drift contract, which this change opened and which is acked. No `typesafe` name appears anywhere outside `pyproject.toml`'s already-landed extra.

**What is left, and it is all 2b**: `pipelex/providers/typesafe/` with its worker, translation and error classification written against the four findings above; the backend records and the `.pipelex/inference/` mirror; the plugin surface tests; the `[profiles.typesafe]` arm and a `[collections.judgment]` naming `jev-1.13.0` (deliberately removed from 2a, since it names the vendor); the live tests; and the docs for both halves, including the new `docs/contribute/inference-family-surface.md`. The changelog entry under `## [Unreleased]` describes 2a's family and is 2b's to extend with the backend rather than to duplicate.

**The commands a cold session needs**, all from the worktree root:

- `make agent-check` after every code change, with changes staged first so the drift digest sees them.
- `make agent-test` to close, or `.venv/bin/pytest tests/unit/pipelex/cogt/judgment/ tests/unit/pipelex/cogt/content_generation/test_judgment_generate_dry_branch.py tests/unit/pipelex/cogt/models/ tests/unit/pipelex/cogt/usage/ -q` for the fast loop over what 2a touched.
- `make rtm` after any `make ti PROF=…` run. In this repo `tests/integration/pipelex/fixtures/_generated_model_sets.py` is **gitignored**, so the plan's warning about it being a tracked file does not apply here — running `rtm` is still right for local consistency.
- ⚠ `make agent-check` runs the keyword-only auto-fixer, and it **silently rewrote four of this phase's signatures** before their grants existed: `get_judgment_setting`, `_warn_if_ambiguous_judgment` and both `JudgmentTokenCostReportField.report_field_for_*` staticmethods. Record the grant with `make sgr FUNC=… RATIONALE=…` *before* running the check, and do not put backticks in a rationale.

**Open questions, none blocking 2b's code.** The design's own list still stands unratified (the standard's native names, how much optional surface to pin, `question` against `prompt`, hosted serving), and phase 3's gate waits on it. What 2a added to that list is the consequence recorded above: with no `choice_default`, `PipeJudge` cannot default a model, so "hosted serving" is now a question with a user-visible cost attached rather than a purely internal one.

### Checkpoint 2 — reached

**Where the work is.** 2b is on `feature/Typesafe-backend` in worktree `_pipelex--typesafe-backend`, stacked on 2a's `feature/Judgment-cogt-family`, which is itself stacked on phase 1's `feature/Judgment-family` (PR #1214). Each pull request targets the branch below it until that one merges. 2a's branch gained one commit after checkpoint 2a, because the full suite had never finished on it and was red: a fake model deck missing the family's fields, and three generated artefacts (the error identity snapshot, the error pages, the inference-backend migration golden) that had not been regenerated. Nine end-to-end failures in the same run were the machine's global deck predating the judgment section, not the code.

**What the live tests cover and how they ran.** `make ti PROF=typesafe TEST=judgment` ran six tests green against the live API: each question kind alone on the unambiguous case, the three kinds in one request (usage recorded, the pinned model on the report), an unknown model id rendered as `JudgmentModelNotFoundError` with its request id, and the config-coverage call. Under the default profile, which lists no judgment model, the same six skip with "No judgment combos in test profile". The wording and the state are the spike's own, pinned, and a yes/no probability is held to ±0.05 of the recorded 0.98.

**What a run costs.** The five requests that reach the model read 1,998 input tokens and wrote 186 output tokens, which at $0.042 per million input tokens and free output is **$0.00008 per run**. Cost is not a reason to keep these tests thin.

**Contract changes against the design**, all recorded in `design.md` Part 5:

- **The managed routing profiles carry an optional route, `"jev-*" = "typesafe"`.** Without it a user holding a TypeSafe key still could not reach the model under the default profile: every handle routes to the gateway by default, and one the gateway does not serve is dropped from the deck without a word. The kit deck carries `@default-judgment` and still no preset.
- **Classification lives in the provider package** and branches on the body's code before handing the rest to the shared classifier, which stays free of vendor names.
- **The worker warns when the API names a model other than the pinned one**, the one way the pin could fail silently.

**Sites no plan named, found on the way**, now all listed in `docs/contribute/inference-family-surface.md`: the CI placeholder list in `pipelex/test_extras/shared_pytest_plugins.py`, whose omission would have failed the boot of every CI shard (now guarded by `tests/unit/pipelex/test_extras/test_ci_placeholder_keys.py`); the SDK in the import-light boot guard's blocked list; and `.env.example`. A pre-existing bug was fixed on the way: `RoutingProfile.get_backend_match_for_model` merged the enabled optional routes into the profile's declared `routes` in place, harmless until now only because each match re-checks enablement, and this is the kit's first real use of optional routes.

**A replay trap for the next backend.** The SDK coerces a rating's string-keyed `probabilities` to integers only when it parses JSON text; validating the decoded dict refuses every rating. The unit tests replay the recorded wire bodies with `model_validate_json` for that reason, and the fixtures they read are copied into `tests/data/typesafe/responses/` so they outlive this campaign directory.

**What waits elsewhere.** The Temporal activity and queue for the leaf are L-260919-9da413, owned by `pipelex-server/temporal`; the protocol's missing `judgment` model category is L-260919-afb6c0 in `mthds`, which a judgment *preset* would make live — the kit ships none.

**What is left of phase 2, for a session starting cold.** Everything is committed on `feature/Typesafe-backend`; `make agent-check` passed on the committed tree. The full `make agent-test` was started on it and had not finished when the session ended — **rerun it first**, from the worktree root, writing to a file rather than piping to `tail` (a pipe masks the exit code): `make agent-test > /tmp/at.log 2>&1; echo EXIT=$?`. Then:

- Tick the last phase 2 box above once `make agent-test` is green. `make ti PROF=typesafe TEST=judgment` and `make rtm` already ran green in this session, with the six live tests passing and the same six skipping under the default profile.
- Run `/rev` on each branch before its pull request opens — 2a's `feature/Judgment-cogt-family` against `feature/Judgment-family`, and 2b's `feature/Typesafe-backend` against `feature/Judgment-cogt-family`. Neither has a recorded review pass.
- Open the two pull requests, each targeting the branch below it: 2a with `Advances L-260919-502f36`, 2b with `Closes L-260919-502f36`. Phase 1 (PR #1214) merges first.
- Decide whether `[typesafe]` ships enabled. It ships enabled, like Linkup, which was verified to behave identically: a live boot without `TYPESAFE_API_KEY` fails naming `'typesafe'`, and a keyless boot succeeds. `pipelex update` touches only the deck, so upgraders never receive the table; only a fresh `pipelex init` meets it. This is the one open question for the user.

**The traps met here**, all worth knowing before touching this branch:

- A worktree's e2e CLI tests boot from the machine's **global** `~/.pipelex`, whose deck must carry `5_judgment_deck.toml`; copy the kit's file there if those tests fail with "Missing required fields: 'judgment'".
- `make agent-check` runs the keyword-only fixer, which rewrote `TypesafePlugin.register` before its grant existed. Grant first (`make sgr FUNC=… RATIONALE=…`).
- `make gei` and `make gep` must be rerun after any change to an error class; the identity snapshot test fails otherwise.

**Confirm the gate below before starting phase 3.**

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
