---
title: "Turn your expertise into an AI-powered App, MCP or API"
description: "Pipelex lets you build AI methods with your coding agent and run them anywhere — from your agent or your chatbot via MCP, as a webapp, or via API in any software."
---

![Pipelex Banner](https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_banner_docs_v2.png)

# Turn your expertise into an AI-powered App, MCP or API

Describe how the work gets done in plain English, and your coding agent builds it into a method with the Pipelex plugin. A method is a multi-step, deterministic AI procedure that chains LLMs, OCR, image generation and more. Then run it as a webapp for your team or as SaaS for your customers, from your agent or your chatbot via MCP, or via API in any software.

[:material-rocket-launch: Quick Start](./get-started/quick-start.md){ .md-button .md-button--primary }
[:material-account-plus: Sign up at app.pipelex.com](https://app.pipelex.com){ .md-button }
[:material-book-open-variant: Cookbook](./cookbook/index.md){ .md-button }

---

## Get Started

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Quick Start](./get-started/quick-start.md)**

    Sign up, install the Pipelex plugin in Claude Code or Codex, and ask your agent for the method you want — then run it from your chatbot, as a webapp, or via API.

-   :material-laptop: **[Run It Yourself](./get-started/run-it-yourself.md)**

    Install the Pipelex runtime and run methods on your own machine, against the model providers you choose.

-   :material-school: **[MTHDS Language Tutorial](./get-started/mthds-language-tutorial.md)**

    Learn the declarative language step by step: concepts, pipes, sequences, inputs, and structured outputs.

-   :material-book-open-variant: **[Cookbook Examples](./cookbook/index.md)**

    Production-ready recipes — from Hello World to document extraction, synthetic data, and image generation.

</div>

---

## What a Method Looks Like

A method is a reusable, typed AI procedure, written in [MTHDS](https://mthds.ai/latest/), an open standard, and saved as a `.mthds` file. Each step is explicit, each output is structured, and every run is repeatable.

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

## Capabilities

<div class="grid cards" markdown>

-   :material-shape-outline: **[Typed Concepts](./features/concepts.md)**

    Semantic types that give meaning to every input and output — native, inline, or backed by Python classes.

-   :material-pipe: **[Pipe Operators](./features/pipe-operators.md)**

    Operators that do the work: LLM calls, text structuring, document extraction, image generation, web search, composition, and custom functions.

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

## The Ecosystem

MTHDS is the open standard behind Pipelex methods. It defines the language, the file format, and the ecosystem for sharing methods.

!!! info "Explore the MTHDS ecosystem"

    - **[mthds.ai](https://mthds.ai/latest/)** — The MTHDS language specification
    - **[mthds.sh](https://mthds.sh)** — The Methods Hub for discovering and sharing methods

!!! info "Build and run methods with Pipelex"

    - **[Pipelex plugin](./features/pipelex-plugin.md)** — The Pipelex plugin for Claude Code and Codex: skills that build and run methods, a hook that checks every edit, and the Pipelex tools
    - **[Pipelex MCP](https://github.com/Pipelex/pipelex-mcp)** — The Pipelex MCP, which ChatGPT or Claude adds to run the methods saved in your account
