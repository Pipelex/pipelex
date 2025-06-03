# Quick-start

In this section, we introduce the basics of Pipelex for the simplest use-cases: LLM calling and structured outputs.

You can **run the following examples** directly from the [Getting-started repository](https://github.com/Pipelex/ev-getting-started).
No need to create files in the getting-started repo, they are already there.

## Your first LLM call with Pipelex

Let's start by running your very first LLM call using the Pipelex framework.
For illustration purposes, let's build **a character generator.**

### **🖊️ Write your first Pipelex script:**

You have to create a `TOML` library file that will store your Pipelex script.
If you are using Pipelex elsewhere than in the Getting Started repository, make sure you add this file to the `pipelex_libraries` folder.

```toml
# character.toml

# Library definition
domain = "characters"
definition = "Tools for creating characters"

# Pipe definition
[pipe]
[pipe.create_character]
PipeLLM = "Creates a character."
output = "Text"
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
```

### **🏃 Run your first Pipelex script:**

You have to create a `python` file to run your script. You can save it anywhere in your repository.

```python
# character.py

import asyncio
from pipelex.pipelex import Pipelex
from pipelex.run import execute_pipe

async def create_character() -> str:
    # Run the script with execute_pipe
    pipe_output = await execute_pipe(
        pipe_code="create_character",
    )
    # Print the output
    print(pipe_output.main_stuff_as_text)

# Setup required to initialize the Pipelex framework and load the pipeline libraries
Pipelex.make()

# Run using asyncio because our APIs are all async 
asyncio.run(create_character())
```

### **🎉 Get your first Pipelex result!**

```bash
python character.py
```

![Example of a generated character sheet](character_sheet.png)

## How to use a specific LLM

### **🖊️ Indicate your LLM selection explicitly using the `llm` attribute:**

```toml
[pipe.create_character]
PipeLLM = "Create a character."
output = "Text"
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
llm = { llm_handle = "gpt-4o-mini", temperature = 0.9, max_tokens = "auto" }
```

### **🖊️ Or use an LLM preset:**

```toml
[pipe.create_character]
PipeLLM = "Create a character."
output = "Text"
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
llm = "llm_for_creative_writing"

# The llm preset above is defined in `pipelex_libraries/llm_deck/base_llm_deck.toml` as:
# llm_for_creative_writing = { llm_handle = "best-claude", temperature = 0.9 }
# it's a base preset but you can add your own
```

💡We have a lot of [LLM presets available](https://github.com/Pipelex/pipelex/tree/main/pipelex/libraries/llm_deck/base_llm_deck.toml).
Make sure you have credentials for the underlying LLM provider (and added your API key to the `.env`) and select the one you want!

### **Generate a structured output**

Let's say that we no longer want plain text as output but a rigorous, structured Character object.

### **🖊️ Define the model**

Using the [Pydantic Basemodel](https://docs.pydantic.dev/latest/) syntax, define your object structure as a Python class.

```python
# pipelex_libraries/pipelines/characters.py

from pipelex.core.stuff_content import StructuredContent

# Define the structure of your output here
# This class must inherit from StructuredContent
class Character(StructuredContent):
    name: str
    age: int
    gender: str
    description: str
```

### **🖊️ Write the script**

It's time to specify that your output should be a `Character` instance. Use the `output` field for that purpose.

💡 Here, the concept name matches the class name (ie. `Character`), the `Character` class will automatically be considered as the structure to output.

```toml
domain = "characters"
definition = "Tools for creating characters"

[concept]
[concept.Character]
Concept = "A character is a fiction story"
# Concept matches class name. Structure is automatically used for structuring the output

[pipe]
[pipe.create_character]
PipeLLM = "Create a character. Get a structured result."
output = "Character"
prompt_template = """You are a book writer. Your task is to create a character.
Think of it and then output the character description."""
```

💡 Defining the `Character` concept as "A character is a fiction story" might seem obvious but… think of it: "character" can also mean a letter or symbol in a text. Defining concepts is the best way to avoid any ambiguity and make sure the LLMs understand what you mean.

### **🏃 Run**

![Example of a generated character sheet with structure](structured_character_sheet.png)

As you can see, the output is a `Character` instance.

![Example of a generated character sheet with structure in JSON](structured_character_sheet_json.png)


## Generate using information in a prompt template

What if you want to integrate some data into prompts?
You can do that using a prompt template.

In this example, we no longer want to generate characters. We want to process existing ones, especially their description attributes.

We want to extract structured information from the description field. Thus we have a `Character` input and a `CharacterMetadata` output.

### **Define the output structure**

```python
# pipelex_libraries/character_model.py
from pipelex.core.stuff_content import StructuredContent

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

### **Let's use a template to fill prompts with data:**

💡Our template syntax is based on [Jinja2 syntax](https://jinja.palletsprojects.com/en/stable/) so you can include a variable using the classic {{ double.curly.braces }} and to make it simpler, we've added the possibility to just prefix your variable with the "@" symbol: 

```toml
[concept]
Character = "A character from a book"
CharacterMetadata = "Metadata regarding a character."

[pipe]
[pipe.extract_character_1]
PipeLLM = "Get character information from a description."
input = "Character"
output = "CharacterMetadata"
prompt_template = """
You are given a text description of a character.
Your task is to extract specific data from the following description.

@character.description
"""
```

### **This is how you do it from the code side**

```python
from pipelex.core.stuff_factory import StuffFactory
from pipelex.client.client import PipelexClient
from pipelex_libraries.pipeline.characters import Character, CharacterMetadata

async def process_existing_character():
    # Your existing data
    character = Character(
        name="Elias",
        age=38,
        gender="man",
        description = """Elias Varrin is a 38-year-old man, standing at approximately 1.85 meters tall, with a lean,
        weathered frame shaped by decades of travel through remote and often unforgiving landscapes.
        His name, though not widely known, carries weight among historians, explorers, and those who trade in whispered legends.
        Elias has piercing storm-gray eyes that scan every environment with sharp precision, and his ash-blond hair—flecked with
        early streaks of grey—is usually tucked beneath a wide-brimmed, timeworn hat.His hands are etched with fine scars and stained
        with ink, each mark a silent record of years spent charting unrecorded lands and handling fragile relics of lost civilizations.
        He moves with quiet purpose and speaks with a calm, thoughtful cadence that suggests he's always listening for more than just what's said."""
    )
    # Wrap it into a stuff object
    character_stuff = StuffFactory.make_stuff(
        concept_code="character.Character",
        name="character",
        content=character,
    )
    # Add it to the working memory
    working_memory = WorkingMemoryFactory.make_from_single_stuff(
        stuff=character_stuff,
    )
    # Run the pipe identified by its pipe_code (it's the name of the pipe)
    pipelex_client = PipelexClient()
    pipe_output = await pipelex_client.execute_pipeline(
        pipe_code="extract_character_1",
        working_memory=working_memory,
    )

    # Get the result as a porperly typed instance
    extracted_metadata = pipe_output.main_stuff_as(content_type=CharacterMetadata)
    
    print(CharacterMetadata)

Pipelex.make()
asyncio.run(create_character())
```

### **Get result**

![Example of extracted character metadata](extracted_character_metadata)

:arrow_left: [**Back to Installation**](../Installation/Installation.md)

:arrow_right: [**Next section: Pipelex paradigm**](../Pipelex%20paradigm/Pipelex%20paradigm.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
