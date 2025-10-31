# Kicking off a Pipelex Workflow Project

## Creating Your First Pipeline

A pipeline in Pipelex is a collection of related concepts and pipes. Start by creating a PLX file in your project:

```plx
# tutorial.plx

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

## What Are Domains?

A domain in Pipelex represents a topic or area of functionality within your pipeline. Every pipeline file must specify its domain, which helps organize and categorize your pipes and concepts.

### Domain in Practice

When you create a pipeline file (`.plx`), you always start by declaring its domain:

```plx
domain = "finance"                                      # The domain name for this file
description = "Financial document processing"            # Optional description
system_prompt = "You are an expert financial analyst."  # Optional system prompt for all PipeLLM in this domain
```

A domain consists of:

1.  **Pipeline File** (`.plx`)
    ```plx
    domain = "finance"
   
    [concept]
    Invoice = "A commercial document for a sale of products or services"
    InvoiceSummary = "A summary of an invoice with key details"
   
    [pipe]
    [pipe.summarize_invoice]
    type = "PipeLLM"
    description = "Summarize an invoice to extract key information"
    inputs = { invoice = "finance.Invoice" }
    output = "finance.InvoiceSummary"
    ```

2.  **Python Models** (`.py`)
    ```python
    from pipelex.core.stuffs.structured_content import StructuredContent
    from pydantic import Field
    from typing import List
    from datetime import date

    class Invoice(StructuredContent):
        invoice_number: str
        vendor: str
        customer: str
        total_amount: float = Field(ge=0)
        issue_date: date
        line_items: List[str]

    class InvoiceSummary(StructuredContent):
        vendor: str
        total_amount: float
        is_overdue: bool
    ```

### Best Practices

1.  **Naming**
    - Use clear, descriptive domain names.
    - Keep names lowercase and simple.
    - Use names that reflect the purpose (e.g., "finance", "legal", "content_creation").

2.  **Organization**
    - One domain per topic/functionality.
    - Use `_struct.py` suffix for structure files (`finance.plx` -> `finance_struct.py`).
    - Keep related concepts within the same domain.
    - Place your `.plx` files anywhere in your project - Pipelex automatically discovers them.
    - Keep `.pipelex/` configuration directory at repository root.

3.  **Documentation**
    - Always add a description to your domain.
    - Document concepts clearly.
    - Include examples where helpful.

### Using Domains

When using a domain in your code, you refer to concepts with `domain.ConceptName`:

```python
from pipelex.core.stuffs.stuff_factory import StuffFactory

# The concept_code combines domain and concept names
invoice_stuff = StuffFactory.make_from_concept_string(
    concept_string="finance.Invoice",  # domain.ConceptName
    name="invoice_123",
    content=invoice_data # dictionary or Invoice object
)
```

## File Naming Conventions

Consistent naming makes your pipeline code discoverable and maintainable:

### PLX Files
- Use lowercase with underscores: `legal_contracts.plx`, `customer_service.plx`
- Match the domain name when possible: domain "legal" → `legal.plx`
- For multi-word domains, use underscores: domain "customer_service" → `customer_service.plx`

### Python Model Files
- It is recommended to name structure files with a `_struct.py` suffix: `legal.plx` → `legal_struct.py`
- Pipelex will automatically discover and load structure classes from all Python files in your project (excluding common directories like `.venv`, `.git`, etc.)

## Project Structure

**Key principle:** Put `.plx` files where they belong in YOUR codebase. Pipelex automatically finds them.

### Recommended Patterns

**Topic-Based (Best for organized codebases):**
```
your-project/
├── my_project/                # Your Python package
│   ├── finance/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── invoices.plx          # Pipeline with finance code
│   │   └── invoices_struct.py    # Structure classes
│   └── legal/
│       ├── models.py
│       ├── contracts.plx         # Pipeline with legal code
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
│   │   ├── finance.plx
│   │   ├── finance_struct.py
│   │   ├── legal.plx
│   │   └── legal_struct.py
│   └── core/
│       └── (your code)
└── .pipelex/
```

**Flat (Small projects):**
```
your-project/
├── my_project/
│   ├── invoice_pipeline.plx
│   ├── invoice_struct.py
│   └── main.py
└── .pipelex/
```

### Key Points

- **Flexible placement**: `.plx` files work anywhere in your project
- **Automatic discovery**: Pipelex scans and finds them automatically
- **Configuration location**: `.pipelex/` stays at repository root
- **Naming convention**: Use `_struct.py` suffix for structure files
- **Excluded directories**: `.venv`, `.git`, `__pycache__`, `node_modules` are skipped
- **Best practice**: Keep related pipelines with their related code
