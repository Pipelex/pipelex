# Writing Workflows

Ready to dive deeper? This section shows you how to manually create pipelines and understand the `.plx` language.

!!! tip "Prefer Automated Workflow Generation?"
    If you have access to **Claude 4.5 Sonnet** (via Pipelex Inference, Anthropic, Amazon Bedrock, or BlackBox AI), you can use our **pipe builder** to generate workflows from natural language descriptions. See the [Pipe Builder guide](./pipe-builder.md) to learn how to use `pipelex build pipe` commands. This tutorial is for those who want to write workflows manually or understand the `.plx` language in depth.

## Write Your First Pipeline

Let's build a **character generator** to understand the basics.
Create a `.plx` file anywhere in your project (we recommend a `pipelines` directory):

`character.plx`
```plx
domain = "characters"                    # domain of existance of your pipe

[pipe]
[pipe.create_character]                  # Declare the pipe and give it a code name
type = "PipeLLM"                         # Specify the type: Here, PipeLLM can provide LLM/vLLM calls.
description = "Creates a character."     # Give it a description in natural language
output = "Text"                          # Specify the output of the pipe: Here its will be plain text.
prompt = """                             # write your prompt
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""
```

This pipeline is a simple LLM call without any input, with the provided prompt and will output a `TextContent` object. See more about native concepts [here](../6-build-reliable-ai-workflows/concepts/define_your_concepts.md)

### Run Your First Pipelex Script

**CLI:**

```bash
pipelex run create_character
```

**Python:**

Create a Python file to execute the pipeline:

`character.py`
```python
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

# Initialize pipelex to load your pipeline libraries
Pipelex.make()

pipe_output = await execute_pipeline(
    pipe_code="create_character",
)

print(pipe_output.main_stuff_as_str)            # `main_stuff_as_str` is allowed here because the output is a `TextContent`
```

Then run the python file.

```bash
python character.py
```

### Get Your First Pipelex Result

![Example of a generated character sheet](./images/character_sheet.png)

As you might notice, this is plain text, and nothing is structured. Now we are going to see how to output a structured object instead of plain text.

## Generate Structured Outputs

Let's create a rigorously structured `Character` object instead of plain text. We need to create the concept `Character`. The concept names MUST be in PascalCase. [Learn more about defining concepts](../6-build-reliable-ai-workflows/concepts/define_your_concepts.md)

### Option 1: Define the Structure in your `.plx` file

Define structures directly in your `.plx` file:

```plx
[concept.Character]                                 # Declare the concept by giving it a name.
description = "A character in a fiction story"      # Give it a description in natural language.

[concept.Character.structure]                       # Define the structure
name = "The character's name"                       # First attribute: name, with the description in natural language "The character's name"
age = { type = "integer", description = "The character's age", required = true } # Second attribute: age, that is mandatory.
gender = "The character's gender"                   # Third attribute: "gender"
description = "A description of the character"      # Fourth attribute: "description"
```

### Now use your structured concept in your pipe

Specify that the output of your Pipellm is a `Character` object:

`characters.plx`
```plx
domain = "characters"

[concept.Character]
description = "A character in a fiction story"

[concept.Character.structure]
name = "The character's name"
age = { type = "integer", description = "The character's age", required = true }
gender = "The character's gender"
description = "A description of the character"

[pipe]
[pipe.create_character]
type = "PipeLLM"
description = "Create a character. Get a structured result."
output = "Character"                                 # <- This is the output concept for your pipe
prompt = """
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""
```

!!! tip "Concept Naming"
    The concept name matches the class name (`Character`), so Pipelex automatically links them.

!!! tip "Semantic Clarity"
    Defining concepts removes ambiguity—"character" could mean a letter or symbol, but here it clearly means a fictional person.


### Option 2: Define the Structure using Pydantic BaseModel

