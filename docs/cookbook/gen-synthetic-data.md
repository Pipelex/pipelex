---
title: "Synthetic Data Generation Example"
description: "Generate diverse synthetic data samples from a description using a two-step pipeline that identifies cases then creates profiles for each."
---

# Example: Synthetic Data Generation

This example generates diverse synthetic data samples from a text description. It first identifies a comprehensive set of sample cases, then creates detailed profiles for each one.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/c_advanced/gen_synthetic_data/bundle.mthds)

## What it demonstrates

- Concept refinement (`DataDescription` refines `Text`, `NbOfSamples` refines `Number`)
- Rich structured concept with constrained choices (`Sample` with `current_performance`, `learns_best_with`, etc.)
- Two-step generation: identify diverse cases, then create a profile for each
- Batching over identified cases to generate samples in parallel

## The Method: `bundle.mthds`

### Sample concept

The `Sample` concept represents a student profile with constrained fields:

```toml
[concept.Sample]
description = "A complete synthetic data record representing a student profile."

[concept.Sample.structure]
student_name = { type = "text", description = "The name of the student", required = true }
current_performance = { type = "text", description = "The student's current performance level", choices = [
  "Struggling", "Average", "Advanced",
], required = true }
learns_best_with = { type = "text", description = "The learning modality that works best", choices = [
  "Visual examples", "Step-by-step text", "Hands-on practice", "Videos",
], required = true }
# ... pace, complexity, strengths, needs_help_with, etc.
```

### Pipeline

```toml
[pipe.generate_synthetic_data_samples]
type = "PipeSequence"
inputs = { data_description = "DataDescription", nb_samples = "NbOfSamples" }
output = "Sample[]"
steps = [
  { pipe = "identify_sample_cases", result = "cases" },
  { pipe = "create_profile_for_case", result = "samples",
    batch_over = "cases", batch_as = "case_characterization" },
]
```

The first step identifies diverse real-world scenarios to ensure comprehensive coverage (edge cases, common scenarios, important variations). The second step creates a full profile for each case.

## How to run

```bash
pipelex run bundle examples/c_advanced/gen_synthetic_data/bundle.mthds \
  -i examples/c_advanced/gen_synthetic_data/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
- [Understanding Multiplicity](../building-methods/pipes/understanding-multiplicity.md) - How batching works
- [Refining Concepts](../building-methods/concepts/refining-concepts.md) - How concept refinement works
