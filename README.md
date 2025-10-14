<div align="center">
  <a href="https://www.pipelex.com/"><img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/logo.png" alt="Pipelex Logo" width="400" style="max-width: 100%; height: auto;"></a>

  <h2 align="center">Open-source language for repeatable AI workflows</h2>
Pipelex is an open-source devtool that transforms how you build repeatable AI workflows. Think of it as Docker or SQL for AI operations.

Create modular "pipes", each using a different LLM and guaranteeing structured outputs. Connect them like LEGO blocks sequentially, in parallel, or conditionally, to build complex knowledge transformations from simple, reusable components.

Stop reinventing AI workflows from scratch. With Pipelex, your proven methods become shareable, versioned artifacts that work across different LLMs. What took weeks to perfect can now be forked, adapted, and scaled instantly.

  <div>
    <a href="https://go.pipelex.com/demo"><strong>Demo</strong></a> -
    <a href="https://docs.pipelex.com/"><strong>Documentation</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/issues"><strong>Report Bug</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/discussions"><strong>Feature Request</strong></a>
  </div>
  <br/>

  <p align="center">
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
    <a href="https://github.com/Pipelex/pipelex/actions/workflows/check-test-count-badge.yml"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Pipelex/pipelex/main/.badges/tests.json" alt="Tests"></a>
    <img src="https://img.shields.io/pypi/v/pipelex?logo=pypi&logoColor=white&color=blue&style=flat-square"
     alt="PyPI – latest release">
    <br/>
    <br/>
    <a href="https://go.pipelex.com/discord"><img src="https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
    <a href="https://www.youtube.com/@PipelexAI"><img src="https://img.shields.io/badge/YouTube-FF0000?logo=youtube&logoColor=white" alt="YouTube"></a>
    <a href="https://pipelex.com"><img src="https://img.shields.io/badge/Homepage-03bb95?logo=google-chrome&logoColor=white&style=flat" alt="Website"></a>
    <a href="https://github.com/Pipelex/pipelex-cookbook"><img src="https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat" alt="Cookbook"></a>
    <a href="https://docs.pipelex.com/"><img src="https://img.shields.io/badge/Docs-03bb95?logo=read-the-docs&logoColor=white&style=flat" alt="Documentation"></a>
    <a href="https://docs.pipelex.com/changelog/"><img src="https://img.shields.io/badge/Changelog-03bb95?logo=git&logoColor=white&style=flat" alt="Changelog"></a>
    <br/> 
    <br/>
</div>

<div align="center">
  <h2 align="center">📜 The Knowledge Pipeline Manifesto</h2>
  <p align="center">
    <a href="https://go.pipelex.com/manifesto"><strong>Read why we built Pipelex to transform unreliable AI workflows into deterministic pipelines 🔗</strong></a>
  </p>

  <h2 align="center">🚀 See Pipelex in Action</h2>
  <h3 align="center">From Whiteboard to AI Workflow in less than 5 minutes with no hands</h3>
  <p align="center">
    <a href="https://go.pipelex.com/demo"><img src="https://go.pipelex.com/demo-thumbnail" alt="Pipelex Demo" width="600" style="max-width: 100%; height: auto;"></a>
  </p>
  
</div>

# 📑 Table of Contents

