# Build Structures

Generate Pydantic models from your concept definitions.

## Usage

```bash
pipelex build structures <TARGET> [OPTIONS]
```

**Arguments:**

- `TARGET` - Either a library directory containing `.mthds` files, or a specific `.mthds` file

**Options:**

- `-o`, `--output-dir` - Output directory for generated Python files (defaults to `structures/` in target's directory)

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

For each concept in your library, the command generates:

- **Pydantic model classes** - Full type definitions for your concepts
- **Field definitions** - Proper types and constraints
- **Validation** - Based on concept constraints

## Why Use Generated Structures?

Now you have your structures as Python code:

- **Iterate on them** - Modify and extend the generated classes
- **Add custom validation** - Add Pydantic validators for business logic
- **Use as type hints** - Get IDE autocompletion and type checking in your code
- **Integrate in your app** - Use the models directly in your application

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

You get a Pydantic model:

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class CandidateProfile(StructuredContent):
    """Generated CandidateProfile class"""

    skills: str = Field(..., description="Technical and soft skills")
    years_of_experience: float = Field(..., description="Total years of experience")
    education: str = Field(..., description="Educational background")
    work_history: str = Field(..., description="Summary of previous roles")
```

## Related Documentation

- [Build Runner](runner.md) - Generate Python runner scripts
- [Build Inputs](inputs.md) - Generate example input JSON for a pipe
- [Build Output](output.md) - Generate example output JSON for a pipe
- [Concepts](../../../6-build-reliable-ai-workflows/concepts/define_your_concepts.md) - Understanding concept definitions

