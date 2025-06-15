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

The `domain` property is the most important part of your library file. It groups all your concepts and pipes into a single, addressable unit. Learn more about how to use them in [What Are Domains?](what-are-domains.md).

## Organizing Your Libraries

As your project grows, you'll create multiple library files. Each file should contain a single domain with its related concepts and pipes. This helps keep your knowledge organized and easy to manage.

For more details on how to structure your domains, see [What Are Domains?](what-are-domains.md).

## File Naming Conventions

Consistent naming makes your pipeline code discoverable and maintainable:

### TOML Files
- Use lowercase with underscores: `legal_contracts.toml`, `customer_service.toml`
- Match the domain name when possible: domain "legal" → `legal.toml`
- For multi-word domains, use underscores: domain "customer_service" → `customer_service.toml`

### Python Model Files
- It is recommended to match the TOML filename exactly: `legal.toml` → `legal.py`
- But in any case, Pipelex will load models from all python modules in the `pipelines` directory or its subdirectories.
