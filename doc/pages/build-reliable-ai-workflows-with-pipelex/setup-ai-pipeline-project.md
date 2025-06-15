# Setting Up Your Pipeline Project

## Project Structure

Every Pipelex project follows a simple directory structure that keeps your knowledge pipelines organized and maintainable:

```
your-project/
├── pipelex_libraries/          # All your pipeline code lives here
│   ├── pipelines/             # Pipeline definitions and models
│   │   ├── __init__.py
│   │   ├── characters.toml    # Domain definitions
│   │   └── characters.py      # Python models for concepts
│   ├── templates/             # Reusable prompt templates
│   ├── llm_integrations/      # LLM provider configurations
│   └── llm_deck/              # LLM model presets
├── main.py                    # Your application code
└── requirements.txt           # Python dependencies
```

The `pipelex_libraries` directory is where Pipelex looks for your pipeline definitions. This standardized structure means you can share libraries between projects, version control them separately, and maintain clean separation between your pipeline logic and application code.

## Creating Your First Library

A library in Pipelex is a collection of related concepts and pipes. Start by creating a TOML file in the `pipelines` directory:

```toml
# pipelex_libraries/pipelines/tutorial.toml

domain = "tutorial"
description = "My first Pipelex library"
system_prompt = "You are a helpful assistant."

[concept]
Question = "A question that needs to be answered"
Answer = "A response to a question"

[pipe]
[pipe.answer_question]
PipeLLM = "Answer a question"
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

## Organizing Libraries and Domains

Think of domains as namespaces for your pipeline functionality. Each domain represents a distinct area of knowledge processing:

```
pipelex_libraries/pipelines/
├── legal.toml          # Domain: legal document processing
├── legal.py            # Models for legal concepts
├── finance.toml        # Domain: financial analysis
├── finance.py          # Models for financial concepts
├── content.toml        # Domain: content generation
└── content.py          # Models for content concepts
```

**Domain Guidelines:**

1. **One domain per file**: Each TOML file defines exactly one domain
2. **Focused scope**: Keep domains focused on a specific area (legal, finance, content)
3. **Shared models**: The corresponding Python file contains all structured models for that domain
4. **Clear boundaries**: If concepts don't naturally fit together, they belong in different domains

Example of multiple related concepts in one domain:

```toml
# pipelex_libraries/pipelines/legal.toml

domain = "legal"
description = "Legal document analysis and processing"

[concept]
Contract = "A legally binding agreement between parties"
NonCompeteClause = "A clause restricting competitive activities"
Jurisdiction = "The legal authority under which the contract operates"
ContractSummary = "A concise overview of key contract terms"

[pipe]
[pipe.extract_non_compete]
PipeLLM = "Extract non-compete clauses from a contract"
inputs = { contract = "legal.Contract" }
output = "legal.NonCompeteClause"

[pipe.summarize_contract]
PipeLLM = "Create a summary of contract key points"
inputs = { contract = "legal.Contract" }
output = "legal.ContractSummary"
```

## File Naming Conventions

Consistent naming makes your pipeline code discoverable and maintainable:

### TOML Files
- Use lowercase with underscores: `legal_contracts.toml`, `customer_service.toml`
- Match the domain name when possible: domain "legal" → `legal.toml`
- For multi-word domains, use underscores: domain "customer_service" → `customer_service.toml`

### Python Model Files
- Must match the TOML filename exactly: `legal.toml` → `legal.py`
- This convention allows Pipelex to automatically find your models

### Concept Names
- Use PascalCase: `Contract`, `NonCompeteClause`, `CustomerProfile`
- Be descriptive but concise
- Avoid generic names like `Data` or `Result`

### Pipe Names
- Use snake_case: `extract_non_compete`, `analyze_sentiment`, `generate_summary`
- Start with a verb that describes the action
- Be specific about what the pipe does

### Stuff Names (in code)
- Use snake_case: `input_contract`, `customer_question`, `analysis_result`
- Describe what the stuff contains, not its type
- Keep names consistent across your pipeline

**Example showing all conventions together:**

```toml
# pipelex_libraries/pipelines/customer_service.toml
domain = "customer_service"

[concept]
CustomerQuery = "A question or concern from a customer"
SentimentAnalysis = "Analysis of emotional tone and urgency"

[pipe]
[pipe.analyze_customer_sentiment]
PipeLLM = "Analyze the sentiment of customer communication"
inputs = { query = "customer_service.CustomerQuery" }
output = "customer_service.SentimentAnalysis"
```

```python
# pipelex_libraries/pipelines/customer_service.py
from pipelex.core.stuff_content import StructuredContent

class CustomerQuery(StructuredContent):
    text: str
    customer_id: str
    timestamp: datetime

class SentimentAnalysis(StructuredContent):
    sentiment: Literal["positive", "neutral", "negative"]
    urgency: Literal["low", "medium", "high"]
    key_concerns: List[str]
```

With this structure in place, you're ready to start building your knowledge pipelines.
