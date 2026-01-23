---
title: "Chicago Release"
---

# Pipelex v0.18.0 "Chicago"

**The AI workflow framework that just works.**

---

## A Major Milestone

Three months after our first public launch in San Francisco, Pipelex reaches a new level of maturity with the "Chicago" release (currently in beta-test). This version delivers on our core promise: **enabling every developer to build AI workflows that are reliable, flexible, and production-ready**.

Version 0.18.0 represents our most significant release to date, addressing the three priorities that emerged from real-world usage:

- **Universal model access** — one API key for all leading AI models
- **State-of-the-art document extraction** — deployable anywhere
- **Visual pipeline inspection** — full transparency into your workflows

---

## What's New

### Pipelex Gateway

A fully managed infrastructure providing unified access to AI models through a single API key. Built on enterprise-grade architecture, the Gateway:

- Fetches model configurations remotely — always access the latest models without updating Pipelex
- Supports an extensive catalog of models from OpenAI, Google, Anthropic, Mistral, and more
- Includes the latest image generation capabilities: GPT-Image-1.5, Nano Banana, Nano Banana Pro, and Flux-2-pro

[Join the waitlist](https://go.pipelex.com/waitlist) to get early access to the Gateway.

!!! info "Full Model Catalog"
    Browse all supported models in our [Gateway Models documentation](https://docs.pipelex.com/pre-release/home/5-setup/gateway-models/).

---

### Document Extraction

Four powerful extraction options to fit any use case:

| Provider | Description |
|----------|-------------|
| **Azure Document Intelligence** | Enterprise-grade OCR with high accuracy for complex layouts, tables, and handwriting |
| **docling** | IBM's open-source extraction library with local CPU processing and optional GPU acceleration |
| **Mistral OCR** | Industry-leading document understanding for media, text, tables, and equations |
| **Deepseek-OCR** | Open-source model optimized for markdown extraction from images |

**Documents in LLM Prompts** — Include PDFs directly in your prompts using `@variable` syntax. Single documents, multiple documents, mixed with text and images.

---

### Execution Graph Visualization

Full transparency into pipeline execution:

- **Interactive HTML visualization** — Inspect any pipeline with a local ReactFlow-based interface
- **Mermaid chart export** — Render pipeline diagrams anywhere: VS Code, GitHub, web applications
- **Step-by-step data inspection** — View JSON, HTML preview, images, and embedded PDFs at each execution stage

![Execution Graph Example](../../images/flow-chart-example.png){ width="400" }

---

## Additional Capabilities

### Telemetry & Observability

Production-ready monitoring with **Langfuse** and **OpenTelemetry** integration.

### Open-Source Model Support

Broad support for open-source AI:

- **Hugging Face Inference** — including qwen-image for text-to-image
- **Scaleway** — Deepseek R1, Llama 3.3, Qwen3, GPT-OSS
- **Groq** — Llama-4, Kimi-K2-Instruct
- **Via the Pipelex Gateway** — Phi-4, Kimi-K2-Thinking, Mistral-Large-3, Deepseek-OCR

### Developer Experience

- **Pydantic Structure Generation** — Convert Pipelex's declarative structured concepts into Python code with full IDE autocomplete, type checking, and validation
- **PipeCompose Construct Mode** — Build `StructuredContent` objects deterministically without an LLM, composing outputs from working memory variables, fixed values, templates, and nested structures
- **Cloud Storage for Artifacts** — Store generated images and extracted pages on AWS S3 or Google Cloud Storage with public or signed URLs
- **Python 3.14 Support**

---

## Getting Started

```bash
pip install pipelex
```

Then run `pipelex init` to configure your environment and obtain your Gateway API key at [app.pipelex.com](https://app.pipelex.com/).

!!! tip "Documentation"
    Explore our comprehensive guides at [docs.pipelex.com](https://docs.pipelex.com/)

---

## Why Pipelex

Pipelex eliminates the complexity of building AI-powered applications. Instead of managing multiple SDKs, API configurations, and infrastructure concerns, developers focus on what matters: their application logic.

- **One framework** for prompts, pipelines, and structured outputs
- **One API key** for dozens of AI models
- **One workflow** from prototype to production

---

*Ready to build AI workflows that just work?*

[Join the Waitlist](https://go.pipelex.com/waitlist){ .md-button .md-button--primary }
[Documentation](https://docs.pipelex.com/pre-release){ .md-button }
