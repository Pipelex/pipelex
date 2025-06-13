# Installation

## 📋 Prerequisites

Pipelex requires `python ≥3.10`, and access to LLM api keys, if you want to run pipelines locally, or an API key provided by Pipelex to use our cloud-hosted service.

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

- **Make sure you have a .env** file at the root of your project that contains the following fields

```bash
OPENAI_API_KEY=sk_...
```

- **Make sure your project looks like this:**

```bash
<your_repo>
├── pipelex.toml    # the config file for pipelex
├── .env                          # the .env file to put your API keys and other pipelex variables in
├── pipelex_libraries               # a directory to store your pipelex related code
│   ├── __init__.py
```

💡 _Any troubles? Have a look at our [Cookbook](https://github.com/Pipelex/pipelex-cookbook)!_

:arrow_right: [**Next section: Quick-start**](../Quick-start/Quick-start.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
