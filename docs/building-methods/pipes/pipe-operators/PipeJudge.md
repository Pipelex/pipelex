---
description: "PipeJudge asks a judgment model one closed question about its inputs and returns a verdict with a measure of how sure it is: yes or no, one option out of a set, or a level on a scale."
---

# PipeJudge

The `PipeJudge` operator asks a judgment model one closed question about its inputs, and stores the verdict it answers with: a `YesNo`, a `Choice` or a `Rating`, each carrying the probabilities the model measured. A judgment model is built for this kind of question: it answers with a verdict and the probabilities it measured, where a language model asked the same question writes its answer out as text.

## How it works

The fields a `PipeJudge` declares decide the kind of question it asks, and the kind decides its output:

| Declares | Asks | Output |
| -------- | ---- | ------ |
| neither `options` nor `levels` | a yes/no question, which may carry `criteria` and a `threshold` | `YesNo` |
| `options` | which option fits | `Choice` |
| `levels` | which level fits, the levels being ordered from lowest to highest | `Rating` |

The output must be that native or a concept refining it, and `Dynamic` is neither: a pipe declaring `options` whose output is `YesNo` is refused when the method loads, with a message naming both sides. A `PipeJudge` produces one verdict, so its output cannot be a list; to judge every item of a list, map the `PipeJudge` over it with a [`PipeBatch`](../pipe-controllers/PipeBatch.md).

**Every input is material to judge.** The model receives each input the pipe declares, by name, whether or not the question mentions it: a `Text` as its text, a `Number` as its number, a `YesNo` as its boolean, a list as a list, and a structured concept as its fields. An optional input that is absent is left out. Each input is sent whole, so an input name cannot reach into a field with a dot, as `invoice.total` would: declare `invoice` instead. So, unlike the other operators, a `PipeJudge` does not have to read its inputs in its `question`; it may still interpolate one, which suits a short parameter such as `"Is the message about $topic?"`, and every variable the question reads must be a declared input.

**Images and documents are sent as files.** An `Image` or a `Document` input, or a list of either, reaches the model as a file rather than as text. Whether a model reads files is stated in its model configuration, and a `PipeJudge` with an image or a document input is refused when the method loads if its model does not read that kind of file, with a message naming the input and what the model reads. An input declared `Dynamic` names no kind of value, so a file it holds is checked when the step runs instead. A document given to the run in a format the model does not read is refused when the run starts, before any step spends anything. TypeSafe's model reads text only, so turn a document into text with a [`PipeExtract`](PipeExtract.md) step first.

**The verdict.** A yes/no question's verdict follows from its probability: yes when the probability of yes is at least the `threshold`, which defaults to `0.5`. A model that reports no probability gives its own verdict, and a declared threshold then cannot apply, which the run logs as a warning. A choice's verdict is the key of the option chosen, with the model's `confidence` and the `probabilities` of every option when it reports them. A rating's verdict is the index of the level chosen, `0` being the first level declared, with the model's `confidence`, the `probabilities` of every level keyed by its index written as text, and a continuous `position` on the scale, when it reports them.

The [native concepts page](../../concepts/native-concepts.md) describes the fields of the three verdicts. A downstream pipe reads them like any other fields, for example a [`PipeCondition`](../pipe-controllers/PipeCondition.md) routing on `routing.choice`, or one gating on `approved.probability`.

## Configuration

### The judgment model

No judgment model is served out of the box: the model deck names no default for judgments, so a `PipeJudge` names its model in its `model` field, and a `PipeJudge` that names none is refused when the method loads. The deck's `@default-judgment` alias points at TypeSafe's model, which works once a `TYPESAFE_API_KEY` is set (see [the inference backend configuration](../../../configuration/config-technical/inference-backend-config.md)). To let your pipes leave `model` out, set a `choice_default` under `[judgment]` in your model deck.

### MTHDS Parameters

