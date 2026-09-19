---
status: draft
item: L-260919-9965d0
---

# Judgment family and the `PipeJudge` operator — design

A judgment is a closed-form verdict on some material: a yes or a no, one option out of a declared set, or a position on a declared scale, together with how sure the producer is. The language already speaks this vocabulary and routes it nowhere special: the native `YesNo` concept (`pipelex/core/concepts/native/concept_native.py:31`) and the `label` and `rating` intent words (`pipelex/language/intent_hints.py:21`, spelled to the author at `pipelex/pipeline/hint_warnings.py:195`). The corpus bundle `native_yes_no_urgent_message` (`pipelex/test_extras/mthds_corpus/entries/native_yes_no_urgent_message/bundle.mthds`) spends a full generative call, a free-text completion and a structured-output parse to obtain one boolean, and the boolean arrives with no measure of certainty.

This design adds a new `InferenceFamily` member beside `search` (`pipelex/plugins/inference_backend_registry.py:11`), a worker contract for it, a new operator that reaches it, and a first backend: TypeSafe's Jev model, whose question types are exactly these verdict shapes. `search` is the family it copies, because `search` is the lightest: no core config section, no cached workers, one leaf module, one kernel module.

**Scope of this document:** the contracts and the decisions. The implementation tracker is a `plan.md` written after ratification, and the cross-repo items named under "Route" are filed then.

## What the backend offers, as observed

These facts were read from `docs.typesafe.ai` while writing this design and then **checked against the live API by the phase 1 spike**, whose record is `spike-findings.md` beside this file and whose saved responses are under `spike/responses/`. Where the two disagreed the observation won and the line below says so. They are the vendor's contract at that reading, and the worker is the only place allowed to depend on them.

- One endpoint, `POST https://api.typesafe.ai/v1/systemone`, with a bearer key. A request carries one `state` (a string, a JSON object, or an array), a `model`, and a map of `questions` keyed by an id the model never sees. Every question in a request is answered independently and in parallel over the same state; none can see another's answer.
- A question has a `type`, `instructions`, and `criteria`. For the yes/no type (the vendor calls it Noul) the criteria are optional descriptions of the two outcomes, under the keys `true` and `false`; an unknown key is accepted and silently ignored, so only our own validation catches a typo. For Choice they are a map from option key to a description or null, and 61 options were accepted. For Score they are an ordered array of level descriptions, from low to high, each describing a concrete situation, **within ten levels** — eleven is refused. Both `instructions` and `criteria` also accept structured JSON rather than strings, which this design does not use. The vendor's own minimum is one option and one level; the two-member minimum in Part 1 is this language's rule, not the vendor's.
- The yes/no answer is a single number: the probability of yes. There is deliberately no separate confidence, because the probability is the confidence. The Choice answer is the most probable option key, the full distribution over options, and a confidence between zero and one that summarises how concentrated the distribution is. The Score answer is the probability-weighted position over zero-based level indices, the distribution over levels, a legend, and a confidence of the same kind.
- The response reports `usage.input_tokens` and `usage.output_tokens` **per request, never per question**, and the versioned model id that answered, and carries a `request_id` on success as well as on failure. A rating answer's `probabilities` and `legend` are keyed by **strings on the wire** and by integers only after the SDK's models coerce them. The aliases `jev-latest` and `jev-preview` both resolve to `jev-1.13.0` today, and that versioned id is accepted as a request `model` — but `GET /v1/models` lists only the two aliases, so moving a pinned handle is a read of the vendor's models page and never a programmatic lookup.
- Input is text only, though a JSON object state has its numbers, booleans, nested objects and arrays read as such; an array state drops the field names a question refers to and answers measurably worse, so the state is always an object. Pricing is $0.042 per million input tokens with **output free**, which is the one place this family's cost arithmetic differs from an LLM's. A request answered in about 0.24 s from a developer machine, not the tenth of a second the documentation suggests. The context limit is 64k tokens per request, 32k for the state plus the longest question, and exceeding it is a `400` carrying `max_tokens_exceeded`. Three questions over one state cost 506 input tokens against 1138 for the same three sent separately.
- Errors: `401` for a missing or invalid key, and **`400` for every validation failure observed** — an illegal question, an unknown model, an oversized state — rather than the `422` the documentation advertises; `429` for a rate limit and `529` for overload are documented and were not provoked. The error body takes two shapes that the worker must both read: `detail` is a bare string for question-shape errors and an object carrying `error_type` (`authentication_error`, `api_usage_error`, `max_tokens_exceeded`) and sometimes `message` for the rest. The Python package is `typesafe-sdk` (MIT), with an `AsyncTypeSafeClient` whose `system_one(state, questions, *, model, retry, timeout, …)` returns a typed response; its `TypeSafeAPIError` subclasses carry `status`, `body`, `headers`, `endpoint` and `request_id`, while a bare `TypeSafeError` is raised client-side, before any call, for an empty questions map or a rating with no levels. Its `RetryPolicy` defaults to two retries on 408, 429 and every 5xx with backoff and `Retry-After`, and `max_retries=0` turns it off. It depends on `httpx2`, `tenacity`, and a pydantic floor above the one `pyproject.toml` declares for the core, which the repo already satisfies.
- The vendor's known-limitations page is a design input: the model reads literally, does not count, should not be asked for arithmetic or date ordering, degrades on large irrelevant state, and its scores should be thresholded rather than used as exact magnitudes.

