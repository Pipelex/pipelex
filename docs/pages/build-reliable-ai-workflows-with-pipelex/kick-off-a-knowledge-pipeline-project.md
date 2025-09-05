# Kicking off a Knowledge Pipeline Project

## Creating Your First Pipeline

A pipeline in Pipelex is a collection of related concepts and pipes. Start by creating a PLX file in the `pipelines` directory:

```plx
# pipelex_libraries/pipelines/tutorial.plx

domain = "tutorial"
definition = "My first Pipelex library"
system_prompt = "You are a helpful assistant."

[concept]
Question = "A question that needs to be answered"
Answer = "A response to a question"

[pipe]
[pipe.answer_question]
type = "PipeLLM"
definition = "Answer a question"
inputs = { question = "tutorial.Question" }
output = "tutorial.Answer"
prompt_template = """
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
definition = "Financial document processing"            # Optional description
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
    definition = "Summarize an invoice to extract key information"
    inputs = { invoice = "finance.Invoice" }
    output = "finance.InvoiceSummary"
    ```

2.  **Python Models** (`.py`)
    ```python
    from pipelex.core.stuffs.stuff_content import StructuredContent
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
    - Match Python file names with domain names (`finance.plx` -> `finance.py`).
    - Keep related concepts within the same domain.

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
- It is recommended to match the PLX filename exactly: `legal.plx` → `legal.py`
- But in any case, Pipelex will load models from all python modules in the `pipelines` directory or its subdirectories.

## Project Structure

Every Pipelex project follows a simple directory structure that keeps your knowledge pipelines organized and maintainable:

```
your-project/
├── pipelex_libraries/         # All your pipeline code lives here
│   ├── pipelines/             # Pipeline definitions and models
│   │   ├── __init__.py
│   │   ├── characters.plx     # Domain definitions
│   │   └── characters.py      # Python models for concepts
│   ├── templates/             # Reusable prompt templates
│   ├── llm_integrations/      # LLM provider configurations
│   └── llm_deck/              # LLM model presets
├── main.py                    # Your application code
└── requirements.txt           # Python dependencies
```

The `pipelex_libraries/pipelines` directory is where Pipelex looks for your pipeline definitions. This standardized structure means you can share libraries between projects, version control them separately, and maintain clean separation between your pipeline logic and application code.
