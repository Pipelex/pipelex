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


- **Initialize configuration:**

To set up the Pipelex configuration files, run this command at the root of your project:

- `pipelex init config`: This CLI command will create a `.pipelex/` directory with configuration files including `pipelex.toml`. This configuration file contains settings for feature flags, logging, cost reporting, and more. Learn more in our [Configuration documentation](../configuration/index.md)

- **Create your pipelines:**

You can now create `.plx` pipeline files **anywhere** in your project. Pipelex automatically discovers them (excluding `.venv`, `.git`, `node_modules`, etc.).

**Keep pipelines with related code** - that's usually the best organization:

```bash
your_project/
├── my_project/             # Your Python package
│   ├── finance/
│   │   ├── services.py
│   │   ├── invoices.plx           # Pipeline with finance code
│   │   └── invoices_struct.py     # Structure classes
│   └── legal/
│       ├── services.py
│       ├── contracts.plx          # Pipeline with legal code
│       └── contracts_struct.py
├── .pipelex/                      # Config at repo root (created by init config)
│   └── pipelex.toml
└── requirements.txt
```

Or centralize if you prefer: `my_project/pipelines/*.plx`

Learn more about flexible organization in our [Project Structure documentation](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md)


💡 _Any troubles? Have a look at our [Cookbook](https://github.com/Pipelex/pipelex-cookbook)! 
<!-- and come ask for help on our [Discord](https://go.pipelex.com/discord)_ -->
