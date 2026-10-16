---
description: "Run custom Python functions inside Pipelex pipelines with PipeFunc. Add exact computation, business rules, and data transformations to your methods."
---

# PipeFunc

The `PipeFunc` operator provides an essential escape hatch, allowing you to execute arbitrary Python code from within a pipeline. It is for the work a model should not do: exact arithmetic, deterministic business rules, and reshaping data, for example with pandas or openpyxl.

!!! note "Keep other services out of a PipeFunc"
    A method receives its data through its inputs and hands its results to whatever runs it. Reading from a mailbox, a drive or a CRM, and writing back to one, belongs to that caller: an application using the SDK, an automation platform such as n8n, or an agent with its own connectors. A PipeFunc that calls another service works on your machine but fails on a sandbox-hosted deployment, where PipeFunc code runs in an isolated sandbox with no network access, no credentials and a short time limit. To read a web page or search the web, use [PipeExtract](PipeExtract.md) or [PipeSearch](PipeSearch.md).

## How it works

A `PipeFunc` step names a Python function of its method by the function's **import path from the root of the method's tree**: `function_name = "funcs.totals.compute_totals"` names the function `compute_totals` of the file `funcs/totals.py` in the method's folder. The [method tree](../../method-trees.md) is the set of files the method is made of, so the function travels with the method wherever the method goes.

1. **Validation** locates the module in the tree and proves, from its source and without running any Python, that the function is a top-level `def` or `async def` of the module carrying the `@pipe_func()` marker. A function it cannot find or prove is a `pipe_func_function_refused` validation error on the step's `function_name`, saying what is missing.
2. **The step's first run** imports the module under its real name, with the tree's root first on Python's import path, so the module imports its siblings in the tree as it would anywhere else (`from funcs.rates import VAT_RATE`). The imported function is then checked against the calling convention and the step's output.
3. **Each run** calls the function with the current `working_memory`, and stores what it returns as the step's output.

Nothing is discovered or imported when Pipelex starts: a module's top-level code runs when a step that names one of its functions first runs.

## Writing a function

A function a `PipeFunc` step can call:

- **carries the `@pipe_func()` marker**, which takes no argument;
- **is a top-level function of its module**, a `def` or an `async def` the module defines itself: a function the module imports from elsewhere, or assigns to the name, is refused;
- **takes exactly one parameter**, named `working_memory` and typed `WorkingMemory`;
- **returns a `StuffContent` subclass**, such as `TextContent`, a `StructuredContent` model or `ListContent[SomeType]`, matching the step's `output`: a list type for an output such as `Text[]`, the concept's own structure class otherwise.

An `async def` function is awaited; a plain `def` function runs in a worker thread (via `asyncio.to_thread`), so it does not block the pipeline.

Here is a method holding its Python beside its bundle:

```text
invoicing/
├── METHODS.toml
├── invoicing.mthds
└── funcs/
    ├── rates.py
    └── totals.py
```

```python
# invoicing/funcs/totals.py

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

from funcs.rates import VAT_RATE


@pipe_func()
async def concatenate_texts(working_memory: WorkingMemory) -> TextContent:
    """Retrieve two texts, concatenate them, and return a new text."""
    text1 = working_memory.get_stuff_as_str("text_a")
    text2 = working_memory.get_stuff_as_str("text_b")
    return TextContent(text=f"{text1} -- {text2} (VAT {VAT_RATE})")
```

```toml
# invoicing/invoicing.mthds

[pipe.combine_them]
type          = "PipeFunc"
description   = "Combine two text inputs using a custom Python function"
inputs        = { text_a = "Text", text_b = "Text" }
output        = "Text"
function_name = "funcs.totals.concatenate_texts"
```

A folder of modules, such as `funcs/` here, is a package with or without an `__init__.py`.

## The function name

`function_name` is a dotted import path: the module's path from the tree's root, its folders and its file name without `.py` joined by dots, then the function's name. A `function_name` holding no dot names no module, and is refused as the bundle is read, the message naming the migration command below.

Where the path starts depends on how the bundle reaches Pipelex:

- **A bundle of a method tree**, a method folder, a `.mthds` file in it, a library directory or a dependency package, imports from the root of its tree: the folder holding the method's `METHODS.toml`, or the folder handed over when there is none (see [Where a tree is rooted](../../method-trees.md#where-a-tree-is-rooted)).
- **A bundle passed as content**, with no file of its own, imports locally from Python's own import path, such as a module of your project or an installed package. On a sandbox-hosted deployment, it imports from the root of the Python submitted with it, the files of the library directories loaded beside it.

