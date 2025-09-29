# Quick-start

This guide shows the basics of Pipelex for the simplest use-cases: LLM calling and structured outputs.

You can **find more powerful examples** in the [Cookbook Examples](../cookbook-examples/index.md) section of the docs or dive directly into the [Cookbook repository](https://github.com/Pipelex/pipelex-cookbook). [![GitHub](https://img.shields.io/badge/Cookbook-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/)

---

## Setting up API Keys

Before you can make LLM calls with Pipelex, you need to configure API keys. You have two options:

### Option 1: Use Pipelex Inference (Recommended for Getting Started)

Get **free access** to all well-known commercial and open-source LLMs with a single API key:

1. **Join our Discord community to get your free Pipelex Inference key** (no credit card required, limited time offer)
   - Visit [https://go.pipelex.com/discord](https://go.pipelex.com/discord) to join
   - Request your API key in the appropriate channel once you're in

2. **Set up your environment**:
   ```bash
   # Create a .env file in your project root
   echo "PIPELEX_INFERENCE_API_KEY=your-key-here" > .env
   ```

With Pipelex Inference, you get instant access to models from OpenAI, Anthropic, Google, Mistral, and more - all through a single API key!

### Option 2: Use Your Own API Keys

If you already have API keys from LLM providers, you can use them directly:

```bash
# Add to your .env file
# To directly use models on OpenAI, you will need to set the following variable
OPENAI_API_KEY=your-openai-key
# To directly use models on Anthropic, you will need to set the following variable
ANTHROPIC_API_KEY=your-anthropic-key
# To directly use models on Google, you will need to set the following variable
GOOGLE_API_KEY=your-google-key
# To directly use models on Mistral, you will need to set the following variable
MISTRAL_API_KEY=your-mistral-key
# To directly use models on FAL, you will need to set the following variable
FAL_API_KEY=your-fal-key
# To directly use models on XAI, you will need to set the following variable
XAI_API_KEY=your-xai-key

# To use models via Ollama, you will need to set the following variables
OLLAMA_API_KEY=your-ollama-key
# To use models via BlackboxAI, you will need to set the following variables
BLACKBOX_API_KEY=your-blackboxai-key
# To use models via Azure OpenAI, you will need to set the following variables
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=your-azure-endpoint
AZURE_API_VERSION=your-azure-version
# To use models via AWS Bedrock, you will need to set the following variables
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_REGION=your-aws-region
```

Adding those env variables is not enough. You also need to configure the inference backend to choose where to route the AI calls.
See the [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md#inference-backends) documentation.

For example, if you want to use a gemini model via GOOGLE, enable the google backend in `.pipelex/inference/backends.toml` and set the API key in your env.
---

## Your first LLM call with Pipelex

Let's start by running your very first LLM call using Pipelex.
For illustration purposes, let's build **a character generator**. Each example relies on asynchronous execution and typed models for reliable prompts.

### Write your first pipeline

First, create a `.plx` library file in the `pipelex_libraries/pipelines` directory to store your pipe definition.
Run `pipelex init libraries` to create this directory if it doesn't exist. For now, keep all your pipeline definitions inside that folder only.

`character.plx`
```plx
domain = "characters"

[pipe]
[pipe.create_character]
type = "PipeLLM"
definition = "Creates a character."
output = "Text"
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
```

### Run your first Pipelex script

Now, create a `.py` python file to run your script. You can save it anywhere in your repository.

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

### Get your first Pipelex result

```bash
python character.py
```

![Example of a generated character sheet](character_sheet.png)

## How to use a specific LLM or LLM provider

### Indicate your LLM selection explicitly using the `llm` attribute

```plx
[pipe.create_character]
type = "PipeLLM"
definition = "Create a character."
output = "Text"
llm = { llm_handle = "gpt-4o-mini", temperature = 0.9, max_tokens = "auto" }
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
```

### Or use an LLM preset from the LLM deck

```plx
[pipe.create_character]
type = "PipeLLM"
definition = "Create a character."
output = "Text"
llm = "llm_for_creative_writing"
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""

# The llm deck above is defined in `.pipelex/inference/deck/base_deck.toml` as:
# llm_for_creative_writing = { llm_handle = "best-claude", temperature = 0.9 }
# it's a base preset that we provide. you can add your own presets, too.
```

💡 We have a lot of [LLM presets available by default](https://github.com/Pipelex/pipelex/tree/main/.pipelex/inference/deck/base_deck.toml).
Make sure you have credentials for the underlying LLM provider (and added your API key to the `.env`) and select the one you want!

Learn more about LLM presets, LLM handles and LLM deck in our [LLM Configuration Guide](../build-reliable-ai-workflows-with-pipelex/configure-ai-llm-to-optimize-workflows.md)

### Generate a structured output

Let's say that we no longer want plain text as output but a rigorously structured Character object.

### Define the model

Using the [Pydantic BaseModel](https://docs.pydantic.dev/latest/) syntax, define your object structure as a Python class, in the `pipelex_libraries/pipelines` directory:

`pipelex_libraries/pipelines/characters.py`
```python
from pipelex.core.stuffs.stuff_content import StructuredContent

# Define the structure of your output here
# This class must inherit from StructuredContent
class Character(StructuredContent):
    name: str
    age: int
    gender: str
    description: str
```

### Improve the pipeline

It's time to specify that your output be a `Character` instance. Use the `output` field for that purpose.

💡 Here, the concept name matches the class name (ie. `Character`), the `Character` class will automatically be considered as the structure to output.

`pipelex_libraries/pipelines/characters.plx`
```plx
domain = "characters"

[concept]
Character = "A character is a fiction story" # <- Define here your output concept so that it is linked to the class name

[pipe]
[pipe.create_character]
type = "PipeLLM"
definition = "Create a character. Get a structured result."
output = "Character"    # <- This is the output concept for your pipe
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
```

💡 Defining the `Character` concept as "A character is a fiction story" might seem obvious but… think of it: "character" can also mean a letter or symbol in a text. Defining concepts is the best way to avoid any ambiguity and make sure the LLMs understand what you mean.

### Run your pipeline

As you can see, the output is a `Character` instance.

![Example of a generated character sheet with structure in JSON](structured_character_sheet_json.png)


## Generate using information in a prompt template

What if you want to pass some data into a prompt?
You can do that using a prompt template.

In this example, we no longer want to generate characters. We want to process existing ones, especially their description attributes.

We want to extract structured information from the description field. Thus we have a `Character` input and a `CharacterMetadata` output.

### Define the output structure

```python
# pipelex_libraries/pipelines/character_model.py
from pipelex.core.stuffs.stuff_content import StructuredContent

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

### **Let's use a template to fill prompts with data**

💡 Our template syntax is based on [Jinja2 syntax](https://jinja.palletsprojects.com/en/stable/). You can include a variable using the **classic** `{{ double.curly.braces }}`, and to make it simpler, we've added the possibility to just prefix your variable with the `@` symbol (recommended). Pipes declare their required inputs explicitly with the `inputs` table:

```plx
[concept]
Character = "A character from a book"
CharacterMetadata = "Metadata regarding a character."

[pipe]
[pipe.extract_character_1]
type = "PipeLLM"
definition = "Get character information from a description."
inputs = { character = "Character" }  # <- These are the inputs of your pipe, usable in the prompt_template
output = "CharacterMetadata"
prompt_template = """
You are given a text description of a character.
Your task is to extract specific data from the following description.

@character.description
"""
```

💡 `@character.description` is substituted by grabbing the stuff named `character`in the working memory and using its `description`attribute

Learn more about how we use Jinja in the [PipeLLM documentation](../build-reliable-ai-workflows-with-pipelex/pipe-operators/PipeLLM.md).

### **This is how you do it from the code side**

```python
import asyncio

from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

from pipelex.libraries.pipelines.screenplay import Character, CharacterMetadata


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

    # Get the result as a porperly typed instance
    extracted_metadata = pipe_output.main_stuff_as(content_type=CharacterMetadata) # <- This is the output of your pipe, properly typed

    print(extracted_metadata)


Pipelex.make()
asyncio.run(process_existing_character())
```

### **Get result**

![Example of extracted character metadata](extracted_character_metadata.png)
