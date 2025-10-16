# Quick-start

## Understanding How It Works

Ready to dive deeper? This section shows you how to manually create pipelines and understand the `.plx` language.

### Your First LLM Call with Pipelex

Let's build a **character generator** to understand the basics.

#### Write Your First Pipeline

Create a `.plx` file anywhere in your project (we recommend a `pipelines` directory):

`character.plx`
```plx
domain = "characters"

[pipe]
[pipe.create_character]
type = "PipeLLM"
description = "Creates a character."
output = "Text"
prompt = """
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""
```

This pipeline:

- Declares a `characters` domain
- Defines a `create_character` pipe of type `PipeLLM`
- Outputs plain `Text`
- Uses a simple prompt

#### Run Your First Pipelex Script

Create a Python file to execute the pipeline:

`character.py`
```python
import asyncio
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

async def create_character():
    # Run the script with execute_pipe
    pipe_output = await execute_pipeline(
        pipe_code="create_character",
    )
    # Print the output
    print(pipe_output.main_stuff_as_str)

# Initialize pipelex to load your pipeline libraries
Pipelex.make()

# Run using asyncio because our APIs are all async 
asyncio.run(create_character())
```

#### Get Your First Pipelex Result

```bash
python character.py
```

![Example of a generated character sheet](character_sheet.png)

### Using Specific LLMs

#### Indicate Your LLM Selection Explicitly

```plx
[pipe.create_character]
type = "PipeLLM"
description = "Create a character."
output = "Text"
model = { model = "gpt-4o-mini", temperature = 0.9, max_tokens = "auto" }
prompt = """
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""
```

#### Or Use an LLM Preset from the LLM Deck

```plx
[pipe.create_character]
type = "PipeLLM"
description = "Create a character."
output = "Text"
model = "llm_for_creative_writing"
prompt = """
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""

# The llm choice above is defined in `.pipelex/inference/deck/base_deck.toml` as:
# llm_for_creative_writing = { model = "best-claude", temperature = 0.9 }
# it's a base preset that we provide. you can add your own presets, too.
```

