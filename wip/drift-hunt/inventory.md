# Drift Hunt — Stage 0 inventory

Every hand-written `.md` page under `docs/` in scope for the hunt, grouped by section, per decision D2 (see `TODOS.md`). Page counts per section are the denominator for the campaign's defect-density metric. Snapshot taken 2026-07-12 on `docs/Drift-hunt`.

## Scope summary

| Section | Pages | Notes |
|---|---|---|
| building-methods | 35 | MTHDS language reference (blueprint layer) |
| cookbook | 21 | ground truth = `../pipelex-cookbook` (D3) |
| features | 21 | |
| under-the-hood | 19 | |
| advanced | 7 | provider-injection pages |
| reliability | 4 | |
| contribute | 3 | 2 of 3 written/rewritten within the last days (drift-contracts, keyword-only) — expected low yield, kept per D2 |
| get-started | 3 | |
| (root) | 2 | `index.md`, `license.md` |
| tools (non-CLI) | 2 | `logging.md`, `plxt.md` |
| setup | 1 | `telemetry.md` (`gateway-models.md` excluded as generated) |
| viewpoint | 1 | |
| **Total (explicit in-scope)** | **119** | |
| pending confirmation | 4 | see below — for Louis at Checkpoint 0 |

## Pending confirmation (Checkpoint 0)

Hand-written, not generated, not freshly reviewed — but not named by D2's section list. Default proposal: include all four.

- `docs/agents/debugging-hanging-pytest-runs.md` — agent-facing debugging guide
- `docs/analytics/data-extraction.md`
- `docs/distributed-execution/index.md` — the single public distributed-execution capability page
- `docs/CLAUDE.md` — docs-site architecture notes for agents (not in the mkdocs nav, but rich in code-contradictable claims)

Also for the same ruling: the root-level `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` are include-targets of docs stubs (see Excluded) and live outside `docs/` — swept only if Louis says so.

## Excluded (with reasons)

- `docs/errors/**` — generated (`make gep`); fix the generator, never the pages (D2).
- `docs/setup/gateway-models.md` — snippet-include of the generated gateway-models doc (D2).
- `docs/configuration/**` — freshly reviewed as the config-docs drift-contract seed ack (D2).
- `docs/tools/cli/**` — freshly reviewed as the cli-docs drift-contract seed ack (D2; `pipelex/cli/agent_cli/CLAUDE.md` likewise).
- `docs/changelog.md`, `docs/contributing.md`, `docs/CODE_OF_CONDUCT.md` — pure snippet-include stubs (`--8<--` of root files); no content of their own.
- `docs/overrides/**` — theme templates, not content pages.

## In-scope pages by section

### building-methods (35)

- `docs/building-methods/adapt-to-llm-prompting-style-openai-anthropic-mistral.md`
- `docs/building-methods/concepts/define_your_concepts.md`
- `docs/building-methods/concepts/inline-structures.md`
- `docs/building-methods/concepts/native-concepts.md`
- `docs/building-methods/concepts/python-classes.md`
- `docs/building-methods/concepts/refining-concepts.md`
- `docs/building-methods/configure-ai-llm-to-optimize-methods.md`
- `docs/building-methods/domain.md`
- `docs/building-methods/kick-off-a-methods-project.md`
- `docs/building-methods/libraries.md`
- `docs/building-methods/packages.md`
- `docs/building-methods/pipelex-bundle-specification.md`
- `docs/building-methods/pipes/csv-input-and-output.md`
- `docs/building-methods/pipes/executing-pipelines.md`
- `docs/building-methods/pipes/index.md`
- `docs/building-methods/pipes/pipe-controllers/PipeBatch.md`
- `docs/building-methods/pipes/pipe-controllers/PipeCondition.md`
- `docs/building-methods/pipes/pipe-controllers/PipeParallel.md`
- `docs/building-methods/pipes/pipe-controllers/PipeSequence.md`
- `docs/building-methods/pipes/pipe-controllers/index.md`
- `docs/building-methods/pipes/pipe-operators/PipeCompose.md`
- `docs/building-methods/pipes/pipe-operators/PipeExtract.md`
- `docs/building-methods/pipes/pipe-operators/PipeFunc.md`
- `docs/building-methods/pipes/pipe-operators/PipeImgGen.md`
- `docs/building-methods/pipes/pipe-operators/PipeLLM.md`
- `docs/building-methods/pipes/pipe-operators/PipeSearch.md`
- `docs/building-methods/pipes/pipe-operators/PipeStructure.md`
- `docs/building-methods/pipes/pipe-operators/index.md`
- `docs/building-methods/pipes/pipe-output.md`
- `docs/building-methods/pipes/provide-inputs.md`
- `docs/building-methods/pipes/run-modes-and-backends.md`
- `docs/building-methods/pipes/signature-pipes.md`
- `docs/building-methods/pipes/understanding-multiplicity.md`
- `docs/building-methods/pipes/understanding-optionality.md`
- `docs/building-methods/pipes/working-memory.md`

