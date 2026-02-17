---
title: "Architecture Overview"
---

# Architecture Overview

Pipelex is a Python framework for building and running **repeatable AI methods** using a declarative language (`.mthds` files).

---

## Two-Layer Architecture

Pipelex separates concerns into two distinct layers:

1. **High-Level**: Business logic and orchestration
2. **Low-Level**: Cognitive tools (COGT) and AI inference

This separation allows pipeline authors to focus on *what* should happen, while the framework handles *how* to interact with AI providers.

---

## High-Level: Business Logic & Orchestration

### PipeControllers (Orchestrators)

Located in [`pipelex/pipe_controllers/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/pipe_controllers)

Controllers manage execution flow without performing work themselves:

- **PipeSequence** - Execute pipes one after another
- **PipeParallel** - Execute pipes concurrently
- **PipeBatch** - Process collections of items
- **PipeCondition** - Branch based on conditions

### PipeOperators (Workers)

Located in [`pipelex/pipe_operators/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/pipe_operators)

Operators perform concrete actions:

- **PipeLLM** - Generate text or structured data via LLMs
- **PipeExtract** - Extract content from documents (OCR, parsing)
- **PipeImgGen** - Generate images
- **PipeFunc** - Execute custom Python functions
- **PipeCompose** - Compose content from templates

### Core Domain

Located in [`pipelex/core/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/core)

- **Concepts** - Semantic types with meaning (not just data types)
- **Stuffs** - Knowledge objects combining a concept type with content
- **Working Memory** - Runtime storage for data flowing through pipes
- **Bundles** - Complete pipeline definitions loaded from `.mthds` files

---

## Low-Level: Cognitive Tools (COGT) & Inference

### COGT Layer

Located in [`pipelex/cogt/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/cogt)

The COGT layer abstracts AI provider details from business logic:

- **LLM Workers** - Prompt construction, structured output, templating
- **Extract Workers** - Document processing and OCR
- **Image Generation Workers** - Image creation
- **Model Catalog & Model Deck** - Manages available models, aliases, and presets
- **Content Generation** - Unified generation interface

!!! note "Why COGT?"
    COGT stands for "Cognitive Tools". This layer lets you swap AI providers without touching your pipeline definitions.

### Plugin System

Located in [`pipelex/plugins/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/plugins)

Provider-specific integrations handle API specifics:

- OpenAI
- Anthropic
- Google (Gemini)
- Mistral
- AWS Bedrock
- And more...

Each plugin translates Pipelex's unified interface into provider-specific API calls.

---

## How It All Fits Together

```mermaid
flowchart TB
    subgraph MTHDS[".mthds Pipeline Files"]
        direction LR
        D1["Declarative method definitions"]
    end

    subgraph HL["HIGH-LEVEL: Business Logic"]
        direction TB
        subgraph Controllers["PipeControllers"]
            C1["Sequence"]
            C2["Parallel"]
            C3["Batch"]
            C4["Condition"]
        end
        subgraph Operators["PipeOperators"]
            O1["PipeLLM"]
            O2["PipeExtract"]
            O3["PipeFunc"]
            O4["PipeImgGen"]
            O5["PipeCompose"]
        end
        subgraph Core["Core Domain"]
            CR1["Concepts"]
            CR2["Stuffs"]
            CR3["Working Memory"]
            CR4["Bundles"]
        end
        Controllers --> Operators
        Operators --> Core
    end

    subgraph LL["LOW-LEVEL: COGT & Inference"]
        direction TB
        subgraph COGT["COGT Layer"]
            CG1["LLM Workers"]
            CG2["Extract Workers"]
            CG3["Model Catalog"]
            CG4["Content Gen"]
        end
        subgraph Plugins["Plugins"]
            P1["OpenAI"]
            P2["Anthropic"]
            P3["Google"]
            P4["Mistral"]
            P5["Bedrock"]
        end
        COGT --> Plugins
    end

    subgraph API["AI Provider APIs"]
        A1["External Services"]
    end

    MTHDS --> HL
    HL --> LL
    LL --> API
```

---

## Next Steps

- [:material-book-open: Understand the Pipelex Paradigm](../home/3-understand-pipelex/pipelex-paradigm/index.md){ .md-button }
- [:material-cog: Explore Configuration Internals](../contribute/configuration-defaults-and-overrides.md){ .md-button }