- [Introduction](#introduction)
- [Quick start](#-quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [API Key Configuration](#api-key-configuration)
  - [Optional features](#optional-features)
- [Contributing](#-contributing)
- [Support](#-support)
- [License](#-license)

# Introduction

Pipelex makes it easy for developers to define and run repeatable AI workflows. At its core is a clear, declarative pipeline language specifically crafted for knowledge-processing tasks.

Build **pipelines** from modular pipes that snap together. Each pipe can use different AI models - language models (LLMs) for text generation, OCR models for document processing, or image generation models for creating visuals. Pipes consistently deliver **structured, predictable outputs** at each stage.

Pipelex uses its own syntax PLX, based on TOML, making workflows readable and shareable. Business professionals, developers, and AI coding agents can all understand and modify the same pipeline definitions.

Example:
```plx
[concept]
Buyer = "The person who made the purchase"
PurchaseDocumentText = "Transcript of a receipt, invoice, or order confirmation"

[pipe.extract_buyer]
type = "PipeLLM"
description = "Extract buyer from purchase document"
inputs = { purchase_document_text = "PurchaseDocumentText" }
output = "Buyer"
model = "llm_to_extract_info"
prompt = """
Extract the first and last name of the buyer from this purchase document:
@purchase_document_text
"""
```

Pipes are modular building blocks that **connect sequentially, run in parallel, or call sub-pipes.** Like function calls in traditional programming, but with a clear contract: knowledge-in, knowledge-out. This modularity makes pipelines perfect for sharing: fork someone's invoice processor, adapt it for receipts, share it back. 

Pipelex is an **open-source Python library** with a hosted API launching soon. It integrates seamlessly into existing systems and automation frameworks. Plus, it works as an [MCP server](https://github.com/Pipelex/pipelex-mcp) so AI agents can use pipelines as tools.

# 🚀 Quick start

> :books: Note that you can check out the [Pipelex Documentation](https://docs.pipelex.com/) for more information and clone the [Pipelex Cookbook](https://github.com/Pipelex/pipelex-cookbook) repository for ready-to-run examples.

Follow these steps to get started:

## Installation

### Prerequisites

- Python ≥3.10
- [pip](https://pip.pypa.io/en/stable/), [poetry](https://python-poetry.org/), or [uv](https://github.com/astral-sh/uv) package manager

We **highly** recommend installing our own extension for PLX files into your IDE of choice. You can find it in the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex). It's coming soon to VS Code marketplace too and if you are using Cursor, Windsurf or another VS Code fork, you can search for it directly in your extensions tab.

### Option #1: Run examples

Visit the 
[![GitHub](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/): you can clone it, fork it, play with it 

### Option #2: Install the package

```bash
# Using pip
pip install pipelex

# Using Poetry
poetry add pipelex

# Using uv (Recommended)
uv pip install pipelex
```

### API Key Configuration

Pipelex supports two approaches for accessing AI models:

#### Option A: Pipelex Inference (Optional & Free)

Get a single API key that works with all providers (OpenAI, Anthropic, Google, Mistral, FAL, and more):

1. **Get your API key:**
   - Join our Discord community: [https://go.pipelex.com/discord](https://go.pipelex.com/discord)
   - Request your free API key (no credit card required, limited time offer) in the [🔑・free-api-key](https://discord.com/channels/1369447918955921449/1418228010431025233) channel

2. **Configure environment variables:**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and add your Pipelex Inference API key
   # PIPELEX_INFERENCE_API_KEY="your-api-key"
   ```
   
   > **Note:** Pipelex automatically loads environment variables from `.env` files. No need to manually source or export them.

3. **Verify backend configuration:**
   - The `pipelex_inference` backend is already enabled in `.pipelex/inference/backends.toml`
   - The default routing profile `pipelex_first` is configured to use Pipelex Inference

#### Option B: Bring Your Own Keys

Use your own API keys from individual providers (OpenAI, Anthropic, Google, Mistral, AWS Bedrock, Azure OpenAI, FAL):

1. **Configure environment variables:**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and add your provider API keys
   # OPENAI_API_KEY="your-openai-key"
   # ANTHROPIC_API_KEY="your-anthropic-key"
   # GOOGLE_API_KEY="your-google-key"
   # ... (add the keys you need)
   ```

2. **Configure backends:**
   - Edit `.pipelex/inference/backends.toml` to enable/disable backends
   - Set `enabled = true` for the backends you want to use
   - Set `enabled = false` for backends you don't need

3. **Select routing profile:**
   - Edit `.pipelex/inference/routing_profiles.toml`
   - Set `active = "custom_routing"` or create your own profile
   - Configure which backend handles which models

#### Option C: Mix & Match (Custom Routing)

Combine Pipelex Inference with your own keys for maximum flexibility:

1. **Configure environment variables:**
   ```bash
   # Copy and edit .env with both Pipelex and provider keys
   cp .env.example .env
   ```

2. **Enable multiple backends:**
   - Keep `pipelex_inference` enabled in `.pipelex/inference/backends.toml`
   - Enable specific provider backends (e.g., `openai`, `fal`)

3. **Create custom routing:**
   - Edit `.pipelex/inference/routing_profiles.toml`
   - Set up a hybrid profile routing some models to Pipelex, others to your backends

See the [configuration documentation](https://docs.pipelex.com/pages/configuration/config-technical/inference-backend-config/) for detailed setup instructions.

### Optional Features

The package supports the following additional features:

- `anthropic`: Anthropic/Claude support for text generation
- `google`: Google models (Vertex) support for text generation
- `mistralai`: Mistral AI support for text generation and OCR
- `bedrock`: AWS Bedrock support for text generation
- `fal`: Image generation with Black Forest Labs "FAL" service

Install all extras:

Using `pip`:
```bash
pip install "pipelex[anthropic,google,google-genai,mistralai,bedrock,fal]"
```

Using `poetry`:
```bash
poetry add "pipelex[anthropic,google,google-genai,mistralai,bedrock,fal]"
```

Using `uv`:
```bash
uv pip install "pipelex[anthropic,google,google-genai,mistralai,bedrock,fal]"
```

---

## Example: optimizing a tweet in 2 steps

Example with the extension you can download now on Cursor, Windsurf or another VS Code fork. (Coming soon for VS Code Marketplace)

<div>
<a href="https://open-vsx.org/extension/Pipelex/pipelex">
<img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/sample_code.png" alt="Pipelex Code Sample" style="max-width: 100%; height: auto;">
</a>
</div>

### 1. Define the pipeline in PLX

```plx
domain = "tech_tweet"
description = "A pipeline for optimizing tech tweets using Twitter/X best practices"

[concept]
DraftTweet = "A draft version of a tech tweet that needs optimization"
OptimizedTweet = "A tweet optimized for Twitter/X engagement following best practices"
TweetAnalysis = "Analysis of the tweet's structure and potential improvements"
WritingStyle = "A style of writing"

[pipe]
[pipe.analyze_tweet]
type = "PipeLLM"
description = "Analyze the draft tweet and identify areas for improvement"
inputs = { draft_tweet = "DraftTweet" }
output = "TweetAnalysis"
model = "llm_for_writing_analysis"
system_prompt = """
You are an expert in social media optimization, particularly for tech content on Twitter/X.
Your role is to analyze tech tweets and check if they display typical startup communication pitfalls.
"""
prompt = """
Evaluate the tweet for these key issues:

**Fluffiness** - Overuse of buzzwords without concrete meaning (e.g., "synergizing disruptive paradigms")

**Cringiness** - Content that induces secondhand embarrassment (overly enthusiastic, trying too hard to be cool, excessive emoji use)

**Humblebragginess** - Disguising boasts as casual updates or false modesty ("just happened to close our $ 10M round 🤷")

**Vagueness** - Failing to clearly communicate what the product/service actually does

For each criterion, provide:
1. A score (1-5) where 1 = not present, 5 = severely present
2. If the problem is not present, no comment. Otherwise, explain of the issue and give concise guidance on fixing it, 
without providing an actual rewrite

@draft_tweet
"""

[pipe.optimize_tweet]
type = "PipeLLM"
description = "Optimize the tweet based on the analysis"
inputs = { draft_tweet = "DraftTweet", tweet_analysis = "TweetAnalysis", writing_style = "WritingStyle" }
output = "OptimizedTweet"
model = "llm_for_social_post_writing"
system_prompt = """
You are an expert in writing engaging tech tweets that drive meaningful discussions and engagement.
Your goal is to rewrite tweets to be impactful and avoid the pitfalls identified in the analysis.
"""
prompt = """
Rewrite this tech tweet to be more engaging and effective, based on the analysis:

Original tweet:
@draft_tweet

Analysis:
@tweet_analysis

Requirements:
- Include a clear call-to-action
- Make it engaging and shareable
- Use clear, concise language

### Reference style example

@writing_style

### Additional style instructions

No hashtags.
Minimal emojis.
Keep the core meaning of the original tweet.
"""

[pipe.optimize_tweet_sequence]
type = "PipeSequence"
description = "Analyze and optimize a tech tweet in sequence"
inputs = { draft_tweet = "DraftTweet", writing_style = "WritingStyle" }
output = "OptimizedTweet"
steps = [
    { pipe = "analyze_tweet", result = "tweet_analysis" },
    { pipe = "optimize_tweet", result = "optimized_tweet" },
]
```

### 2. Run the pipeline

Here is the flowchart generated during this run:
```mermaid
---
config:
  layout: dagre
  theme: base
---
flowchart LR
    subgraph "optimize_tweet_sequence"
    direction LR
        FGunn["draft_tweet:<br>**Draft tweet**"]
        EWhtJ["tweet_analysis:<br>**Tweet analysis**"]
        65Eb2["optimized_tweet:<br>**Optimized tweet**"]
        i34D5["writing_style:<br>**Writing style**"]
    end
class optimize_tweet_sequence sub_a;

    classDef sub_a fill:#e6f5ff,color:#333,stroke:#333;

    classDef sub_b fill:#fff5f7,color:#333,stroke:#333;

    classDef sub_c fill:#f0fff0,color:#333,stroke:#333;
    FGunn -- "Analyze tweet" ----> EWhtJ
    FGunn -- "Optimize tweet" ----> 65Eb2
    EWhtJ -- "Optimize tweet" ----> 65Eb2
    i34D5 -- "Optimize tweet" ----> 65Eb2
```


### 3. wait… no, there is no step 3, you're done!

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on how to get started, including development setup and testing information.

## 👥 Join the Community

Join our vibrant Discord community to connect with other developers, share your experiences, and get help with your Pipelex projects!

[![Discord](https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white)](https://go.pipelex.com/discord)

## 💬 Support

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and community discussions
- [**Documentation**](https://docs.pipelex.com/)

## ⭐ Star Us!

If you find Pipelex helpful, please consider giving us a star! It helps us reach more developers and continue improving the tool.

## 📝 License

This project is licensed under the [MIT license](LICENSE). Runtime dependencies are distributed under their own licenses via PyPI.

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
