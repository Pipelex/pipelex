---
title: "Judgment"
description: "Closed questions answered by a judgment model inside Pipelex methods. PipeJudge returns a yes/no, a choice or a rating with the probabilities the model measured, ready to route or gate the steps after it."
---

# Judgment

Closed questions about your data, answered with a verdict and how sure the model is.

## Overview

Many steps of a method come down to a closed question: is this message urgent, which team owns this ticket, how severe is this report. PipeJudge asks such a question of a judgment model, a model built to answer it with a verdict and the probabilities it measured rather than with free text. The verdict is a typed `YesNo`, `Choice` or `Rating`, so the steps after it read it like any other concept.

## Key Capabilities

- **Three kinds of question** — A yes/no question, a choice among declared options, or a rating on a scale of declared levels, the kind read from the fields the pipe declares
- **Measured probabilities** — Each verdict carries the probabilities the model measured, so a method can act on how sure it is as well as on what it decided
- **Thresholds** — A yes/no question can declare the probability at or above which its verdict is yes
- **Material, not prompts** — Every input of the step is sent to the model as material to judge, images and documents as files for a model that reads them
- **Checked when the method loads** — A step with no model, an output that disagrees with its kind of question, or a file input its model does not read is refused before any run spends anything

## Usage in Pipelines

Put a PipeJudge where a method needs a decision, then route on the verdict: a `PipeCondition` whose expression is `routing.choice` sends each item to the branch its judgment chose, and one comparing `approved.probability` with a bound gates a step on the model's certainty. To judge every item of a list, map the PipeJudge over it with a `PipeBatch`.

No judgment model is served out of the box: a judgment names its model, such as the deck's `@default-judgment` alias for TypeSafe's model, which needs a `TYPESAFE_API_KEY`.

## Related Documentation

- [PipeJudge](../building-methods/pipes/pipe-operators/PipeJudge.md) - Operator reference and authoring guidance
- [Native concepts](../building-methods/concepts/native-concepts.md) - The `YesNo`, `Choice` and `Rating` verdicts
- [Pipeline Orchestration](./pipeline-orchestration.md) - Route and gate steps on a verdict
