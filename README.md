<div align="center">
  <a href="https://www.pipelex.com/"><img src="https://raw.githubusercontent.com/Pipelex/pipelex/main/.github/assets/logo.png" alt="Pipelex Logo" width="400" style="max-width: 100%; height: auto;"></a>

  <h3 align="center">The simpler way to build reliable LLM Pipelines</h3>
  <p align="center">Pipelex is an open‑source dev tool based on a simple declarative language<br/>that lets you define replicable, structured, composable LLM pipelines.</p>

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
    <a href="https://pipelex.com"><img src="https://img.shields.io/badge/Web-pipelex.com-03bb95?logo=google-chrome&logoColor=white&style=flat" alt="Website"></a>
    <br/> 
    <br/>
</div>

<div align="center">
  <a href="https://www.pipelex.com/demo"><strong>Checkout our demo!</strong></a>
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

Pipelex™ is a developer tool designed to simplify building reliable AI applications. At its core is a clear, declarative pipeline language specifically crafted for knowledge-processing tasks.

**The Pipelex language uses pipelines,** or "pipes", each capable of integrating different language models (LLMs) or software to process knowledge. Pipes consistently deliver **structured, predictable outputs** at each stage.

Pipelex employs user-friendly TOML syntax, enabling developers to intuitively define workflows in a narrative-like manner. This approach facilitates collaboration between business professionals, developers, and language models (LLMs), ensuring clarity and ease of communication.

Pipes function like modular building blocks, **assembled by connecting other pipes sequentially, in parallel, or by calling sub-pipes.** This assembly resembles function calls in traditional programming but emphasizes a more intuitive, plug-and-play structure, focused explicitly on clear knowledge input and output.

Pipelex is distributed as an **open-source Python library,** with a hosted API launching soon, enabling effortless integration into existing software systems and automation frameworks. Additionally, Pipelex will provide an MCP server that will enable AI Agents to run pipelines like any other tool.

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

The package supports additional features that can be installed separately:

```bash
# Using pip
pip install "pipelex[anthropic]"    # For Anthropic/Claude support
pip install "pipelex[google]"       # For Google API support
pip install "pipelex[mistralai]"    # For Mistral AI support
pip install "pipelex[bedrock]"      # For AWS Bedrock support
pip install "pipelex[fal]"          # For image generation with Black Forest Labs "FAL" service

# Using poetry
poetry add "pipelex[anthropic,google,mistralai,bedrock,fal]"  # Install all features

# Using uv
uv pip install "pipelex[anthropic,google,mistralai,bedrock,fal]"
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on how to get started, including development setup and testing information.

## 💬 Support

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and community discussions
- [**Documentation**](doc/Documentation.md)

## ⭐ Star Us!

If you find Pipelex helpful, please consider giving us a star! It helps us reach more developers and continue improving the tool.

## 👥 Contributors

Contributions are welcome, check out our [Contributing to Pipelex](CONTRIBUTING.md) guide.

## 📝 License

This project is licensed under the [MIT license](LICENSE). Runtime dependencies are distributed under their own licenses via PyPI.

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