### cookbook (21)

- `docs/cookbook/advisory-board.md`
- `docs/cookbook/blog-article-generator.md`
- `docs/cookbook/design-slides.md`
- `docs/cookbook/discord-newsletter.md`
- `docs/cookbook/extract-dpe.md`
- `docs/cookbook/extract-gantt.md`
- `docs/cookbook/extract-generic.md`
- `docs/cookbook/extract-invoice.md`
- `docs/cookbook/extract-markdown.md`
- `docs/cookbook/extract-proof-of-purchase.md`
- `docs/cookbook/extract-slides.md`
- `docs/cookbook/extract-table.md`
- `docs/cookbook/gen-expense-data.md`
- `docs/cookbook/gen-synthetic-data.md`
- `docs/cookbook/generate-image.md`
- `docs/cookbook/hello-world.md`
- `docs/cookbook/index.md`
- `docs/cookbook/summarize.md`
- `docs/cookbook/using-inference-plugins.md`
- `docs/cookbook/validate-expense-data.md`
- `docs/cookbook/write-tweet.md`

### features (21)

- `docs/features/advanced-customizations.md`
- `docs/features/claude-code-skills-plugin.md`
- `docs/features/cli.md`
- `docs/features/cloud-storage.md`
- `docs/features/concepts.md`
- `docs/features/configuration.md`
- `docs/features/cost-tracking.md`
- `docs/features/distributed-execution.md`
- `docs/features/document-extraction.md`
- `docs/features/execution-graph.md`
- `docs/features/gateway.md`
- `docs/features/image-generation.md`
- `docs/features/index.md`
- `docs/features/llm-integration.md`
- `docs/features/mthds-language.md`
- `docs/features/pipe-operators.md`
- `docs/features/pipeline-orchestration.md`
- `docs/features/plxt.md`
- `docs/features/telemetry.md`
- `docs/features/validation-dry-run.md`
- `docs/features/web-search.md`

### under-the-hood (19)

- `docs/under-the-hood/architecture-overview.md`
- `docs/under-the-hood/build-time-elaboration.md`
- `docs/under-the-hood/codegen-projections.md`
- `docs/under-the-hood/distributed-content-generation.md`
- `docs/under-the-hood/dry-run-mock-generation.md`
- `docs/under-the-hood/error-model.md`
- `docs/under-the-hood/execution-graph-tracing.md`
- `docs/under-the-hood/image-handling-in-llm-prompts.md`
- `docs/under-the-hood/index.md`
- `docs/under-the-hood/inference-backend-plugins.md`
- `docs/under-the-hood/init-cli-flows.md`
- `docs/under-the-hood/orchestrator-plugins.md`
- `docs/under-the-hood/pipe-routing-and-execution.md`
- `docs/under-the-hood/reasoning-controls.md`
- `docs/under-the-hood/runtime-bridge-and-transport.md`
- `docs/under-the-hood/secrets-provider-plugins.md`
- `docs/under-the-hood/storage-provider-plugins.md`
- `docs/under-the-hood/stuffartefact-and-image-rendering.md`
- `docs/under-the-hood/test-profile-configuration.md`

### advanced (7)

- `docs/advanced/content-generator-injection.md`
- `docs/advanced/index.md`
- `docs/advanced/observer-provider-injection.md`
- `docs/advanced/pipe-router-injection.md`
- `docs/advanced/reporting-delegate-injection.md`
- `docs/advanced/secrets-provider-injection.md`
- `docs/advanced/storage-provider-injection.md`

### reliability (4)

- `docs/reliability/automatic-retries.md`
- `docs/reliability/durable-execution.md`
- `docs/reliability/failure-classification.md`
- `docs/reliability/retries-and-resilience.md`

### contribute (3)

- `docs/contribute/configuration-defaults-and-overrides.md`
- `docs/contribute/drift-contracts.md`
- `docs/contribute/keyword-only-arguments.md`

### get-started (3)

- `docs/get-started/build-with-claude-code.md`
- `docs/get-started/configure-ai-providers.md`
- `docs/get-started/mthds-language-tutorial.md`

### (root) (2)

- `docs/index.md`
- `docs/license.md`

### tools, non-CLI (2)

- `docs/tools/logging.md`
- `docs/tools/plxt.md`

### setup (1)

- `docs/setup/telemetry.md`

### viewpoint (1)

- `docs/viewpoint/viewpoint.md`
