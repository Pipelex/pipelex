# Libraries

Pipelex proposes a Python framework along with a syntax for defining and running knowledge processing workflows.

## Scripts

What we call _scripts_ are the `TOML` files containing the concept and pipe definitions written using the Pipelex syntax.

## `pipelex_libraries` folder

Concepts, Pipelines and code are meant to be stored in a `pipelex_libraries` folder at the root of your project.

## Pipelex Libraries

Within a consistent **domain** (domain is the Pipelex name for topic), scripts constitute a library.

A library is a set of scripts along with their corresponding Python code (used for structuring LLM outputs through structured Concepts).

## Library structure

A library is defined by a `toml` file in a `pipelex_libraries` folder.

The `toml` file contains the concepts and pipes definitions.

It looks like this:

![Schema showing Pipelex library structure](library_structure.png)

## Fields

### Domain definition

As a library `toml` file header, you need to define the domain of the library.

```toml
domain = "domain_name"
definition = "Definition of the domain"
```

:bulb: Optional global settings (such as `system_prompt`) can be defined at the library level, in the header.

### Concepts

See [Concepts](../Concepts/Concepts.md)

### Pipes

See [Pipes](../Pipes/Pipes.md)

:arrow_left: [**Back to Quick-start**](../Quick-start/Quick-start.md)

:arrow_right: [**Next section: Concepts**](../Concepts/Concepts.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