## The decisions, in one place

1. **The family is `judgment` and the operator is `PipeJudge`.** The operator is a verb like `PipeExtract` and `PipeSearch`; the family is a noun like `search` reads in "the search family".
2. **The language surface uses the standard's own words, never the vendor's.** The question kinds are yes/no, choice and rating — `YesNo` is already a native and `rating` is already an intent word. "Noul", "Score", "Jev" and "System One" appear only under `pipelex/providers/typesafe/`, in the backend TOML, and in the backend's documentation page. This is the MTHDS-versus-Pipelex brand boundary applied one level further out: the operator belongs to the language, and the vendor belongs to a plugin.
3. **The answer carries its uncertainty in its content**, which requires a change to the standard's native set: `YesNo` gains an optional `probability`, and two natives are added, `Choice` and `Rating`. Part 2 argues this against the alternatives.
4. **The question kind is decided by which criteria member the pipe declares, and the output concept must agree.** No separate discriminator field, as with `PipeLLM` and `PipeSearch`, where the output concept decides the mode.
5. **Inputs reach the model as named state, not as text pasted into the question.** The question is a template like every other inference operator's prompt, but the material being judged travels beside it.
6. **The worker contract is batch-shaped** — one state, a map of questions, a map of answers — and the operator sends a batch of one. Batching is the backend's whole economy, and a contract that cannot express it would have to be broken to gain it.
7. **Intent hints stay non-normative.** `label` and `rating` never route a pipe to this family. An author chooses `PipeJudge` explicitly.
8. **No core config section, no cached worker**, following `search`. The SDK client is cached through the `SdkClientRegistry`, because unlike Linkup's it holds a connection pool.
9. **Uncertainty is optional in the contract**, so that a backend which cannot measure it (a generative model emulating a judgment) can still serve the family honestly, by leaving the field absent rather than inventing a number.

## Part 1 — The operator surface

```toml
[pipe.judge_is_urgent]
type = "PipeJudge"
description = "Decides whether a message is urgent"
inputs = { message = "Text" }
output = "YesNo"
question = "Is the message urgent?"
```

```toml
[pipe.route_ticket]
type = "PipeJudge"
description = "Picks the team that should handle a ticket"
inputs = { ticket = "Ticket" }
output = "Choice"
question = "Which team should handle the ticket?"

[pipe.route_ticket.options]
returns = "Exchanges, refunds, wrong or damaged items"
shipping = "Delivery status, delays, lost packages"
billing = "Charges, invoices, payment problems"
other = "None of the above"
```

```toml
[pipe.rate_severity]
type = "PipeJudge"
description = "Rates how severe a reported issue is"
inputs = { report = "BugReport" }
output = "Rating"
question = "How severe is the reported issue?"
levels = [
  "Cosmetic; no impact on functionality",
  "Broken or degraded feature, but a workaround exists",
  "Blocking issue; no workaround exists",
]
```

**`PipeJudgeBlueprint` fields** (`pipelex/pipe_operators/judge/pipe_judge_blueprint.py`, mirroring `pipe_search_blueprint.py`):

