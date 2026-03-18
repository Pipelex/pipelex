---
description: "Set up your first Pipelex project with .mthds files, define concepts and pipes, and build executable AI methods from scratch."
---

# Kicking off a Pipelex Method Project

## Creating Your First Pipeline

A pipeline in Pipelex is a collection of related concepts and pipes. Start by creating a MTHDS file in your project:

`tutorial.mthds`
```toml
domain = "tutorial"
description = "My first Pipelex library"
system_prompt = "You are a helpful assistant."

[concept]
Question = "A question that needs to be answered"
Answer = "A response to a question"

[pipe]
[pipe.answer_question]
type = "PipeLLM"
description = "Answer a question"
inputs = { question = "tutorial.Question" }
output = "tutorial.Answer"
prompt = """
Please answer the following question:

@question

Provide a clear and concise answer.
"""
```

This creates a simple Q&A pipeline with:

- A domain called "tutorial"
- Two concepts: Question and Answer
- One pipe that transforms a Question into an Answer

The `domain` property is the most important part of your pipeline file. It groups all your concepts and pipes into a single, easy to read bundle.

!!! info "Learn More About Domains"
    Domains are a core concept in Pipelex that organize your pipelines, concepts, and pipes into semantic namespaces. For a comprehensive guide on domains, see [Understanding Domains](./domain.md).

See more about designing pipes in [Designing Pipelines](./pipes/index.md).
See more about concepts in [Define Your Concepts](./concepts/define_your_concepts.md)
See more about domains in [Understanding Domains](./domain.md)

## File Naming Conventions

Consistent naming makes your pipeline code discoverable and maintainable:

### MTHDS Files
- Use lowercase with underscores: `legal_contracts.mthds`, `customer_service.mthds`
- Match the domain name when possible: domain "legal" → `legal.mthds`
- For multi-word domains, use underscores: domain "customer_service" → `customer_service.mthds`

See more about pipelex bundle specification in [Pipelex Bundle Specification](./pipelex-bundle-specification.md)

### Python Model Files
- It is recommended to name structure files with a `_struct.py` suffix: `legal.mthds` → `legal_struct.py`
- Pipelex will automatically discover and load structure classes from all Python files in your project (excluding common directories like `.venv`, `.git`, etc.)

## Project Structure

**Key principle:** Put `.mthds` files where they belong in YOUR codebase. Pipelex automatically finds them.

### Recommended Patterns

**Topic-Based (Best for organized codebases):**
```
your-project/
├── my_project/                # Your Python package
│   ├── finance/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── invoices.mthds          # Pipeline with finance code
│   │   └── invoices_struct.py    # Structure classes
│   └── legal/
│       ├── models.py
│       ├── contracts.mthds         # Pipeline with legal code
│       └── contracts_struct.py
├── .pipelex/                     # Config at repo root
│   ├── pipelex.toml
│   └── inference/
└── requirements.txt
```

**Centralized (If you prefer grouping pipelines):**
```
your-project/
├── my_project/
│   ├── pipelines/              # All pipelines together
│   │   ├── finance.mthds
│   │   ├── finance_struct.py
│   │   ├── legal.mthds
│   │   └── legal_struct.py
│   └── core/
│       └── (your code)
└── .pipelex/
```

**Flat (Small projects):**
```
your-project/
├── my_project/
│   ├── invoice_pipeline.mthds
│   ├── invoice_struct.py
│   └── main.py
└── .pipelex/
```

### Key Points

- **Flexible placement**: `.mthds` files work anywhere in your project
- **Automatic discovery**: Pipelex scans and finds them automatically
- **Configuration location**: `.pipelex/` stays at repository root
- **Naming convention**: Use `_struct.py` suffix for structure files
- **Excluded directories**: `.venv`, `.git`, `__pycache__`, `node_modules` are skipped
- **Best practice**: Keep related pipelines with their related code
