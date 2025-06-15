# Libraries

Pipelex organizes code into libraries, which are collections of related functionality stored in the `pipelex_libraries` directory.

## Library Structure

A Pipelex library consists of:

1. **Pipeline Definitions** (`pipelines/`)

    - TOML files defining domains, concepts, and pipes
    - Python files containing structured output models
    - Base library with common functionality

1. **Templates** (`templates/`)

    - Reusable prompt templates
    - Common patterns and configurations

1. **LLM Integrations** (`llm_integrations/`)

    - Provider-specific configurations
    - Platform settings

1. **LLM Configuration** (`llm_deck/`)

    - LLM model configurations
    - Preset definitions
    - See more in our [LLM Configuration Guide](../build-reliable-ai-workflows-with-pipelex/configure-ai-llm-to-optimize-workflows.md)

## Creating a Library

Every library file must belong to a domain. The domain helps organize your code and provides context for your concepts and pipes.

### Library File Structure

A typical library file looks like this:

```toml
domain = "tutorial"                             # Domain name (required)
description = "A tutorial library"              # Library description
system_prompt = "You are a book writer."        # Default system prompt for this domain

[concept]
Character = "A character is a fiction story"    # Concept definition

[pipe]
[pipe.create_character]
PipeLLM = "Create a character."                 # Pipe operator type
output = "Character"                            # Output concept
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
```

Learn more about domains in our [Domains Guide](../how-to-build-pipelex-pipelines/domains.md).

## Library Components

### 1. Domain Definition
Every library must specify its domain. This helps organize your code and provides context for your concepts and pipes.

### 2. Concepts
Concepts define the structured data types your library works with. They link to Python classes that implement the structure.

See more in our [Concepts Documentation](../how-to-build-pipelex-pipelines/concepts.md)

### 3. Pipes
Pipes define the operations your library can perform, such as generating text or processing data.

See more in our [Pipes Documentation](../how-to-build-pipelex-pipelines/pipes.md)

### 4. Operators
Pipelex provides various operators (PipeLLM, PipeOcr, etc.) that define how pipes process data.

See more in our [Pipelex Pipe Operators](../how-to-build-pipelex-pipelines/pipe-operators/index.md)

## Best Practices

1. **Organization**

    - Group related functionality into domains
    - Keep library files focused and well-documented
    - Use clear, descriptive names

2. **Documentation**

    - Add descriptions to domains and concepts
    - Document pipe behavior and requirements
    - Include examples where helpful

3. **Structure**

    - Follow the standard library layout
    - Keep related files together
    - Use consistent naming conventions
