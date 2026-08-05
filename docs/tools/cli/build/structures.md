---
description: "Generate Pydantic models from concept definitions in your .mthds files — turn declarative types into Python code automatically."
---

# Build Structures

Generate Pydantic models from your concept definitions.

!!! note "Alias of `codegen types`"
    `pipelex build structures` is an alias of [`pipelex codegen types --target python-structures`](../../../under-the-hood/codegen-projections.md): it resolves your bundles into a normalized library crate and emits a single stamped `structures.py` module plus a `codegen.lock`. Use `pipelex codegen check` to verify the generated files are current without regenerating.

## Usage

```bash
pipelex build structures <TARGET> [OPTIONS]
```

**Arguments:**

- `TARGET` - Either a library directory containing `.mthds` files, or a specific `.mthds` file (its directory is used as the closure)

**Options:**

- `-o`, `--output-dir` - Output directory for the generated module (defaults to `structures/` in target's directory)
- `-L`, `--library-dir` - Additional directory of `.mthds` bundles to load (repeatable)

## Examples

**Generate structures from a library directory:**

```bash
pipelex build structures ./my_pipelines/
```

**Generate structures from a specific bundle file:**

```bash
pipelex build structures ./my_pipeline/bundle.mthds
```

**Generate structures to a specific output directory:**

```bash
pipelex build structures ./my_pipelines/ -o ./generated/
```

## What Gets Generated

One `structures.py` module for the whole closure, plus a `codegen.lock`:

- **Pydantic model classes** - One `StructuredContent` subclass per concept, with types, constraints, and descriptions
- **Bare-when-unique names** - A concept `demo.Report` becomes `class Report`; only a code that collides across domains gets the domain-qualified spelling
- **Stamp + lock** - Each file carries a self-describing codegen stamp (crate fingerprint, engine version, content hash) and is tracked in `codegen.lock`, so `pipelex codegen check` can detect drift offline
- **Declared imprecision** - A concept whose shape cannot be fully derived is surfaced with an explicit caveat, never a silent guess

Generated files are never meant to be edited: to customize a type, subclass it in a sibling module (the generated header shows how) — subclasses survive regeneration.

## Bootstrapping a Method That Uses `PipeFunc`

This command projects your **concepts**, so it never loads or runs your pipes — and never imports your `@pipe_func` Python. That is what lets you start a `PipeFunc` method from nothing:

1. Write your `.mthds` bundle, declaring the concepts and the `PipeFunc` that outputs one of them.
2. Run `pipelex build structures . -o .` — it succeeds even though your implementation file does not exist yet.
3. Write your `@pipe_func`, importing the class you just generated and annotating it as the return type.

Without this, step 2 would demand the function from step 3, and step 3 would demand the output of step 2. At step 2 your implementation may be missing, half-written, or fail to import — structure generation is unaffected. The command needs no model deck either, so it works offline.

Everything else stays strict: `pipelex validate`, `pipelex resolve`, `pipelex build inputs` and `pipelex run` all still reject a method whose `PipeFunc` implementation is missing or broken. Generating structures is not a claim that your method is runnable — validate it once the function is written.

## Why Use Generated Structures?

- **Use as type hints** - Get IDE autocompletion and type checking in your code
- **Add custom logic** - Subclass the generated classes in your own module
- **Integrate in your app** - Use the models directly in your application
- **Trust the drift check** - `pipelex codegen check` tells you when the models no longer match the method

## Example Output

For a concept defined in a `.mthds` file like:

```toml
[concept.CandidateProfile]
description = "A structured representation of a candidate's professional background."

[concept.CandidateProfile.structure]
skills = { type = "text", description = "Technical and soft skills", required = true }
years_of_experience = { type = "number", description = "Total years of experience" }
education = { type = "text", description = "Educational background", required = true }
work_history = { type = "text", description = "Summary of previous roles", required = true }
```

You get (inside the stamped `structures.py`):

```python
class CandidateProfile(StructuredContent):
    """A structured representation of a candidate's professional background."""

    skills: str = Field(..., description="Technical and soft skills")
    years_of_experience: Optional[float] = Field(default=None, description="Total years of experience")
    education: str = Field(..., description="Educational background")
    work_history: str = Field(..., description="Summary of previous roles")
```

## Related Documentation

- [Codegen projections](../../../under-the-hood/codegen-projections.md) - The engine behind this command (`codegen types`, stamps, lock, offline check)
- [Build Runner](runner.md) - Generate Python runner scripts
- [Build Inputs](inputs.md) - Generate example input JSON for a pipe
- [Build Output](output.md) - Generate example output JSON for a pipe
- [Concepts](../../../building-methods/concepts/define_your_concepts.md) - Understanding concept definitions