- `type: Literal["PipeJudge"]`, `pipe_category: Literal["PipeOperator"]`.
- `question: str` — required. A template, preprocessed and parsed exactly as `PipeSearchBlueprint.prompt` is, so `$name` and `@name` behave as they do everywhere else and `validate_inputs` diffs required variables against declared inputs with the same code.
- `model: JudgmentModelChoice | None` — a preset, an alias, a waterfall or a bare handle, resolved by the same ladder as `SearchModelChoice`.
- `options: dict[str, str] | None` — the choice question's option set, key to description. An empty string is an option with no description, since TOML has no null. At least two options, with non-empty keys. Keys are what the answer carries, and a `PipeCondition` outcome map is keyed by plain strings too, so a `Choice` drives a `PipeCondition` with no translation (`expression = "routing.choice"`, one outcome per option).
- `levels: list[str] | None` — the rating question's scale, low to high. At least two levels, each a non-empty description. A level's index in this list is the level number, starting at zero.
- `criteria: JudgeYesNoCriteria | None` — a closed table with optional `yes` and `no` descriptions, valid only on a yes/no question.
- `threshold: float | None` — valid only on a yes/no question, strictly between zero and one. The verdict is yes when the probability is at or above it; absent means one half. It lives on the pipe because the threshold is policy, and policy belongs in the method file where a reviewer can see it.

**Kind resolution.** `options` and `levels` are mutually exclusive. Neither present is a yes/no question; `options` is a choice; `levels` is a rating. `criteria` or `threshold` beside `options` or `levels` is a blueprint validation error. These are language rules, so they live on the blueprint. The output agreement needs the concept library, so it lives in `validate_output_with_library` and in the factory, which resolves the wanted native the way `PipeSearchFactory` resolves `SearchResult` (`pipe_search_factory.py:39`): the output must be compatible, strictly, with `YesNo`, `Choice` or `Rating` according to the kind, which admits an author's own refinement (`Department` refining `Choice`). A mismatch names both sides: "this pipe declares `options`, so it asks a choice question and its output must be `Choice` or refine it; it declares `Text`".

**Multiplicity.** The output is single. A `PipeBatch` over a list asks one question per item, each with its own state, which is inherent: different states cannot share a request.

**Input restrictions.** The family's first model accepts text only, but that is a model capability, not a language rule, so it is not a blueprint error. `validate_inputs_static` rejects an input whose concept is compatible with native `Image` or `Document` when the resolved model's spec lists only `text` among its `inputs`, and tells the author to extract first. An image nested inside a structured input is serialised as its fields and is the author's concern.

**The spec layer.** `PipeJudgeSpec` (`pipelex/builder/pipe/pipe_judge_spec.py`) carries the same fields and converts with `to_blueprint()`; there is no authoring convenience worth a divergence between the two layers at this stage.

## Part 2 — What the answer is, and why the natives change