## One method's Python in a process

A local run imports a method's modules under their real names, with the tree's root first on the import path, so Pipelex keeps the methods of one process from stepping on each other:

- **No shadowing.** A top-level module of the tree named like a standard-library module, such as `json.py`, or like a module importable outside the tree, such as an installed package, is refused as the method is validated, the message naming the module, the file and what it would shadow. The one exception is a `structures` module, which the runtime generates from a method's concepts (`pipelex build structures`), so the method's own copy of it is the intended one.
- **One tree's Python at a time.** A run holds the Python of the tree it imports from until its library is torn down, and every run of that same tree shares the hold. A step of another tree that would load its Python while it is held is refused, the message naming both trees: two trees could define modules of the same name, and one process has one module of each name. So a run whose own steps and a dependency package's steps both call Python is refused locally.
- **Eviction before the next tree.** Once no run holds a tree, the next tree to load its Python first removes every module imported from the earlier tree, so a process running several methods one after the other never runs one method's module for another's step.

## The local import guard

While a run holds a tree, Pipelex serves the imports of every module under the tree's root:

- **A file the tree keeps out cannot be imported**, such as a `.gitignore`d module or a module of a virtual environment inside the folder: the import is refused with the membership rule that excluded it. What runs locally is what a sandbox would receive.
- **No bytecode is written into the tree**: no `__pycache__` folder appears beside your modules, so a method's files, and its tree digest, stay as they were written.

The guard covers imports only. A file your function reads with `open()` is not checked locally: read the files your method ships by their path in the tree, and keep in mind that a sandbox receives only the tree's files.

## Sandbox-hosted execution

On a sandbox-hosted deployment, the runner never imports a method's Python. Validation proves each function's form from the method's files, and each call of a `PipeFunc` step runs in a sandbox that receives every file of the step's tree except its `.mthds` files, written at their paths in the tree, the tree's root first on the import path. The sandbox generates the `structures` module from the method's concepts, so a function can `from structures import <domain>__<Concept>` without the method shipping a copy.

## Migrating flat function names

A `PipeFunc` step used to name its function by a flat name, the key under which a process-wide function registry held every `@pipe_func` function of every scanned directory, and `@pipe_func(name="...")` gave a function another key. The registry is retired: a flat name is refused, and `@pipe_func()` takes no argument. One command rewrites a method:

```bash
pipelex fix function-names invoicing/
pipelex fix function-names invoicing/ --dry-run
```

For each `PipeFunc` step whose `function_name` holds no dot, it finds the marked function of the tree that the flat name registered and writes its import path, then drops the argument of every `@pipe_func(name=...)` marker. It imports nothing and keeps every comment and alignment of your files. A flat name that no module of the tree registers, or that two register, is left as it is and reported with the markers registering it, a marker whose name is not a string literal is reported too, and the command exits `1`. See [Fix Commands](../../../tools/cli/fix.md#fix-function-names).

## Declaring the packages your functions need

When your functions import a package beyond Pipelex and the standard library, such as pandas or openpyxl, declare it in a `requirements.txt` at the root of the method's folder, one PEP 508 requirement per line. Pipelex checks it when the method loads and refuses the method, naming each requirement that is not met, rather than letting the function fail at its first import. Locally the check reads the interpreter Pipelex runs in and the refusal gives the `uv pip install` command that fixes it; on a sandbox-hosted deployment it reads the packages the sandbox holds, which are all a PipeFunc gets there. Pipelex never installs anything. The rules of the file are in [Method Trees](../../method-trees.md#python-packages-requirementstxt).

## Configuration

### MTHDS Parameters

| Parameter       | Type   | Description                                                                                                      | Required |
| --------------- | ------ | ---------------------------------------------------------------------------------------------------------------- | -------- |
| `type`          | string | The type of the pipe: `PipeFunc`                                                                                 | Yes      |
| `description`   | string | A description of the function operation.                                                                         | Yes      |
| `function_name` | string | The function's import path from the root of the method tree, such as `"funcs.totals.compute_totals"`.          | Yes      |
| `output`        | string | The concept to associate with the function's return value.                                                       | Yes      |

## Related Documentation

- [Method Trees](../../method-trees.md) - The files a method is made of, and where its tree is rooted
- [Advanced Customizations](../../../advanced/index.md) - Extend Pipelex with custom logic
- [Working Memory](../working-memory.md) - How pipes access and share data
