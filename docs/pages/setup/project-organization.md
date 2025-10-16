# Project Organization

## Overview

Pipelex automatically discovers `.plx` pipeline files anywhere in your project (excluding `.venv`, `.git`, `node_modules`, etc.).

## Recommended: Keep pipelines with related code

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
├── .pipelex/                      # Config at repo root
│   └── pipelex.toml
├── .env                           # API keys (git-ignored)
└── requirements.txt
```

## Alternative: Centralize pipelines

```bash
your_project/
├── pipelines/
│   ├── invoices.plx
│   ├── contracts.plx
│   └── structures.py
└── .pipelex/
    └── pipelex.toml
```

Learn more in our [Project Structure documentation](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md).

---

## Prerequisites

- **Python**: Version 3.10 or above
- **API Access**: One of the three options from [Configure AI Providers](configure-ai-providers.md) (Pipelex Inference, your own keys, or local AI)

---

## Next Steps

Now that you understand project organization:

1. **Start building**: [Get Started](../../index.md)
2. **Learn the concepts**: [Full Tutorial](../quick-start/index.md)
3. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook)
4. **Deep dive**: [Build Reliable AI Workflows](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md)