The user-facing requirement is that the answer carries its probability or confidence. There are consumers for it at every distance: a `PipeCondition` inside the same method gating on it (`expression_template = "{{ 'auto' if verdict.probability >= 0.9 else 'review' }}"` — the vendor's confidence-gated routing pattern, expressed with a controller the language already has), the calling application reading it from a typed output, and the graph viewer. The first two read working memory and the method's output, so the number has to be in the stuff's content.

**The rule the natives follow: a native requires its verdict and nothing else.** The required member is the one thing every conceivable producer can state — the boolean, the option key, the level. Every measure of uncertainty is optional and is defined by what it means, never by how one vendor computes it, so that a producer which measures less fills in less and a producer which measures nothing still emits a valid content. The first backend happens to fill every member; the definitions must not assume the next one will. Adding an optional member to a pinned native later is additive, while removing or loosening a required one breaks every port, which is the second reason to start from the smallest required set.

**The native set after the change:**

- `YesNo` — unchanged `yes_no: boolean, required`; added `probability: number`, optional, "The probability that the answer is yes, from 0 to 1, when the producer reports one." A `YesNo` produced by `PipeLLM`, by an input form or by a `PipeFunc` leaves it absent, and every existing `YesNo` stays valid. There is precedent for an optional member beside a native's required one: `Date` carries an optional `time`.
- `Choice` — "One option picked out of a declared set." `choice: text, required`, the key of the selected option. Optional: `confidence: number`, "The producer's confidence in the choice, from 0 to 1, when it reports one"; `probabilities: dict` from text to number, the distribution over option keys, when the producer measures one.
- `Rating` — "A position on an ordered scale of described levels." `level: integer, required`, the index of the selected level, zero being the first level declared. Optional: `confidence: number`, defined as for `Choice`; `position: number`, a continuous position on the scale when the producer measures one; `probabilities: dict` from text to number, keyed by level index.

The standard does not fix how `confidence` is computed. The first backend derives it from how concentrated its distribution is; another may report a different measure, and a method that gates on a threshold has to be evaluated against the model it runs on either way, which is already the vendor's own advice. No optional member is ever synthesised: a backend that has a confidence but no distribution fills `confidence` alone, and nothing fabricates a `probability` of one or zero from a bare yes or no.

`level` is the required member of `Rating`, not the weighted position, for two reasons. Every conceivable backend can produce a level — one that only measures a continuous position rounds it — while only one that measures a distribution can produce a position. And the vendor's own limitations page warns against using the weighted score as an exact magnitude, so the field a method branches on should be the discrete one. How a level is selected is the producer's business and not the standard's; the first backend's worker takes the most probable level, and on a tie the one nearer the weighted position, then the lower one.

Plain rendering follows `YesNoContent`, which renders as "yes" or "no": a `Choice` renders as its key and a `Rating` as its level, so `$routing` in a downstream prompt reads naturally and the uncertainty is reached by name (`$routing.confidence`).

**Alternatives considered, and why each loses:**

- *Verdict in content, uncertainty only in the graph trace.* No change to the standard, but a `PipeCondition` cannot gate on it and the calling application never sees it. It drops the one thing this backend adds over a generative call.
- *An author-declared structured concept matched by reserved field names.* This is a native concept that refuses to say so: the operator would validate a shape by convention, and every author would redeclare it.
- *A refinement of `YesNo` that adds a field.* Not expressible: a concept cannot have both `refines` and `structure` (`pipelex/core/concepts/concept_blueprint.py:118`).
- *An annotation on `Stuff` rather than on content.* It would touch working-memory serialisation, the protocol models and both SDKs to serve one operator.
- *One polymorphic `Judgment` native.* Its verdict would be a boolean, a text or a number depending on the producer, which is no type at all.
- *`Text` and `Number` as the choice and rating outputs.* Tempting, because `label` is a text-valued intent and `rating` a number-valued one, but a `Text` has nowhere to put a confidence. A later "bare verdict" tier that also accepts a `Text`-compatible or `Number`-compatible output is possible without breaking anything, and is deferred until an author asks: it would silently drop the uncertainty, which is the wrong default.

**Cost of the change, stated plainly.** The natives are pinned by the standard (`pipelex/core/concepts/native/pinned_blueprints.py`, held to `mthds/docs/spec/native-concepts.md` by `test_pinned_natives_vs_standard.py`), so this lands in the `mthds` spec page first, re-pins the set at a new standard version, and ripples to every port: `NativeConceptCode` and its exhaustive matches, new `ChoiceContent` and `RatingContent` classes registered in `CoreRegistryModels.STUFF`, the concept factory, codegen's native expansion, and the projection corpus committed in `mthds-js` and `mthds-python`. Two questions belong to that standard change and are left open here with a recommendation: `Choice` and `Rating` should join the out-of-matrix natives (`OUT_OF_MATRIX_NATIVES` in `pipelex/cli/dev_cli/commands/projection_reference.py`) beside `SearchResult`, because a bare `"billing"` at a `Choice` position is indistinguishable from a `Text`; and `YesNo`'s light form should stay the bare boolean, which means a projection that flattens a judged `YesNo` loses its probability and a consumer who wants it reads the full form.

If the standard change cannot land soon, the fallback that wastes the least work is to ship the yes/no kind alone against today's `YesNo`, with the probability in the trace only, and to hold choice and rating until the natives exist. It is a fallback and not the plan, because it ships the operator without its point.

## Part 3 — The cogt contract

The package is `pipelex/cogt/judgment/`, mirroring the live files of `pipelex/cogt/search/`.

**Question and answer models** (`judgment_models.py`), discriminated unions on `kind`:

- `YesNoQuestion(kind, instructions, yes_criterion, no_criterion)`, `ChoiceQuestion(kind, instructions, options: dict[str, str | None])`, `RatingQuestion(kind, instructions, levels: list[str])`.
- `YesNoAnswer(kind, probability: float | None, yes_no: bool | None)`, `ChoiceAnswer(kind, choice, confidence: float | None, probabilities: dict[str, float] | None)`, `RatingAnswer(kind, level, position: float | None, confidence, probabilities: dict[int, float] | None)`.

The answers follow the same rule as the natives: `choice` and `level` are the only required members, and `YesNoAnswer` requires at least one of its two, enforced by a model validator. A worker that measures a probability returns it and leaves `yes_no` to the caller; a worker that cannot returns `yes_no` and no probability, and a `threshold` on such a pipe has nothing to apply to, which the kernel reports as a warning on the run rather than ignoring quietly. Deriving a required member from a richer measurement — the most probable level from a distribution, for instance — is the worker's translation work, since only the worker knows what its backend measured. Applying the threshold is the kernel's job, not the worker's, so the raw judgment stays reusable and the policy stays in one place.

**Job.** `JudgmentJob(InferenceJobAbstract)` carries `state: JudgmentState` (a JSON-compatible value), `questions: dict[str, JudgmentQuestion]` (non-empty), `job_params: JudgmentJobParams` holding the `JudgmentSetting`, and `job_report` holding `JudgmentTokensUsage`. `JudgmentJobFactory.make_judgment_job(...)` stamps `JobCategory.JUDGMENT_JOB`.

**Worker.** `JudgmentWorkerAbstract(InferenceWorkerAbstract)` exposes one template method, `async def judge(self, judgment_job: JudgmentJob) -> dict[str, JudgmentAnswer]`, and one abstract hook, `_judge`. The template method copies `SearchWorkerAbstract.search_sourced_answer` step for step — validate, stamp `UnitJobId.JUDGMENT_ANSWER`, `judgment_job_before_start`, call the hook, `fill_model_and_provider` on a `CogtError`, and complete and report in `finally` — including the commented reason the reporting sits in `finally` (`search_worker_abstract.py:47`). After the hook returns, the template method checks that the answers' keys are exactly the questions' keys and that each answer's kind matches its question's, so no backend can return a verdict for a question nobody asked.

**Setting and deck.** `JudgmentSetting(ConfigModel)` has `model: str` and `description: str | None` and nothing else; `JudgmentModelChoice` is the usual union with a parsed model reference. `JudgmentDeckBlueprint` has `aliases`, `waterfalls`, `presets` and `choice_default`, flattened onto `ModelDeck` with `get_judgment_setting`, `validate_judgment_presets` and `check_judgment_choice_with_deck` as for search. The deck file is `pipelex/kit/configs/inference/deck/5_judgment_deck.toml` — the numeric prefix is what makes it kit-managed (`pipelex/cogt/models/deck_manifest.py:98`) — with `choice_default = "@default-judgment"` and the alias pointing at a versioned handle, never at a `latest` alias: a verdict model that changes under a method silently changes what every threshold in that method means.

**The family enums.** There are several, and all must move together: `InferenceFamily` (`inference_backend_registry.py:11`), `ModelType` (`pipelex/cogt/model_backends/model_type.py:4`), `InferenceErrorFamily` with its failure and not-found class tables (`pipelex/cogt/inference/error_render.py:35`), and `ModelCategory` in the builder (`pipelex/builder/operations/models_ops.py`). The match statements over them are exhaustive and free of `case _`, so the type checker walks to most arms.

**One dispatch that is exhaustive only by accident.** `CostRegistry.compute_cost_report` (`pipelex/cogt/usage/cost_registry.py`) tests for the LLM, image-generation and search usages and lets everything else fall through to an `ExtractTokenCostReport`. A new family does not slip through silently: each report types `model_type` as its own `Literal`, so once `JudgmentTokensUsage` joins the `TokensUsage` union the fallthrough no longer type-checks and `make agent-check` goes red. The plan adds the judgment arm, gives extract an explicit arm, and closes the function with `assert_never`, so the exhaustiveness is stated rather than inferred from a literal.

**Usage and cost.** Unlike search, which encodes per-request billing as a token count, this family reports real tokens: `nb_tokens_by_category` takes `input` and `output` from the response's usage, and the backend TOML states the price in USD per million tokens like any LLM. When the backend omits usage, the job reports no tokens rather than a guess. The `model_type` comment on `ModelUsageSpec` (`pipelex/graph/graphspec.py:282`) gains the new value and says it is token-billed.

## Part 4 — State, the leaf, and the kernel

**State is the pipe's inputs, by name.** The kernel builds a JSON object with one member per declared input. A `Text` becomes a string, a `Number` a number, a `YesNo` a boolean, a list an array, and anything else the JSON form of its content. This is the vendor's own recommendation (named fields keep relationships clear), and it is also what a vendor-neutral contract wants: a second backend receives the same object. The question template may still interpolate an input, and should do so only for short parameters ("Is the message about $topic?"), because the vendor advises stating the condition directly rather than through an indirection; an interpolated input is sent in the state as well, which is harmless. The operator's documentation page carries the authoring guidance that matters here: one narrow judgment per pipe, levels that describe situations rather than degrees, a catch-all option when nothing may fit, and code rather than the model for counting, arithmetic and date ordering.

**Assignment and leaf.** `JudgmentAssignment(BaseModel)` in `assignment_models.py` carries `job_metadata`, `cogt_run_params`, `state`, `questions`, `judgment_setting` and a `judgment_handle` property. `pipelex/cogt/content_generation/judgment_generate.py` has one coroutine, `judgment_gen_answers(judgment_assignment) -> dict[str, JudgmentAnswer]`, opening with the dry branch. There is no dynamic output class, so there is no boundary arm and in-process arm to split as search has: answers are plain serialisable models and cross an activity boundary as they are. `ContentGeneratorProtocol` gains `make_judgment_answers`, with its `@override` in `ContentGenerator`.

**Dry run.** `dry_judgment_gen_answers` is deterministic: yes for a yes/no question, the first option for a choice, the lowest level for a rating, and every uncertainty member absent — no producer measured anything, and the content says so.

**Kernel.** `pipelex/kernel/judgment_ops.py` exposes `resolve_judgment_setting(*, judgment_choice=None)`, which pins the setting to the resolved handle exactly as `resolve_search_setting` does, and `run_judgment(*, memory, question, templating_style, judgment_setting, concept, job_metadata, cogt_run_params, threshold=None, result_name=None, result_code=None) -> JudgmentResult`, where `question` is the kind-specific blueprint-level question before rendering. It renders the template, builds the state, sends a batch of one under a fixed question id, applies the threshold, builds the native content, and stores it. `JudgmentResult` is frozen and carries `memory`, `content`, `rendered_question`, `judgment_setting` and the raw `answer`. The kernel boot contract test owes this entry point an arm, and the kernel documentation page's entry-point table a row, which fires the `pipelex-kernel-docs` drift contract.

**Trace.** `PipeJudge` registers `rendered_question`, `resolved_model`, the question kind, the applied threshold, and the raw answer as execution data, so the graph viewer can show the distribution without the content having to carry more than the native defines.

## Part 5 — The first backend

A built-in plugin at `pipelex/providers/typesafe/`, appended to `KERNEL_BUILTIN_PLUGINS`, registering `add_inference_backend(family=InferenceFamily.JUDGMENT, sdk="typesafe", make_worker=…)`. The `make_worker` closure calls `require_sdk(spec="typesafe_sdk", extra="typesafe", dependency_name="typesafe-sdk", …)` and imports the worker lazily, as `linkup_plugin.py` does.

- **Dependency: the SDK, behind a `typesafe` optional extra.** The spike settled this. Using the SDK rather than a hand-written POST buys typed exception classes carrying `status`, `body`, `endpoint` and `request_id` — exactly what the error classification below is written from — and the coercion of a rating answer's string keys to integers, both of which a bare `httpx` worker would have to rebuild. The feared cost did not materialise: the extra added five packages (`typesafe-sdk`, `httpx2`, `httpcore2`, `httpx2-jsfetch`, `truststore`), moved nothing else in the lock, left pydantic where it was, and disturbed neither `mypy` nor `pyright` on any unrelated import. The worker passes an explicit retry policy and timeout rather than inheriting the SDK's defaults, so retry behaviour is a Pipelex decision recorded in one place; note that `RetryPolicy` carries a `timeout` of its own beside the client's and the per-call one, and all three are set deliberately.
- **Backend records.** `[typesafe]` in `backends.toml` with `api_key = "${TYPESAFE_API_KEY}"`, and `backends/typesafe.toml` with `model_type = "judgment"`, `sdk = "typesafe"`, one table per versioned model (`inputs = ["text"]`, `outputs = ["judgments"]`, `costs = { input = 0.042, output = 0 }` per million tokens, from the vendor's models page at the time of writing, output being genuinely free), and a routing profile. The default alias points at `jev-1.13.0`, with a comment saying that a newer versioned id is found on the vendor's models page and not through `GET /v1/models`, which lists only aliases. All mirrored into `.pipelex/inference/`.
- **Translation.** The worker maps `YesNoQuestion` to the vendor's yes/no type with `true` and `false` criteria, `ChoiceQuestion` to a choice with a `null` for an undescribed option, `RatingQuestion` to a score, and maps the answers back. The vendor's limits on option and level counts are enforced here, not in the blueprint, because they are this vendor's and not the language's.
- **Errors.** `TypesafeJudgmentResponseError` for an answer that is missing or of the wrong kind. Classification branches on `error_type` where the body carries one and falls back to the status, because a single `400` covers an illegal question, an unknown model and an oversized state: `authentication_error` classifies as credentials, `max_tokens_exceeded` as content, `api_usage_error` naming an unknown model as configuration, rate limit and overload as transient, and a `400` with a bare-string `detail` as a Pipelex defect, since static validation should have caught a malformed question. A bare `TypeSafeError`, raised before the call, is always a Pipelex defect. The family classes are `JudgmentJobFailureError`, `JudgmentModelNotFoundError` and `JudgmentHandleNotFoundError`, and the operator's are `PipeJudgeError` and `PipeJudgeFactoryError`. Error pages and the identity snapshot are regenerated (`gep`, `gei`).

**A second backend, not in this campaign.** A worker that emulates the family on a generative model through structured output makes a method using `PipeJudge` runnable on any deck, which matters for an operator that belongs to an open standard. It returns verdicts without uncertainty, which decision 9 makes legal. It is deferred because it is a second implementation of a contract that should first be proven by one.

## Part 6 — Hints, and what does not change

`docs/spec/intent-hints.md` in `mthds` is explicit that no verdict, execution behaviour or gating decision ever reads a hint, and `pipelex/language/intent_hints.py` repeats it. So `label` and `rating` are evidence that the vocabulary exists, not a routing signal, and nothing in this design consults them. `intent_word_applies` needs no change: a `Rating` or a `Choice` is a structured site, where no intent word applies, exactly as for `YesNo` today. An advisory lint suggesting `PipeJudge` on a `PipeLLM` whose output is `YesNo` is possible and deferred: a generative call is a legitimate way to reach a yes or a no when the judgment needs reasoning or an image, and a lint that fires on legitimate code is noise.

Not touched, and worth saying so: `InferenceBackendRegistry` and `PluginRegistrar.add_inference_backend` are family-agnostic; the MTHDS schema generator derives pipe definitions from `PipeBlueprintUnion`; the error page and identity generators walk classes; `pipelex/pipelex.toml` and `configs.py` gain nothing; `InferenceManager` caches no worker for this family; the agent rules name no pipe type.

## Part 7 — Registration, tests, corpus, docs

The operator follows `docs/contribute/registration-surface.md`: `PipeType.PIPE_JUDGE` and its category arm, membership in `PipeBlueprintUnion`, `PipeJudge` and `PipeJudgeFactory` in `pipelex/pipe_machinery/registry_models.py` (the omission that boots cleanly and fails later in deserialisation), the output renderer's match, the spec map and the spec union, the TOML emission branch in `pipelex/builder/operations/pipe_ops.py` and its twin in `pipelex/cli/agent_cli/commands/pipe_cmd.py`. No page enumerates what a new inference family touches; this campaign writes it, as a sibling of the registration-surface page, from the site map gathered for this design.

Tests, written first: blueprint kind-resolution and its error messages; output agreement with refinements; state building per content kind; threshold application at and around the boundary; the worker template method's key and kind checks, mutation-tested by breaking each guard; the translation to and from the vendor's shapes against recorded responses; the dry branch; the cost-registry arm, with a test that fails if a family falls through to extract; the registry split test; the kernel boot contract arm. A `judgment` pytest marker joins the default deselect expression, `preprocess_test_models_cmd.py` learns the model type in each of its family tables, the test profiles gain a `judgment_models` key, and an e2e bundle under `tests/e2e/pipelex/pipes/pipe_operators/pipe_judge/` covers the question kinds against the live model.

Corpus: a `[operator.judge]` vocabulary entry and new entries under `pipelex/test_extras/mthds_corpus/entries/`, the first being the urgent-message scenario re-cut with `PipeJudge`. `native_yes_no_urgent_message` stays as it is: it covers `native.yes_no` produced by `PipeLLM`, which remains valid MTHDS.

Docs in this repo: the `PipeJudge` operator page and a feature page with their `mkdocs.yml` entries; the operator round-ups; the native concepts page; the inference-backend-plugins page, whose family comment, "serves all four" sentence and worker-contract table all go stale; the distributed content generation, dry-run and per-node usage pages; `pipelex/builder/CLAUDE.md`, whose operator list is already missing `PipeStructure`. Generated artefacts to refresh: the MTHDS schema, the error pages and identity snapshot, the generated model sets, the corpus vocabulary, and the `.pipelex/inference/` mirror.

## Route

The order is set by what each step needs from the one before.

1. `mthds` — the standard change: the native set in `docs/spec/native-concepts.md`, the `PipeJudge` operator in the language reference, and the two projection questions from Part 2.
2. `pipelex` — natives, family, operator, backend, in that order, each independently mergeable: the natives change stands alone, the family is testable with a fake worker before any vendor code exists, and the operator needs both.
3. After a `pipelex` release — the schema copies through the `mthds-schema-sync` skill (`mthds`, `vscode-pipelex`, `mthds-ui`), the corpus through `mthds-corpus-sync`, the projection corpus in `mthds-js` and `mthds-python`, a node rendering for the new operator in `mthds-ui`, and the operator lists the authoring skills in `pipelex-plugins` and `mthds-plugins` teach from.
4. The hosted plane — `pipelex-server/temporal/` registers an activity for the new leaf and a queue for it; the pin moves across `pipelex-server` in one commit; and serving the family from the hosted plane without a customer-held key means a route in `pipelex-manifold` and model entries in `pipelex-remote-config`. That last step is a product decision before it is an engineering one.

## Open questions for ratification

The vendor-dependency question that stood here is closed: the phase 1 spike settled it in favour of the SDK behind an extra, for the reasons in Part 5 and in `spike-findings.md`.

- **The standard change.** Is extending `YesNo` and adding `Choice` and `Rating` acceptable to the standard, and are those the names? `Rating` is chosen over the vendor's "Score" because the language already owns the word.
- **How much optional surface to pin on day one.** `probabilities` and `position` are the members most shaped by the first backend. The smaller alternative pins only the verdict and one optional scalar per native (`probability` on `YesNo`, `confidence` on `Choice` and `Rating`), keeps the distribution and the position in the trace, and promotes them to the natives when a method needs to branch on them. It is cheaper for the standard and every port, and nothing is lost that cannot be added later; it costs the patterns that read a distribution inside a method, such as falling back to the second most probable option. This design pins them as optional members; the smaller set is the one to take if the standard change meets resistance.
- **`question` or `prompt`.** Every other inference operator calls its template `prompt`. `question` says what the field is; `prompt` is what an authoring agent will reach for. This design takes `question`.
- **Hosted serving.** Whether the hosted plane serves this family with a Pipelex-held key, and therefore whether step 4's manifold work is in the campaign or after it.

## Deferred

- A multi-question operator form, where one pipe asks several questions over the same inputs and its output is a structure with one member per question. The worker contract already carries it; the language surface and the output typing are a design of their own.
- Structured criteria — the vendor accepts objects with a definition, exclusions and examples for an option or a level. The first version takes strings.
- Bare-verdict outputs (`Text`-compatible for a choice, `Number`-compatible for a rating).
- The emulated backend on a generative model.
- The advisory lint suggesting `PipeJudge`.
