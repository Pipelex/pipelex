# Concepts

A concept **defines** **what is processed** through pipes: they represent the **knowledge** that is processed as input and generated as output in Pipelex pipelines.

**Rigorous concept definitions are the key to ensure controlled, reliable outputs in pipelines.**

Concepts are defined both with **natural language** (so non-developers and LLMs can understand and write them) and optionally also **with code** (to ensure deterministic validation with software).

Based on concepts, pipes embed **validation** on their inputs and outputs, so **we make sure of the knowledge we process and produce**.

## Concept definition

Concepts are defined using a **`toml` syntax** and (optional) **Python code ([BaseModel](https://docs.pydantic.dev/latest/concepts/models/)).**

- The `toml` part is meant to be **written in a library `toml` file.**

  - 💡*In the quick-start example (character generator) this is the role of `character.toml`[.](https://www.notion.so/Pipelex-Documentation-1b34fbe82c898062af44d70f6aa0f461?pvs=21)*

- The python code related to the Concept definition **must be saved in a `pipelex_libraries` folder at the root of your project.**

As seen in the quick-start, we use Python to instantiate concepts into Stuff objects.

![*Concepts can be defined both with toml and code. Stuffs are instantiated from Concepts with Python code.*](concept_and_stuff.png)

_Concepts can be defined both with toml and code. Stuff are instantiated from Concepts with Python code._

## Concept with text

In the 1st quick-start example, `character.toml` includes a text-based definition of a Concept (Character).

It is a good example of how to define a Concept. Just describe what the stuff is.

```toml
# Library header
domain = "character"
definition = "Tools for creating characters"

[concept]
Character = "A detailed description of a character"
```

## Structured concepts with text and code

Once you are familiar with defining Concepts with text, you may be interested in using a BaseModel to improve LLM reliability by structuring the knowledge you manipulate.

**_This is mandatory if you want your outputs to have a controlled structure and benefit from Pipe validation_**

For that purpose, you will need both `toml` and Python.

In this example, we define a `Summary` structured concept. It consists of a text and a creation date.

```toml
# summarize.toml

domain = "summarize"
definition = "Summarize text using LLMs."

[concept]
Summary = "A concise and organized rewriting of a large and dense text."
```

```python
# summarize_models.py

from datetime import datetime
from pydantic import Field
from pipelex.core.stuff_content import StructuredContent

# Class definition, inherits from StructuredContent
class Summary(StructuredContent):
    text: str
    created_at: datetime = Field(default_factory=datetime.now)
```

:bulb: We take benefit of the `Field` pydantic class to automatically set the `created_at` attribute to the current date and time.

**Super important: How do you bind Models and Concepts?**

:right_arrow: They have the same name! `Summary` and `Summary`

💡 When you define a BaseModel for one of your concepts, **make sure it inherits from a StructuredContent class.**

## Fields description

Defining a list of concepts is done in the `toml` file. Just define a list of concepts with their definition.

```toml
[concept]                                               # Required
Concept1 = "Concept1 definition with Natural Language"  # Required, str
Concept2 = "Concept2 definition with Natural Language"  # Required, str
...
ConceptN = "ConceptN definition with Natural Language"  # Required, str
```

- `Concept` _(required, str)_: The Concept definition.

## Usage in code

A concept instance is called a `Stuff`. Once instantiated **it can be loaded into the working memory and processed by Pipes.**

### Stuff overview

**A stuff object** has:

- **metadata** (code, domain, concept_code, …)
- **a content object** (that stores the data)

For your information, this is what the Stuff and StuffContent classes look like:

- **Stuff class (optional attributes removed)**

```python
class Stuff(BaseModel):
    concept_code: str       # To indicate what concept to instantiate: <domain>.<concept_name>
    stuff_name: str         # To identify the stuff
    content: StuffContent   # To store the data
```

- **StuffContent classes:**

Stuff content objects are instances of a subclass of the StuffContent class. They are very useful when you want to manipulate specific objects and render them.

```python
# Base Classes
class StuffContent(ABC, BaseModel):
    """Base class for all content types. Provides methods to render content in different formats
    (plain text, HTML, Markdown, JSON, spreadsheet)."""
```

### Make stuffs for text-only Concepts

In this example we load a contract content and make a stuff from it. We assume that a legal.Contract concept already exists.

```python
from pipelex.core.stuff_factory import StuffFactory

with open("contract.txt", "r") as file:
    contract_content = file.read()

question_stuff = StuffFactory.make_from_str(
    concept_code="legal.Contract",   # <domain>.<concept_name>
    str_value=contract_content,      # The str content to add to the stuff
    stuff_name="contract",           # The name of the stuff
)
```

### Make stuffs for structured Concepts

Make stuff easily using the StuffFactory class.

```python
from pipelex.core.stuff_factory import StuffFactory
from pipelex_libraries.character_model import Character


character = Character(
    name="Elias",
    age=38,
    gender="man",
    occupation="unemployed",
    description="""Elias Varrin is a 38-year-old man, standing at approximately 1.85 meters tall, with a lean,
weathered frame shaped by decades of travel through remote and often unforgiving landscapes.
His name, though not widely known, carries weight among historians, explorers, and those who trade in whispered legends.
Elias has piercing storm-gray eyes that scan every environment with sharp precision, and his ash-blond hair—flecked with
early streaks of grey—is usually tucked beneath a wide-brimmed, timeworn hat.His hands are etched with fine scars and stained
with ink, each mark a silent record of years spent charting unrecorded lands and handling fragile relics of lost civilizations.
He moves with quiet purpose and speaks with a calm, thoughtful cadence that suggests he’s always listening for more than just what’s said.""",
)
character_stuff = StuffFactory.make_stuff(
    concept_code="character.Character",
    stuff_name="character",
    content=character,
)
```

:arrow_left: [**Back to Libraries**](../Libraries/libraries.md)

:arrow_right: [**Next section: Pipes**](../Pipes/Pipes.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
