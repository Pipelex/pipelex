# Judgment

Closed questions about the evidence a prompt presents, answered with a verdict and how sure the model is.

## Overview

Many steps of a method come down to a closed question: is this message urgent, which team owns this ticket, how severe is this report. PipeJudge renders the evidence in its prompt, as a PipeLLM renders its prompt, and asks such a question about it of a judgment model, a model built to answer with a verdict and the probabilities it measured rather than with free text. The verdict is a typed `YesNo`, `Choice` or `Rating`, so the steps after it read it like any other concept.

## Key Capabilities

- **Three kinds of question** — A yes/no question with criteria for both answers, a choice among declared options, or a rating on a scale of declared levels, each with a label, a description or both, the kind read from the fields the pipe declares
- **Measured probabilities** — Each verdict carries the probabilities the model measured, so a method can act on how sure it is as well as on what it decided
- **Thresholds** — A yes/no question can declare the probability at or above which its verdict is yes
- **Several questions in one request** — A step can ask several questions about the same evidence, each of its own kind, and fill a structure with one verdict per question, each in the field of its question's name
- **The evidence is a prompt** — The model judges what the step's prompt renders and nothing else, so the author decides what it sees, down to one field of a larger value; the images and documents the prompt reads are sent as files to a model that reads them
- **Labels on a rating** — When the scale's levels carry labels, the verdict carries the label of the level chosen, copied from the declaration
- **No verdict from a refusal** — A model that declines to answer fails the step with an error naming the pipe and the model, rather than a verdict read off its silence; a step asking several questions leaves the declined question's field holding nothing instead when that field is optional with no default, and fails when it is required or carries a `default_value`
- **Checked when the method loads** — A step with no model, an input neither its prompt nor its questions read, an output that disagrees with its kind of question or a structure whose fields are not exactly its questions, or a file its prompt reads that its model does not is refused before any run spends anything

## Usage in Pipelines

Put a PipeJudge where a method needs a decision, then route on the verdict: a `PipeCondition` whose expression is `routing.choice` sends each item to the branch its judgment chose, and one comparing `approved.probability` with a bound gates a step on the model's certainty. To judge every item of a list, map the PipeJudge over it with a `PipeBatch`.

No judgment model is served out of the box: a judgment names its model, such as the deck's `@default-judgment` alias for TypeSafe's model, which needs a `TYPESAFE_API_KEY`.

## Related Documentation

- [PipeJudge](../building-methods/pipes/pipe-operators/PipeJudge.md) - Operator reference and authoring guidance
- [Native concepts](../building-methods/concepts/native-concepts.md) - The `YesNo`, `Choice` and `Rating` verdicts
- [Pipeline Orchestration](./pipeline-orchestration.md) - Route and gate steps on a verdict