| Parameter     | Type       | Description | Required |
| ------------- | ---------- | ----------- | -------- |
| `type`        | string     | The type of the pipe: `PipeJudge`. | Yes |
| `description` | string     | A description of the judgment. | Yes |
| `inputs`      | dictionary | The material to judge, as a dictionary mapping input names to concept codes. Every input is sent to the model. | No |
| `output`      | string     | `YesNo`, `Choice` or `Rating`, according to the kind of question, or a concept refining it. | Yes |
| `model`       | string     | The judgment model, alias or preset, such as `"@default-judgment"`. Required unless your model deck names a default for judgments. | No |
| `question`    | string     | The one closed question to ask. It may interpolate an input with the `$` prefix. `prompt` is read as a synonym, but a pipe may not set both. | Yes |
| `options`     | dictionary | For a choice question: each key is an option, each value describes it. An empty string leaves an option undescribed. At least two options. | No |
| `levels`      | list of strings | For a rating question: the levels from lowest to highest. At least two. | No |
| `criteria`    | dictionary | For a yes/no question: what a `yes` and what a `no` mean, either or both. | No |
| `threshold`   | number     | For a yes/no question: the probability of yes at or above which the verdict is yes, strictly between 0 and 1. Defaults to `0.5`. | No |

### Example: A yes/no question with a threshold

```toml
[pipe.judge_is_urgent]
type        = "PipeJudge"
description = "Judges whether a message needs an answer today"
inputs      = { message = "Text" }
output      = "YesNo"
model       = "@default-judgment"
question    = "Does this message need an answer today?"
criteria    = { yes = "Something is broken or blocked for the sender right now", no = "The sender can wait for a reply" }
threshold   = 0.7
```

### Example: A choice that routes a ticket

```toml
[pipe.judge_team]
type        = "PipeJudge"
description = "Judges which team should handle a support ticket"
inputs      = { ticket = "Text" }
output      = "Choice"
model       = "@default-judgment"
question    = "Which team should handle this support ticket?"
options     = { billing = "Charges, invoices, refunds and subscriptions", technical = "Errors, outages and features that do not work", other = "" }

[pipe.dispatch_ticket]
type            = "PipeCondition"
description     = "Sends the ticket to the team the judgment chose"
inputs          = { routing = "Choice", ticket = "Text" }
output          = "Text"
expression      = "routing.choice"
outcomes        = { billing = "acknowledge_billing", technical = "acknowledge_technical" }
default_outcome = "acknowledge_other"
```

### Example: A rating on a scale

```toml
[pipe.rate_severity]
type        = "PipeJudge"
description = "Rates how severe a bug report is"
inputs      = { report = "Text" }
output      = "Rating"
model       = "@default-judgment"
question    = "How severe is the bug this report describes?"
levels      = ["Cosmetic: nothing stops working", "Degraded: a workaround exists", "Blocking: users cannot do their work at all"]
```

## Writing good judgments

- **Ask one narrow question per pipe.** A question that bundles two judgments ("is it urgent and about billing?") gets one verdict for both. Split it into two `PipeJudge` steps, and combine their verdicts downstream.
- **Make levels describe situations, not degrees.** "Blocking: users cannot do their work at all" gives the model something to recognize, where "Very severe" only restates the scale. A long scale of thin levels buys resolution the model cannot supply, and TypeSafe's model reads at most ten levels.
- **Give a choice a catch-all option** when the material may fit none of the others, such as `other = ""`, so the model is not forced to pick a wrong one.
- **Leave counting, arithmetic and dates to code.** Whether an invoice is over a sum, or a date is past a deadline, is a comparison a [`PipeFunc`](PipeFunc.md) or a `PipeCondition` expression makes exactly.
- **State the condition directly** in the question rather than through an indirection, and keep interpolated inputs to short parameters: the material reaches the model anyway.

## Related Documentation

- [Judgment Feature](../../../features/judgment.md) - Overview of judgments in a method
- [Native concepts](../../concepts/native-concepts.md) - The `YesNo`, `Choice` and `Rating` verdicts
- [PipeCondition](../pipe-controllers/PipeCondition.md) - Route on a verdict