Using [Pydantic BaseModel](https://docs.pydantic.dev/latest/) syntax:

`characters.py`
```python
from pipelex.core.stuffs.structured_content import StructuredContent

# Define the structure of your output here
# This class MUST be a subclass of StructuredContent
class Character(StructuredContent):
    name: str
    age: int
    gender: str
    description: str
```

!!! tip "Keep Structure Files Clean"
    Keep your `StructuredContent` classes in dedicated files with minimal module-level code. Pipelex imports these modules during auto-discovery, so any module-level code will be executed.

Learn more in [Inline Structures](../6-build-reliable-ai-workflows/concepts/inline-structures.md) or [Python StructuredContent Classes](../6-build-reliable-ai-workflows/concepts/python-classes.md).

### Use your Structured Concept in Your Pipe

Specify that the output of your Pipellm is a `Character` object:

`characters.plx`
```plx
domain = "characters"

[concept]
Character = "A character in a fiction story"         # <- Declare your concept by giving it the same name as the python class

[pipe]
[pipe.create_character]
type = "PipeLLM"
description = "Create a character. Get a structured result."
output = "Character"                                 # <- This is the output concept for your pipe
prompt = """
You are a book writer. Your task is to create a character.
Think of it and then output the character description.
"""
```

!!! tip "Concept Naming"
    The concept name matches the class name (`Character`), so Pipelex automatically links them.

!!! tip "Semantic Clarity"
    Defining concepts removes ambiguity—"character" could mean a letter or symbol, but here it clearly means a fictional person.

#### Run Your Pipeline

The output is now a structured `Character` instance:

![Example of a generated character sheet with structure in JSON](./images/structured_character_sheet_json.png)

### Add variables in your prompt

Let's process existing characters and extract metadata from their descriptions. Let's imagine, that I have already an instance of the class `Character`. I would like to use it in a prompt in order to process that information, and extract some of the information.

For example, I would like to create and instance of `CharacterMetadata`, that contains the `name`, `age`, and height if it was provided in the description of the character. 


```plx
domain = "characters" 

[concept.Character]
description = "A character in a fiction story"

[concept.Character.structure]
name = "The character's name"
age = { type = "integer", description = "The character's age", required = true }
gender = "The character's gender"
description = "A description of the character"

[concept.CharacterMetadata]                     # <- Declare the new concept
description = "Metadata of a character"

[concept.CharacterMetadata.structure]           # <- Declare its structure
name = "The character's name"
age = { type = "integer", description = "The character's age", required = true }
height = { type = "number", description = "The characters' height" }

[pipe]
[pipe.extract_character_advanced]
type = "PipeLLM"
description = "Get character information from a description."
inputs = { character = "Character" }                         # <- These inputs are usable in the prompt
output = "CharacterMetadata"
prompt = """
You are given a text description of a character.
Your task is to extract specific data from the following description.

@character
"""
```

!!! tip "Template Syntax"
    Our template syntax is based on [Jinja2](https://jinja.palletsprojects.com/en/stable/). Use `@` prefix for tagging a variable in the prompt. Learn more about prompting with Pipelex in the [PipeLLM documentation](../6-build-reliable-ai-workflows/pipes/pipe-operators/PipeLLM.md). 

!!! tip "Template Variables"
    `@character.description` grabs the `character` stuff from the instance and uses its `description` attribute.

Learn more about Jinja in the [PipeLLM documentation](../../home/6-build-reliable-ai-workflows/pipes/pipe-operators/PipeLLM.md).

#### Execute from Python

`run_pipe.py`
```python
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

from character_model import CharacterMetadata

Pipelex.make()

inputs = {
    "character": {
        "concept": "character.Character",
        "content": {
            "name": "Elias",
            "age": 38,
            "gender": "man",
            "occupation": "explorer",
            "description": "Elias Varrin is a 38-year-old man, standing at approximately 1.85 meters tall, with a lean, weathered frame shaped by decades of travel through remote and often unforgiving landscapes. His name, though not widely known, carries weight among historians, explorers, and those who trade in whispered legends. Elias has piercing storm-gray eyes that scan every environment with sharp precision, and his ash-blond hair—flecked with early streaks of grey—is usually tucked beneath a wide-brimmed, timeworn hat."
        }
    }
}

# Run the pipe with loaded inputs
pipe_output = await execute_pipeline(
    pipe_code="extract_character_advances",
    inputs=inputs,
)

# Get the result as a properly typed instance
print(pipe_output)
```

### How to type the output ?

You can get an instance of the python class `CharacterMetadata` if you have created the concept with python:

`character_model.py`
```python
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

`run_pipe.py`
```python
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipelex import Pipelex

from character_model import CharacterMetadata

Pipelex.make()

inputs = {
    "character": {
        "concept": "character.Character",
        "content": {
            "name": "Elias",
            "age": 38,
            "gender": "man",
            "occupation": "explorer",
            "description": "Elias Varrin is a 38-year-old man, standing at approximately 1.85 meters tall, with a lean, weathered frame shaped by decades of travel through remote and often unforgiving landscapes. His name, though not widely known, carries weight among historians, explorers, and those who trade in whispered legends. Elias has piercing storm-gray eyes that scan every environment with sharp precision, and his ash-blond hair—flecked with early streaks of grey—is usually tucked beneath a wide-brimmed, timeworn hat."
        }
    }
}

# Run the pipe with loaded inputs
pipe_output = await execute_pipeline(
    pipe_code="extract_character_advances",
    inputs=inputs,
)

# Get the result as a properly typed instance
extracted_metadata = pipe_output.main_stuff_as(content_type=CharacterMetadata)
print(extracted_metadata)
```

#### Get Result

![Example of extracted character metadata](./images/extracted_character_metadata.png)

# Next Steps

Now that you understand the basics, explore more:

**Learn More about the PipeLLM:**

- [LLM Configuration: play with the models](../../home/6-build-reliable-ai-workflows/configure-ai-llm-to-optimize-workflows.md) - Optimize cost and quality
- [Full configuration of the PipeLLM](../../home/6-build-reliable-ai-workflows/pipes/pipe-operators/PipeLLM.md)

**Learn more about Pipelex (domains, project structure, best practices...)**

- [Build Reliable AI Workflows](../../home/6-build-reliable-ai-workflows/kick-off-a-pipelex-workflow-project.md) - Deep dive into pipeline design
- [Cookbook Examples](../../home/4-cookbook-examples/index.md) - Real-world examples and patterns

**Learn More about the other pipes** 

- [Pipe Operators](../../home/6-build-reliable-ai-workflows/pipes/pipe-operators/index.md) - PipeLLM, PipeExtract, PipeCompose, and more
- [Pipe Controllers](../../home/6-build-reliable-ai-workflows/pipes/pipe-controllers/index.md) - PipeSequence, PipeParallel, PipeBatch, PipeCondition

**Explore Tools:**

- [Pipe Builder](../../home/9-tools/pipe-builder.md) - Generate pipelines from natural language
- [Kit Commands](../../home/9-tools/kit.md) - Manage agent rules and migrations
- [CLI Commands](../../home/9-tools/cli.md) - Command-line interface reference

**Configure:**

- [Inference Backend](../../home/7-configuration/config-technical/inference-backend-config.md) - Configure model providers
