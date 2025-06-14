# Installation

## 📋 Prerequisites

Pipelex requires `python ≥ 3.10`, API keys in your environment file, or the API key to Pipelex API (coming soon).

## 🧭 Getting Started

Everything you need to discover and test Pipelex is available in our **Getting Started repository**.
Along with [our Documentation](../Quick-start/Quick-start.md), we recommend you review it before any further usage: [Cookbook](https://github.com/Pipelex/pipelex-cookbook).

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

All the secret keys used by `pipelex` are specified in the `.env.example` file. However by default, only the `OPENAI_API_KEY` is required.


- **Make sure you run the init commands:**

In order to set the pipelex configuration files, you need to run 2 commands using the CLI (we recommand to run it at the root of you r project):

- `pipelex init-libraries`: This will create in the dir where the cli was run a folder `pipelex_libraries`, with the base llm configation and the bse pipelines. 
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

Learn more about pipelex_libraries in our [Libraries documentation](../Libraries/libraries.md)

- `pipelex init-config`: This cli command will create a `pipelex.toml` file at the root of the project, with basic configuration. This configuration file gathers all configuration for feature flags, logging, cost reporting, and so on... Learn more in our [Configuration documentation](../Configuration/configuration.md)


💡 _Any troubles? Have a look at our [Cookbook](https://github.com/Pipelex/pipelex-cookbook)!_
