![Pipelex Banner](https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_banner_docs_v2.png)

# Build & Run AI Methods

A method is a reusable, typed AI procedure — declared in a `.mthds` file and executed by Pipelex. Each step is explicit, each output is structured, and every run is repeatable.

[:material-robot-outline: Claude Code](./get-started/build-with-claude-code.md){ .md-button .md-button--primary }
[:material-school: MTHDS Tutorial](./get-started/mthds-language-tutorial.md){ .md-button }
[:material-book-open-variant: Cookbook](./cookbook/index.md){ .md-button }

---

## Why Methods?

<div class="grid cards" markdown>

-   :material-file-document-check: **Declarative**

    Express business logic at a high level of abstraction, in human-readable `.mthds` files that work across models.

-   :material-shape-outline: **Typed**

    Concepts are semantic types: AI understands what you mean, and every input and output connects with purpose.

-   :material-refresh: **Repeatable**

    Deterministic orchestration that leaves exactly the room you want for AI to express its intelligence and creativity.

-   :material-puzzle: **Composable**

    Chain pipes into sequences, nest methods inside methods, and share them with the community.

</div>

---

## What a Method Looks Like

A single pipe in MTHDS — five lines that call an LLM with typed inputs and output:

```toml
[pipe.summarize_article]
type    = "PipeLLM"
inputs  = { article = "Text", audience = "Text" }
output  = "Text"
prompt  = "Summarize $article in three bullet points for $audience."
```

From here, Pipelex handles model routing across 60+ models, structured output parsing, and pipeline orchestration.

---

## Capabilities

<div class="grid cards" markdown>

-   :material-shape-outline: **[Typed Concepts](./features/concepts.md)**

    Semantic types that give meaning to every input and output — native, inline, or backed by Python classes.

-   :material-pipe: **[Pipe Operators](./features/pipe-operators.md)**

    Six operators that do the work: LLM calls, document extraction, image generation, web search, composition, and custom functions.

-   :material-sitemap: **[Pipeline Orchestration](./features/pipeline-orchestration.md)**

    Sequence, parallel, batch, and conditional controllers that wire pipes into full methods with shared working memory.

-   :material-cloud-check: **[60+ AI Models](./features/llm-integration.md)**

    One gateway key or bring-your-own: OpenAI, Anthropic, Mistral, Google, Deepseek, Hugging Face, and more.

-   :material-check-decagram: **[Validation and Dry Run](./features/validation-dry-run.md)**

    Validate pipelines before execution and dry-run with mocked responses — catch errors without spending tokens.

-   :material-console: **[CLI and Tooling](./features/cli.md)**

    Full CLI for init, build, validate, run, and graph visualization. Plus `plxt` for formatting and linting `.mthds` files.

</div>

---

## The MTHDS Ecosystem

MTHDS is the open standard behind Pipelex methods. It defines the language, the file format, and the ecosystem for sharing methods.

!!! info "Explore the ecosystem"

    - **[mthds.ai](https://mthds.ai/latest/)** — The MTHDS language specification
    - **[mthds.sh](https://mthds.sh)** — The Methods Hub for discovering and sharing methods
    - **[MTHDS Plugins](https://github.com/mthds-ai/mthds-plugins)** — Claude Code plugin for building, running, and validating methods

---

## Get Started

<div class="grid cards" markdown>

-   :material-robot-outline: **[Build with Claude Code](./get-started/build-with-claude-code.md)**

    Describe what you want in natural language — Claude writes, runs, and iterates on your method for you.

-   :material-school: **[MTHDS Language Tutorial](./get-started/mthds-language-tutorial.md)**

    Learn the declarative language step by step: concepts, pipes, sequences, inputs, and structured outputs.

-   :material-book-open-variant: **[Cookbook Examples](./cookbook/index.md)**

    Production-ready recipes — from Hello World to document extraction, synthetic data, and image generation.

</div>

