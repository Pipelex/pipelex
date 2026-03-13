---
description: "Learn how to structure your Pipelex project so that .mthds files, Python code, and executable AI methods stay organized and easy to maintain."
---

# Project Organization

## Overview

Pipelex automatically discovers `.mthds` pipeline files anywhere in your project (excluding `.venv`, `.git`, `node_modules`, etc.).

## Recommended: Keep pipelines with related code

```bash
your_project/
├── METHODS.toml                   # Package manifest (optional)
├── my_project/                    # Your Python package
│   ├── finance/
│   │   ├── services.py
│   │   ├── invoices.mthds           # Pipeline with finance code
│   │   └── invoices_struct.py     # Structure classes
│   └── legal/
│       ├── services.py
│       ├── contracts.mthds          # Pipeline with legal code
│       └── contracts_struct.py
├── .pipelex/                      # Config at repo root
│   └── pipelex.toml
├── .env                           # API keys (git-ignored)
└── requirements.txt
```

- **Package manifest**: `METHODS.toml` at your project root declares package identity and pipe visibility. See [Packages](../building-methods/packages.md) for details.

## Alternative: Centralize pipelines

```bash
your_project/
├── pipelines/
│   ├── invoices.mthds
│   ├── contracts.mthds
│   └── structures.py
└── .pipelex/
    └── pipelex.toml
```

Learn more in our [Project Structure documentation](../building-methods/kick-off-a-methods-project.md).

---

## Prerequisites

- **Python**: Version 3.10 or above
- **API Access**: One of the three options from [Configure AI Providers](./configure-ai-providers.md) (Pipelex Inference, your own keys, or local AI)

---

## Next Steps

Now that you understand project organization:

1. **Start building**: [Get Started](../get-started/write-methods-manually.md)
2. **Learn the concepts**: [Writing Methods Tutorial](../get-started/write-methods-manually.md)
3. **Explore examples**: [Cookbook Repository](https://github.com/Pipelex/pipelex-cookbook/tree/main)
4. **Deep dive**: [Build Reliable AI Methods](../building-methods/kick-off-a-methods-project.md)

