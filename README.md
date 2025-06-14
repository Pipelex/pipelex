<div align="center">
  <a href="https://www.pipelex.com/"><img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/logo.png" alt="Pipelex Logo" width="400" style="max-width: 100%; height: auto;"></a>

  <h2 align="center">Open-source language for repeatable AI workflows</h2>
  <p align="center">Pipelex is based on a simple declarative language that lets you define repeatable, structured, composable AI workflows.</p>

  <div>
    <a href="https://www.pipelex.com/demo"><strong>Demo</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/blob/main/doc/Documentation.md"><strong>Documentation</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/issues"><strong>Report Bug</strong></a> -
    <a href="https://github.com/Pipelex/pipelex/discussions"><strong>Feature Request</strong></a>
  </div>
  <br/>

  <p align="center">
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
    <img src="https://img.shields.io/pypi/v/pipelex?logo=pypi&logoColor=white&color=blue&style=flat-square"
     alt="PyPI – latest release">
    <br/>
    <br/>
    <a href="https://www.youtube.com/@PipelexAI"><img src="https://img.shields.io/badge/YouTube-FF0000?logo=youtube&logoColor=white" alt="YouTube"></a>
    <a href="https://pipelex.com"><img src="https://img.shields.io/badge/Homepage-03bb95?logo=google-chrome&logoColor=white&style=flat" alt="Website"></a>
    <a href="https://github.com/Pipelex/pipelex-cookbook"><img src="https://img.shields.io/badge/Cookbook-03bb95?logo=github&logoColor=white&style=flat" alt="Cookbook"></a>
    <a href="https://discord.gg/SReshKQjWt"><img src="https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
    <br/> 
    <br/>
</div>

<div align="center">
  <h2 align="center">📜 The Knowledge Pipeline Manifesto</h2>
  <p align="center">
    <a href="https://www.pipelex.com/post/the-knowledge-pipeline-manifesto"><strong>Read why we built Pipelex to transform unreliable AI workflows into deterministic pipelines 🔗</strong></a>
  </p>

  <h2 align="center">🚀 See Pipelex in Action</h2>
  <p align="center">
    <a href="https://www.pipelex.com/demo"><strong>Checkout our Demo</strong></a>
  </p>
  
</div>

# 📑 Table of Contents

- [Introduction](#introduction)
- [Quick start](#-quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Optional features](#optional-features)
- [Contributing](#-contributing)
- [Support](#-support)
- [License](#-license)

# Introduction

Pipelex makes it easy for developers to define and run repeatable AI workflows. At its core is a clear, declarative pipeline language specifically crafted for knowledge-processing tasks.

Build **pipelines** from modular pipes that snap together. Each pipe can use a different language model (LLM) or software to process knowledge. Pipes consistently deliver **structured, predictable outputs** at each stage.

Pipelex uses TOML syntax, making workflows readable and shareable. Business professionals, developers, and AI coding agents can all understand and modify the same pipeline definitions.

Example:
```toml
[concept]
Buyer = "The person who made the purchase"
PurchaseDocumentText = "Transcript of a receipt, invoice, or order confirmation"

[pipe.extract_buyer]
PipeLLM = "Extract buyer from purchase document"
inputs = { purchase_document_text = "PurchaseDocumentText" }
output = "Buyer"
llm = "llm_to_extract_info"
prompt_template = """
Extract the first and last name of the buyer from this purchase document:
@purchase_document_text
"""
```

Pipes are modular building blocks that **connect sequentially, run in parallel, or call sub-pipes.** Like function calls in traditional programming, but with a clear contract: knowledge-in, knowledge-out. This modularity makes pipelines perfect for sharing: fork someone's invoice processor, adapt it for receipts, share it back. 

Pipelex is an **open-source Python library** with a hosted API launching soon. It integrates seamlessly into existing systems and automation frameworks. Plus, it works as an [MCP server](https://github.com/Pipelex/pipelex-mcp) so AI agents can use pipelines as tools.

# 🚀 Quick start

> :books: Note that you can check out the [Pipelex Documentation](doc/Documentation.md) for more information and clone the [Pipelex Cookbook](https://github.com/Pipelex/pipelex-cookbook) repository for ready-to-run samples.

Follow these steps to get started:

## Installation

### Prerequisites

- Python ≥3.10
- [pip](https://pip.pypa.io/en/stable/), [poetry](https://python-poetry.org/), or [uv](https://github.com/astral-sh/uv) package manager

### Install the package

```bash
# Using pip
pip install pipelex

# Using Poetry
poetry add pipelex

# Using uv (Recommended)
uv pip install pipelex
```

## IDE extension

We **highly** recommend installing an extension for TOML files into your IDE of choice. For VS Code, the [Even Better TOML](https://marketplace.visualstudio.com/items?itemName=tamasfe.even-better-toml) extension does a great job of syntax coloring and checking.

### Optional Features

The package supports the following additional features:

- `anthropic`: Anthropic/Claude support
- `google`: Google models (Vertex) support
- `mistralai`: Mistral AI support
- `bedrock`: AWS Bedrock support
- `fal`: Image generation with Black Forest Labs "FAL" service

Install all extras:

Using `pip`:
```bash
pip install "pipelex[anthropic,google,mistralai,bedrock,fal]"
```

Using `poetry`:
```bash
poetry add "pipelex[anthropic,google,mistralai,bedrock,fal]"
```

Using `uv`:
```bash
uv pip install "pipelex[anthropic,google,mistralai,bedrock,fal]"
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on how to get started, including development setup and testing information.

## 👥 Join the Community

Join our vibrant Discord community to connect with other developers, share your experiences, and get help with your Pipelex projects!

[![Discord](https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/SReshKQjWt)

## 💬 Support

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and community discussions
- [**Documentation**](doc/Documentation.md)

## ⭐ Star Us!

If you find Pipelex helpful, please consider giving us a star! It helps us reach more developers and continue improving the tool.

## 📝 License

This project is licensed under the [MIT license](LICENSE). Runtime dependencies are distributed under their own licenses via PyPI.

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
