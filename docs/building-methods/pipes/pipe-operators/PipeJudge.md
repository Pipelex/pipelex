---
description: "PipeJudge asks a judgment model closed questions about the evidence its prompt presents, and returns a verdict per question with a measure of how sure it is: yes or no, one option out of a set, or a level on a scale."
---

# PipeJudge

The `PipeJudge` operator asks a judgment model a closed question about the evidence its prompt presents, and stores the verdict it answers with: a `YesNo`, a `Choice` or a `Rating`, each carrying the probabilities the model measured. It may also ask several questions about the same evidence in one request, and fill a structure with one verdict per question (see [Several questions in one request](#several-questions-in-one-request)). A judgment model is built for this kind of question: it answers with a verdict and the probabilities it measured, where a language model asked the same question writes its answer out as text.

## How it works

A `PipeJudge` keeps what is judged apart from what is asked. Its `prompt` renders the evidence, the material the model judges, and its `question` asks about that evidence:

```toml
prompt   = """
A message from someone writing to the inbox:
@message
"""
question = "Does this message need an answer today?"
```

The fields a `PipeJudge` declares decide the kind of question it asks, and the kind decides its output:

| Declares | Asks | Output |
| -------- | ---- | ------ |
| neither `options` nor `levels` | a yes/no question, which may carry `criteria` and a `threshold` | `YesNo` |
| `options` | which option fits | `Choice` |
| `levels` | which level fits, the levels being ordered from lowest to highest | `Rating` |

The output must be that native or a concept refining it, and `Dynamic` is neither: a pipe declaring `options` whose output is `YesNo` is refused when the method loads, with a message naming both sides. A `PipeJudge` produces one verdict, so its output cannot be a list; to judge every item of a list, map the `PipeJudge` over it with a [`PipeBatch`](../pipe-controllers/PipeBatch.md).

**The evidence is the rendered prompt.** `prompt` is a template rendered exactly as a [`PipeLLM`](PipeLLM.md)'s prompt is, and the model sees the pipe's inputs only as the prompt and the question render them. `@message` sets the input out as a block tagged with its name, `$total_amount` writes a short value inline, and a dotted reference such as `$invoice.total` reads one field of a larger value, so the model sees that field and nothing else of the invoice. Every declared input must be read by the prompt or by the question, and an input neither of them reads is refused when the method loads, since it would never reach the model. Absence is the template's business too: an optional input is read through a guarded reference such as `@?note`, which renders nothing when the input is absent, and an optional image or document left out that way is not presented to the model at all (see [Understanding optionality](../understanding-optionality.md)).

**The question is plain text.** `question` is a template as well, with the same shorthand, but it presents no file: it suits the instruction itself and a short parameter such as `"Is the message about $topic?"`. The evidence belongs in the prompt, and a question that reads an `Image` or a `Document` is refused when the method loads, since only the prompt presents files.

**Images and documents are sent as files.** An `Image` or a `Document` the prompt reads, a single value or a list, reaches the model as a file rather than as text, and a numbered token such as `[Image 1]` marks the place in the rendered prompt where the prompt reads it. Whether a model reads files is stated in its model configuration, and a `PipeJudge` whose prompt reads an image or a document is refused when the method loads if its model does not read that kind of file, with a message naming the variable and what the model reads. An input declared `Dynamic` names no kind of value, so the prompt renders it as text, as a `PipeLLM`'s does, and an image it holds reaches the model as its address rather than as a file. A document given to the run in a format the model does not read is refused when the run starts, before any step spends anything. TypeSafe's model reads text only, so turn a document into text with a [`PipeExtract`](PipeExtract.md) step first.

**The verdict.** A yes/no question's verdict follows from its probability: yes when the probability of yes is at least the `threshold`, which defaults to `0.5`. A model that reports no probability gives its own verdict, and a declared threshold then cannot apply, which the run logs as a warning. A choice's verdict is the key of the option chosen, with the model's `confidence` and the `probabilities` of every option when it reports them. A rating's verdict is the index of the level chosen, `0` being the first level declared, with the model's `confidence`, the `probabilities` of every level keyed by its index written as text, and a continuous `position` on the scale, when it reports them. When the scale's levels carry labels, the verdict's `label` is the label of the level chosen, copied from the pipe's declaration.

**A refusal fails the step.** A judgment model may decline to answer a question, and a refusal carries no verdict: it is never read as a no, as the first option or as the lowest level. A pipe asking one question has nowhere to leave its verdict absent, so the step fails with a [`JudgmentRefusedError`](../../../errors/judgment-refused-error.md) naming the pipe and the model; reword the question so it can be answered from the evidence, or give the step different evidence. A pipe asking several questions may leave a verdict absent instead, as the next section explains.

The [native concepts page](../../concepts/native-concepts.md) describes the fields of the three verdicts. A downstream pipe reads them like any other fields, for example a [`PipeCondition`](../pipe-controllers/PipeCondition.md) routing on `routing.choice`, or one gating on `approved.probability`.

## Several questions in one request

A `PipeJudge` may ask several questions about the same evidence, written in `questions`, one table per question, each keyed by a name. The model answers every question in one request, each independently of the others, and the verdicts fill the output's structure, each in the field of its question's name:

```toml
[concept.MessageTriage]
description = "What a triage of an inbox message found"

[concept.MessageTriage.structure]
urgent   = { type = "concept", concept_ref = "YesNo", description = "Whether the message needs an answer today", required = true }
team     = { type = "concept", concept_ref = "Choice", description = "The team that should handle it", required = true }
severity = { type = "concept", concept_ref = "Rating", description = "How severe the reported problem is" }

[pipe.triage_message]
type        = "PipeJudge"
description = "Triages a message: its urgency, its team and its severity"
inputs      = { message = "Text" }
output      = "MessageTriage"
model       = "@default-judgment"
prompt      = """
A message from someone writing to the inbox:
@message
"""

[pipe.triage_message.questions.urgent]
question  = "Does this message need an answer today?"
criteria  = { yes = "Something is broken or blocked for the sender right now", no = "The sender can wait for a reply" }
threshold = 0.7

[pipe.triage_message.questions.team]
question = "Which team should handle this message?"
options  = { billing = "Charges, invoices, refunds and subscriptions", technical = "Errors, outages and features that do not work", other = "" }

[pipe.triage_message.questions.severity]
question = "How severe is the problem this message reports?"
levels   = [{ label = "Minor" }, { label = "Major" }, { label = "Blocking" }]
```

**Each question carries its own kind.** A question's table holds its `question` and the fields that decide its kind, `options`, `levels`, `criteria` and `threshold`, under the same rules as a pipe asking one question; no other field is allowed in it. The pipe sets exactly one of `question` and `questions`, and a pipe asking several sets none of the kind fields itself: they belong to the question they qualify. A question's name must be a valid field name: a Python identifier that is not a keyword, does not start with an underscore and is not a reserved name.

**The output is a structure holding one verdict per question.** The output must be a concept with a structure, or a concept refining one, whose fields are exactly the question names: a question with no field to hold its verdict is refused when the method loads, and so is a field no question answers, since nothing could ever fill it. Each field is a `concept` field holding its question's verdict native, `YesNo`, `Choice` or `Rating`, or a concept refining it, and holds one verdict: a list field, a plain value such as a `boolean` and a concept of another kind are refused, each with a message naming the field and the question. The output itself carries no multiplicity; to judge each item of a list, map the `PipeJudge` over it with a [`PipeBatch`](../pipe-controllers/PipeBatch.md).

**The questions share the evidence.** The prompt renders the evidence once, and every question is asked about it. A question may read a short parameter of its own, such as `$topic`, and every declared input must be read by the prompt or by at least one question.

**A refusal leaves an optional field absent.** When the model declines one question, the step leaves that question's field absent if the field is optional, logs a warning naming the question, and records the refusal in the step's execution data, beside every other question's raw answer. When the field is required, or carries a default, as a field of a structure written as a Python class may, the step fails with a [`JudgmentRefusedError`](../../../errors/judgment-refused-error.md) naming the question, since a default filled in for it would read as a verdict the model never gave: reword the question, give the step different evidence, or make the field optional with no default so that a refusal leaves it absent. Declaring a field optional is how a method says that a refusal on that question is acceptable.

**The execution data is kept per question.** A step asking one question records its rendered question, its kind, its threshold, whether the threshold decided the verdict and the model's raw answer at the top level of its execution data, beside the rendered prompt and the model. A step asking several records the rendered prompt and the model there too, and nests the rest under `questions`, keyed by each question's name, as `rendered_question`, `judgment_kind`, `threshold`, `threshold_applied` and `outcome`, the outcome being the raw answer or the refusal.

**A question depending on another's verdict is a later step.** The questions of one `PipeJudge` are answered independently over the same evidence, so none of them can read another's verdict. When one question only makes sense once another is answered, such as rating a problem's severity only when the message reports a problem at all, ask the second in a later `PipeJudge` of a [`PipeSequence`](../pipe-controllers/PipeSequence.md), behind a [`PipeCondition`](../pipe-controllers/PipeCondition.md) routing on the first verdict when the second should not always be asked.

## Configuration

### The judgment model

No judgment model is served out of the box: the model deck names no default for judgments, so a `PipeJudge` names its model in its `model` field, and a `PipeJudge` that names none is refused when the method loads. The deck's `@default-judgment` alias points at TypeSafe's model, which works once a `TYPESAFE_API_KEY` is set (see [the inference backend configuration](../../../configuration/config-technical/inference-backend-config.md)). To let your pipes leave `model` out, set a `choice_default` under `[judgment]` in your model deck.

### MTHDS Parameters

| Parameter     | Type       | Description | Required |
| ------------- | ---------- | ----------- | -------- |
| `type`        | string     | The type of the pipe: `PipeJudge`. | Yes |
| `description` | string     | A description of the judgment. | Yes |
| `inputs`      | dictionary | The inputs, as a dictionary mapping input names to concept codes. Every input must be read by `prompt` or by a question. | No |
| `output`      | string     | Asking one question: `YesNo`, `Choice` or `Rating`, according to the kind of question, or a concept refining it. Asking several: a concept with a structure whose fields are exactly the question names, each holding its question's verdict native or a concept refining it. | Yes |
| `model`       | string     | The judgment model, alias or preset, such as `"@default-judgment"`. Required unless your model deck names a default for judgments. | No |
| `prompt`      | string     | The evidence template: what the model judges. Rendered as a `PipeLLM` prompt, with the `@variable` and `$variable` shorthand and Jinja2, and presents the images and documents it reads as files. Must not be empty. | Yes |
| `question`    | string     | The one closed question to ask about the evidence. A plain text template, which may interpolate a short parameter with the `$` prefix and reads no image or document. Must not be empty. | One of `question` or `questions` |
| `questions`   | dictionary | Several closed questions to ask about the evidence in one request, each keyed by the name of the output field holding its verdict. Each is a table holding its `question` and, for its kind, `options`, `levels`, `criteria` and `threshold`, as described below for a pipe asking one question. At least one question. | One of `question` or `questions` |
| `options`     | dictionary | For a choice question: each key is an option, each value describes it. An empty string leaves an option undescribed. At least two options. | No |
| `levels`      | list       | For a rating question: the levels from lowest to highest, at least two. Each is a string describing the level, or a table carrying a `label`, a `description` or both. Either every level carries a label or none does, and labels are distinct. | No |
| `criteria`    | dictionary | For a yes/no question: what a `yes` and what a `no` mean, both required. | No |
| `threshold`   | number     | For a yes/no question: the probability of yes at or above which the verdict is yes, strictly between 0 and 1. Defaults to `0.5`. | No |

`options`, `levels`, `criteria` and `threshold` are set on the pipe when it asks one `question`, and in each question's table when it asks several `questions`, never on the pipe.

### Example: A yes/no question with a threshold

```toml
[pipe.judge_is_urgent]
type        = "PipeJudge"
description = "Judges whether a message needs an answer today"
inputs      = { message = "Text" }
output      = "YesNo"
model       = "@default-judgment"
prompt      = """
A message from someone writing to the inbox:
@message
"""
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
prompt      = """
A support ticket, as the customer wrote it:
@ticket
"""
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

### Example: A rating on a labelled scale

```toml
[pipe.rate_severity]
type        = "PipeJudge"
description = "Rates how severe a bug report is"
inputs      = { report = "Text" }
output      = "Rating"
model       = "@default-judgment"
prompt      = """
A bug report filed by a user:
@report
"""
question    = "How severe is the bug this report describes?"
levels      = [
  { label = "Cosmetic", description = "Nothing stops working" },
  { label = "Degraded", description = "A workaround exists" },
  { label = "Blocking", description = "Users cannot do their work at all" },
]
```

A verdict of the last level reads `level = 2` and `label = "Blocking"`. A level may also be written as a plain string, which is its description: `levels = ["Nothing stops working", "A workaround exists", "Users cannot do their work at all"]`.

### Example: One field of a larger value

```toml
[pipe.judge_needs_second_signature]
type        = "PipeJudge"
description = "Judges whether an invoice total needs a second signature"
inputs      = { invoice = "Invoice" }
output      = "YesNo"
model       = "@default-judgment"
prompt      = "The total of an invoice, in euros: $invoice.total"
question    = "Is this amount high enough to need a second signature?"
criteria    = { yes = "The amount is above five thousand euros", no = "The amount is five thousand euros or less" }
```

The model sees the rendered prompt, `The total of an invoice, in euros: 7420.0`, and nothing else of the invoice.

## Writing good judgments

- **Ask one narrow thing per question.** A question that bundles two judgments ("is it urgent and about billing?") gets one verdict for both. Split it into two questions of one `PipeJudge` when they share the evidence and neither depends on the other's verdict, and into two `PipeJudge` steps of a `PipeSequence` when one does.
- **Keep the evidence focused.** The judgment vendors advise that a large evidence the question does not need degrades the answers, so render in the prompt what the question is about and leave the rest out: a dotted reference such as `$invoice.total` reads one field, where `@invoice` sets out the whole value.
- **Write criteria for both answers.** `criteria` declares what a `yes` and what a `no` mean, and both are required, so a table with one side or none is refused: when one side is the plain opposite of the other, write it as its complement, "The amount is five thousand euros or less" beside "The amount is above five thousand euros", and leave `criteria` out when the question needs none.
- **Make levels describe situations, not degrees.** "Users cannot do their work at all" gives the model something to recognize, where "Very severe" only restates the scale; a label names the level in a few words, and the description says what it stands for. A long scale of thin levels buys resolution the model cannot supply, and a scale holds at most ten levels: TypeSafe's model refuses more, and a longer scale fails the step before the model is called.
- **Give a choice a catch-all option** when the evidence may fit none of the others, such as `other = ""`, so the model is not forced to pick a wrong one.
- **Leave counting, arithmetic and dates to code.** Whether an invoice is over a sum, or a date is past a deadline, is a comparison a [`PipeFunc`](PipeFunc.md) or a `PipeCondition` expression makes exactly.
- **State the condition directly** in the question rather than through an indirection, and keep what the question interpolates to short parameters: the evidence belongs in the prompt.

## Related Documentation

- [Judgment Feature](../../../features/judgment.md) - Overview of judgments in a method
- [Native concepts](../../concepts/native-concepts.md) - The `YesNo`, `Choice` and `Rating` verdicts
- [PipeLLM](PipeLLM.md) - The prompt templating the evidence shares
- [PipeCondition](../pipe-controllers/PipeCondition.md) - Route on a verdict
