# Installation

## Prerequisites

Pipelex requires `python` version `3.10` or above, and access to an LLM, via an API key or a custom endpoint.

## Getting Started

Along with our [Quick Start Guide](../quick-start/index.md), we recommend you check out our [Cookbook](https://github.com/Pipelex/pipelex-cookbook) for practical examples.

- **Create a virtual environment** (recommended)

```bash
python3 -m venv .venv && source .venv/bin/activate
```

 - **Install Pipelex**

Pipelex can be installed from PyPI. We encourage the use of [uv](https://github.com/astral-sh/uv) for faster installs and dependency management:

```bash
uv pip install pipelex
```

Otherwise use pip:
```bash
pip install pipelex
```

- **Make sure you have a .env** file at the root of your project that contains the following fields

```bash
OPENAI_API_KEY=sk_...
```

All the secret keys used by `pipelex` are specified in the `.env.example` file. However, by default, only the `OPENAI_API_KEY` is required.


- **Make sure you run the init commands:**

In order to set the pipelex configuration files, you need to run 2 commands using the CLI (we recommend to run it at the root of your project):

- `pipelex init libraries`: This will create a `pipelex_libraries` folder, with the base llm configuration and the base pipelines. 
This is the directory where you should add your pipelines. 

The structure is like this:

```bash
├── pipelex_libraries           
│   ├── __init__.py
│   ├── pipelines/                          # The pipelines and the structured output are stored here
│   │   ├── __init__.py
│   │   └── base_library/                   # The base library with basic pipelines
│   ├── templates/                          # Those are template prompt libraries
│   ├── llm_deck/                           # A llm deck is a simple way to name a llm and its configuration.
│   └── llm_integrations/                   # This directory regroups the configuration of the different models
```

Learn more about pipelex_libraries in our [Libraries documentation](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md)

- `pipelex init config`: This cli command will create a `pipelex.toml` file at the root of the project, with basic configuration. This configuration file gathers all configuration for feature flags, logging, cost reporting, and so on... Learn more in our [Configuration documentation](../configuration/index.md)


💡 _Any troubles? Have a look at our [Cookbook](https://github.com/Pipelex/pipelex-cookbook)! 
<!-- and come ask for help on our [Discord](https://go.pipelex.com/discord)_ -->
