---
title: "Pipelex Features"
description: "Explore all Pipelex capabilities: declarative AI methods, 60+ model access, document extraction, image generation, pipeline orchestration, CLI tools, and production monitoring."
---

# Pipelex Features

Pipelex is the reference runtime for AI methods written in MTHDS. This section covers the main capabilities you use to define methods, run them, and operate them in production.

This section covers all Pipelex capabilities, organized by area.

---

## Declarative AI Methods

<div class="grid cards" markdown>

-   **[MTHDS Language](mthds-language.md)**

    A declarative, TOML-based `.mthds` file format for defining AI methods without writing code. Domains, bundles, packages, and cross-references.

-   **[Concepts & Structured Types](concepts.md)**

    Semantic typing system for AI data. Native types, inline structures, Python classes, concept refinement, and hierarchies.

-   **[Pipe Operators](pipe-operators.md)**

    The workers that do the actual processing: PipeLLM, PipeStructure, PipeExtract, PipeImgGen, PipeSearch, PipeCompose, and PipeFunc.

-   **[Pipeline Orchestration](pipeline-orchestration.md)**

    Controllers for building complex workflows: PipeSequence, PipeParallel, PipeBatch, PipeCondition, and working memory for data flow.

</div>

---

## AI Capabilities

<div class="grid cards" markdown>

-   **[Pipelex Gateway & Model Access](gateway.md)**

    Unified access to 60+ AI models through a single API key, or bring your own keys for direct provider access. Open-source model support via Hugging Face, Scaleway, and Groq.

-   **[LLM Integration](llm-integration.md)**

    Text generation, structured outputs, vision language models, templating styles, system prompt inheritance, and model presets.

-   **[Document Extraction](document-extraction.md)**

    Multi-provider OCR with Mistral OCR, Azure Document Intelligence, docling, and Deepseek-OCR. PDF processing, page rendering, layout analysis, and table recognition.

-   **[Image Generation](image-generation.md)**

    Text-to-image generation with FLUX, GPT Image, and other providers. Cloud storage integration for generated images.

-   **[Web Search](web-search.md)**

    Structured web search results with source citations and advanced filters via PipeSearch.

</div>

---

## Developer Tools

<div class="grid cards" markdown>

-   **[Claude Code Skills Plugin](claude-code-skills-plugin.md)**

    Build, run, validate, and edit AI methods directly from Claude Code with the MTHDS skills plugin. Slash commands cover the full method lifecycle.

-   **[CLI](cli.md)**

    Full command-line interface: `login`, `init`, `doctor`, `build`, `validate`, `run`, `graph`, `show`, `which`, and more. Dry run mode, graph generation, and agent CLI.

-   **[plxt Formatter & Linter](plxt.md)**

    Fast formatting and linting for TOML, MTHDS, and PLX files. CI-ready with `--check` mode.

-   **[Execution Graph Visualization](execution-graph.md)**

    Interactive HTML visualization and Mermaid chart export for pipeline execution. Step-by-step data inspection with JSON, HTML, images, and PDFs.

</div>

---

## Production & Operations

<div class="grid cards" markdown>

-   **[Validation & Dry Run](validation-dry-run.md)**

    Pipeline validation without execution, dry run with mocked LLM responses, input validation, and allowed-to-fail pipes.

-   **[Distributed Execution](distributed-execution.md)**

    Run the same methods as durable workflows on a Temporal or Mistral Workflows backend, [delivered through the Pipelex platform](https://pipelex.com/products#durable-execution). Per-activity routing, named runtime profiles, and dashboard observability.

-   **[Telemetry & Observability](telemetry.md)**

    Production monitoring with Langfuse, OpenTelemetry, and PostHog integration. Gateway telemetry, span tracing, and custom destinations.

-   **[Cloud Storage](cloud-storage.md)**

    Store generated artifacts on AWS S3 or Google Cloud Storage with public or signed URLs.

-   **[Cost Tracking & Reporting](cost-tracking.md)**

    Automatic token cost tracking per operation with console logging and CSV report export.

</div>

---

## Configuration & Extensibility

<div class="grid cards" markdown>

-   **[Configuration System](configuration.md)**

    Multi-level TOML configuration: base defaults, project overrides, environment-specific, and run-mode-specific. Environment variable support.

-   **[Advanced Customizations](advanced-customizations.md)**

    Dependency injection framework for secrets, storage, observers, content generators, and pipe routers.

</div>
