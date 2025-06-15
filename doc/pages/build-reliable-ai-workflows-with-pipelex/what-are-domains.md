# What Are Domains?

A domain in Pipelex represents a topic or area of functionality within your library. Every library file must specify its domain, which helps organize and categorize your pipelines and concepts.

## Domain in Practice

When you create a library file (`.toml`), you always start by declaring its domain:

```toml
domain = "finance"                                # The domain name for this library
description = "Financial document processing"     # Optional description
system_prompt = "You are an expert financial analyst." # Optional system prompt for all PipeLLM in this domain
```

### Domain Components

A domain consists of:

1.  **Library File** (`.toml`)
    ```toml
    domain = "finance"
   
    [concept]
    Invoice = "A commercial document for a sale of products or services"
    InvoiceSummary = "A summary of an invoice with key details"
   
    [pipe]
    [pipe.summarize_invoice]
    PipeLLM = "Summarize an invoice to extract key information"
    inputs = { invoice = "finance.Invoice" }
    output = "finance.InvoiceSummary"
    ```

2.  **Python Models** (`.py`)
    ```python
    from pipelex.core.stuff_content import StructuredContent
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

## Best Practices

1.  **Naming**
    - Use clear, descriptive domain names.
    - Keep names lowercase and simple.
    - Use names that reflect the purpose (e.g., "finance", "legal", "content_creation").

2.  **Organization**
    - One domain per topic/functionality.
    - Match Python file names with domain names (`finance.toml` -> `finance.py`).
    - Keep related concepts within the same domain.

3.  **Documentation**
    - Always add a description to your domain.
    - Document concepts clearly.
    - Include examples where helpful.

## Using Domains

When using a domain in your code, you refer to concepts with `domain.ConceptName`:

```python
from pipelex.core.stuff_factory import StuffFactory

# The concept_code combines domain and concept names
invoice_stuff = StuffFactory.make_stuff(
    concept_code="finance.Invoice",  # domain.ConceptName
    name="invoice_123",
    content=invoice_data # dictionary or Invoice object
)
``` 