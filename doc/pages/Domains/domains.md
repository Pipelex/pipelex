# Domains in Pipelex

## What is a Domain?

A domain in Pipelex represents a topic or area of functionality within your library. Every library file must specify its domain, which helps organize and categorize your pipelines and concepts.

## Domain in Practice

When you create a library file (`.toml`), you always start by declaring its domain:

```toml
domain = "characters"                             # The domain name for this library
description = "Character generation and analysis"  # Optional description
system_prompt = "You are a book writer."          # Optional system prompt for all PipeLLM in this domain
```

### Domain Components

A domain consists of:

1. **Library File** (`.toml`):
   ```toml
   domain = "characters"
   
   [concept]
   Character = "A character is a fiction story"
   
   [pipe]
   [pipe.create_character]
   PipeLLM = "Create a character"
   output = "Character"
   ```

2. **Python Models** (`.py`):
   ```python
   from pipelex.core.stuff_content import StructuredContent
   
   class Character(StructuredContent):
       name: str
       age: int
       description: str
       gender: str
   ```

## Best Practices

1. **Naming**
   - Use clear, descriptive domain names
   - Keep names lowercase and simple
   - Use names that reflect the purpose (e.g., "characters", "locations")

2. **Organization**
   - One domain per topic/functionality
   - Match Python file names with domain names
   - Keep related concepts within the same domain

3. **Documentation**
   - Always add a description to your domain
   - Document concepts clearly
   - Include examples where helpful

## Using Domains

When using a domain in your code:

```python
from pipelex.core.stuff_factory import StuffFactory

# The concept_code combines domain and concept names
character_stuff = StuffFactory.make_stuff(
    concept_code="characters.Character",  # domain.ConceptName
    name="character",
    content=character_data
)
```