💡 We have many [LLM presets available by default](https://github.com/Pipelex/pipelex/tree/main/.pipelex/inference/deck/base_deck.toml).

Learn more in our [LLM Configuration Guide](../build-reliable-ai-workflows-with-pipelex/configure-ai-llm-to-optimize-workflows.md).

### Generate Structured Outputs

Let's create a rigorously structured `Character` object instead of plain text.

#### Define the Structure

Using [Pydantic BaseModel](https://docs.pydantic.dev/latest/) syntax:

`characters.py`
```python
from pipelex.core.stuffs.structured_content import StructuredContent

# Define the structure of your output here
# This class must inherit from StructuredContent
class Character(StructuredContent):
    name: str
    age: int
    gender: str
    description: str
```

!!! tip "Keep Structure Files Clean"
    Keep your `StructuredContent` classes in dedicated files with minimal module-level code. Pipelex imports these modules during auto-discovery, so any module-level code will be executed.

💡 **Alternative: Inline Structure Definition**

Define structures directly in your `.plx` file:

```plx
[concept.Character]
description = "A character in a fiction story"

[concept.Character.structure]
name = "The character's name"
age = { type = "integer", description = "The character's age", required = true }
gender = "The character's gender"
description = "A description of the character"
```

Learn more in [Structuring Concepts](../build-reliable-ai-workflows-with-pipelex/structuring-concepts.md).

#### Improve the Pipeline

Specify that your output is a `Character` instance:

`characters.plx`
```plx
domain = "characters"

[concept]
Character = "A character in a fiction story" # <- Define your output concept

[pipe]
[pipe.create_character]
type = "PipeLLM"
description = "Create a character. Get a structured result."
output = "Character"    # <- This is the output concept for your pipe
prompt = """
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""
```

💡 The concept name matches the class name (`Character`), so Pipelex automatically links them.

💡 Defining concepts removes ambiguity—"character" could mean a letter or symbol, but here it clearly means a fictional person.

#### Run Your Pipeline

The output is now a structured `Character` instance:

![Example of a generated character sheet with structure in JSON](structured_character_sheet_json.png)

### Using Prompt Templates

Pass data into prompts using templates.

Let's process existing characters and extract metadata from their descriptions.

#### Define the Output Structure

```python
# character_model.py
from pipelex.core.stuffs.structured_content import StructuredContent

# input class
class Character(StructuredContent):
    name: str
    age: int
    gender: str
    occupation: str
    description: str

# output class
class CharacterMetadata(StructuredContent):
    name: str
    age: int
    height: float
```

#### Use a Template to Fill Prompts with Data

💡 Our template syntax is based on [Jinja2](https://jinja.palletsprojects.com/en/stable/). Use `{{ double.curly.braces }}` or the simpler `@` prefix (recommended).

```plx
[concept]
Character = "A character from a book"
CharacterMetadata = "Metadata regarding a character."

[pipe]
[pipe.extract_character_1]
type = "PipeLLM"
description = "Get character information from a description."
inputs = { character = "Character" }  # <- These inputs are usable in the prompt
output = "CharacterMetadata"
prompt = """
You are given a text description of a character.
Your task is to extract specific data from the following description.

@character.description
"""
```

💡 `@character.description` grabs the `character` stuff from working memory and uses its `description` attribute.

Learn more about Jinja in the [PipeLLM documentation](../build-reliable-ai-workflows-with-pipelex/pipe-operators/PipeLLM.md).

#### Execute from Python

```python
import asyncio

from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

from character_model import Character, CharacterMetadata


async def process_existing_character():
    # Your existing data
    character = Character(
        name="Elias",
        age=38,
        gender="man",
        occupation="explorer",
        description="""Elias Varrin is a 38-year-old man, standing at approximately 1.85 meters tall, with a lean,
        weathered frame shaped by decades of travel through remote and often unforgiving landscapes.
        His name, though not widely known, carries weight among historians, explorers, and those who trade in whispered legends.
        Elias has piercing storm-gray eyes that scan every environment with sharp precision, and his ash-blond hair—flecked with
        early streaks of grey—is usually tucked beneath a wide-brimmed, timeworn hat.His hands are etched with fine scars and stained
        with ink, each mark a silent record of years spent charting unrecorded lands and handling fragile relics of lost civilizations.
        He moves with quiet purpose and speaks with a calm, thoughtful cadence that suggests he's always listening for more than just what's said.""",
    )
    # Wrap it into a stuff object
    character_stuff = StuffFactory.make_from_concept_string(
        concept_string="character.Character", # <- `character` is the domain, `Character` is the concept name
        name="character",
        content=character,
    )
    # Add it to the working memory
    working_memory = WorkingMemoryFactory.make_from_single_stuff(
        stuff=character_stuff,
    )
    # Run the pipe identified by its pipe_code (it's the name of the pipe)
    pipe_output = await execute_pipeline(
        pipe_code="extract_character_1",
        working_memory=working_memory,
    )

    # Get the result as a properly typed instance
    extracted_metadata = pipe_output.main_stuff_as(content_type=CharacterMetadata) # <- This is the output of your pipe, properly typed

    print(extracted_metadata)


Pipelex.make()
asyncio.run(process_existing_character())
```

#### Get Result

![Example of extracted character metadata](extracted_character_metadata.png)

---

## Next Steps

Now that you understand the basics, explore more:

**Learn More:**

- [Cookbook Examples](../cookbook-examples/index.md) - Real-world examples and patterns
- [Build Reliable AI Workflows](../build-reliable-ai-workflows-with-pipelex/kick-off-a-knowledge-pipeline-project.md) - Deep dive into pipeline design
- [Pipe Operators](../build-reliable-ai-workflows-with-pipelex/pipe-operators/index.md) - PipeLLM, PipeExtract, PipeCompose, and more
- [Pipe Controllers](../build-reliable-ai-workflows-with-pipelex/pipe-controllers/index.md) - PipeSequence, PipeParallel, PipeBatch, PipeCondition

**Explore Tools:**

- [Pipe Builder](../tools/pipe-builder.md) - Generate pipelines from natural language
- [Kit Commands](../tools/kit.md) - Manage agent rules and migrations
- [CLI Commands](../tools/cli.md) - Command-line interface reference

**Configure:**

- [LLM Configuration](../build-reliable-ai-workflows-with-pipelex/configure-ai-llm-to-optimize-workflows.md) - Optimize cost and quality
- [Inference Backend](../configuration/config-technical/inference-backend-config.md) - Configure model providers

[![Cookbook](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/)
