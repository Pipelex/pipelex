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
  
  <table align="center">
    <tr>
      <td align="center" width="50%">
        <h3>From Whiteboard to AI Workflow in less than 5 minutes with no hands (2025-07)</h3>
        <a href="https://go.pipelex.com/demo">
          <img src="https://go.pipelex.com/demo-thumbnail" alt="Pipelex Demo" width="100%" style="max-width: 500px; height: auto;">
        </a>
      </td>
      <td align="center" width="50%">
        <h3>The AI workflow that writes an AI workflow in 64 seconds (2025-09)</h3>
        <a href="https://go.pipelex.com/Demo-Live">
          <img src="https://d2cinlfp2qnig1.cloudfront.net/banners/pipelex_play_video_demo_live.jpg" alt="Pipelex Live Demo" width="100%" style="max-width: 500px; height: auto;">
        </a>
      </td>
    </tr>
  </table>
  
</div>

# 📑 Table of Contents

- [🚀 Quick Start](#-quick-start)
  - [1. Install Pipelex](#1-install-pipelex)
  - [2. Get Your API Key](#2-get-your-api-key-free)
  - [3. Generate Your First Workflow](#3-generate-your-first-workflow)
  - [4. Run Your Pipeline](#4-run-your-pipeline)
  - [5. Iterate with AI Assistance](#5-iterate-with-ai-assistance)
- [💡 What is Pipelex?](#-what-is-pipelex)
- [📖 Next Steps](#-next-steps)
- [🔧 IDE Extension](#-ide-extension)
- [📚 Examples & Cookbook](#-examples--cookbook)
- [🎯 Optional Features](#-optional-features)
- [🔒 Privacy & Telemetry](#privacy--telemetry)
- [🤝 Contributing](#-contributing)
- [👥 Join the Community](#-join-the-community)

# 🚀 Quick start

Follow this step-by-step tutorial to build your first AI workflow in minutes:

## 1. Install Pipelex

```bash
pip install pipelex
pipelex init
```

## 2. Get Your API Key (Free)

To use AI models, you need an API key:

- **Free Pipelex API Key**: Join our [Discord community](https://go.pipelex.com/discord) and request your **free API key** (no credit card required) in the [🔑・free-api-key](https://discord.com/channels/1369447918955921449/1418228010431025233) channel.
- **Alternative Options**: Use [BlackBox AI](https://docs.blackbox.ai/), bring your own API keys (OpenAI, Anthropic, Google, Mistral), or run local AI.

See [Configure AI Providers](https://docs.pipelex.com/pages/setup/configure-ai-providers/) for details.

## 3. Generate Your First Workflow

Create a complete AI workflow with a single command:

```bash
# CV matching with interview prep
pipelex build pipe "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview" --output results/cv_match.plx
```

This command generates a production-ready `.plx` file with domain definitions, concepts, and multiple processing steps that analyzes CV-job fit and prepares interview questions.

## 4. Run Your Pipeline

**Via CLI:**

```bash
# Run with input file
pipelex run results/cv_match.plx --inputs inputs.json
```

Create an `inputs.json` file with your PDF URLs:

```json
{
  "cv_pdf": {
    "concept": "PDF",
    "content": {
      "url": "https://pipelex-web.s3.amazonaws.com/demo/John-Doe-CV.pdf"
    }
  },
  "job_offer_pdf": {
    "concept": "PDF",
    "content": {
      "url": "https://pipelex-web.s3.amazonaws.com/demo/Job-Offer.pdf"
    }
  }
}
```

**Via Python:**

```python
import asyncio
import json
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

async def run_pipeline():
    with open("inputs.json", encoding="utf-8") as f:
        inputs = json.load(f)

    pipe_output = await execute_pipeline(
        pipe_code="cv_match",
        inputs=inputs
    )
    print(pipe_output.main_stuff_as_str)

Pipelex.make()
asyncio.run(run_pipeline())
```

## 5. Iterate with AI Assistance

Install AI assistant rules to easily modify your pipelines:

```bash
pipelex kit rules
```

This installs rules for Cursor, Claude, OpenAI Codex, GitHub Copilot, Windsurf, and Blackbox AI. Now you can refine pipelines with natural language:

- "Include confidence scores between 0 and 100 in the match analysis"
- "Write a recap email at the end"
- "Add error handling for invalid inputs"

## 💡 What is Pipelex?

Pipelex is an open-source language that enables you to build and run **repeatable AI workflows**. Instead of cramming everything into one complex prompt, you break tasks into focused steps, each pipe handling one clear transformation.

Each pipe processes information using **Concepts** (typing with meaning) to ensure your pipelines make sense. The Pipelex language (`.plx` files) is simple and human-readable, even for non-technical users. Each step can be structured and validated, giving you the reliability of software with the intelligence of AI.

## 📖 Next Steps

**Learn More:**
- [Writing Workflows Tutorial](https://docs.pipelex.com/pages/writing-workflows/) - Complete guide with examples
- [Build Reliable AI Workflows](https://docs.pipelex.com/pages/build-reliable-ai-workflows-with-pipelex/kick-off-a-pipelex-workflow-project/) - Deep dive into Pipelex
- [Configuration Guide](https://docs.pipelex.com/pages/setup/configure-ai-providers/) - Set up AI providers and models

## 🔧 IDE Extension

We **highly** recommend installing our extension for `.plx` files into your IDE. You can find it in the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex). It's coming soon to VS Code marketplace too. If you're using Cursor, Windsurf or another VS Code fork, you can search for it directly in your extensions tab.

## 📚 Examples & Cookbook

Explore real-world examples in our **Cookbook** repository:

[![GitHub](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/)

Clone it, fork it, and experiment with production-ready pipelines for various use cases.

## 🎯 Optional Features

The package supports the following additional features:

- `anthropic`: Anthropic/Claude support for text generation
- `google`: Google models (Vertex) support for text generation
- `mistralai`: Mistral AI support for text generation and OCR
- `bedrock`: Amazon Bedrock support for text generation
- `fal`: Image generation with Black Forest Labs "FAL" service

Install all extras:

Using `pip`:
```bash
pip install "pipelex[anthropic,google,google-genai,mistralai,bedrock,fal]"
```

## Privacy & Telemetry

Pipelex collects optional, anonymous usage data to help improve the product. On first run, you'll be prompted to choose your telemetry preference:

- **Off**: No telemetry data collected
- **Anonymous**: Anonymous usage data only (command usage, performance metrics, feature usage)
- **Identified**: Usage data with user identification (helps us provide better support)

Your prompts, LLM responses, file paths, and URLs are automatically redacted and never transmitted. You can change your preference at any time or disable telemetry completely by setting the `DO_NOT_TRACK` environment variable.

For more details, see the [Telemetry Documentation](https://docs.pipelex.com/pages/setup/telemetry/) or read our [Privacy Policy](https://www.pipelex.com/privacy-policy).

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
