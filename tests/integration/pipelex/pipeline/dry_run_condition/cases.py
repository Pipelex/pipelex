from typing import ClassVar


class DryRunConditionTestData:
    """Bundles whose dry runs run a condition's every outcome, one per shape an outcome can take."""

    REPORT_SHAPE_MTHDS: ClassVar[str] = """
domain = "dry_condition_report_shape"
description = "Judge a CV, route the follow-up, assemble both"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Text"
expression = "verdict"
outcomes = { fit = "write_questions", no_fit = "write_rejection" }
default_outcome = "write_rejection"

[pipe.write_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "Text"
prompt = "Questions for $cv"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Text"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Text" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

    # The condition writes `draft`, a slot that already holds `first_draft`'s value, and `b_polish`
    # reads that slot. Run last and unisolated, `b_polish` would read the draft `a_rewrite` just wrote.
    SLOT_CROSS_READ_MTHDS: ClassVar[str] = """
domain = "dry_condition_slot_cross_read"
description = "A condition whose outcome reads the slot the condition writes"
main_pipe = "flow"

[pipe.flow]
type = "PipeSequence"
description = "Draft, judge, then rewrite or polish the draft"
inputs = { text = "Text" }
output = "Text"
steps = [
  { pipe = "first_draft", result = "draft" },
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "draft" },
]

[pipe.first_draft]
type = "PipeLLM"
description = "Write a first draft"
inputs = { text = "Text" }
output = "Text"
prompt = "Draft $text"

[pipe.judge]
type = "PipeLLM"
description = "Judge the draft"
inputs = { draft = "Text" }
output = "Text"
prompt = "Judge $draft"

[pipe.route]
type = "PipeCondition"
description = "Rewrite from scratch or polish the draft"
inputs = { verdict = "Text", text = "Text", draft = "Text" }
output = "Text"
expression = "verdict"
outcomes = { rewrite = "a_rewrite", polish = "b_polish" }
default_outcome = "b_polish"

[pipe.a_rewrite]
type = "PipeLLM"
description = "Rewrite from the original text"
inputs = { text = "Text" }
output = "Text"
prompt = "Rewrite $text"

[pipe.b_polish]
type = "PipeLLM"
description = "Polish the draft"
inputs = { draft = "Text" }
output = "Text"
prompt = "Polish $draft"
"""

    # The outcomes write different concepts and multiplicities, so only the condition's declaration
    # covers both: the shared stuff is typed `Anything`, single.
    DIFFERING_OUTCOMES_MTHDS: ClassVar[str] = """
domain = "dry_condition_differing_outcomes"
description = "A condition whose outcomes write different concepts"
main_pipe = "screen"

[concept.Question]
description = "An interview question"
refines = "Text"

[concept.Rejection]
description = "A rejection letter"
refines = "Text"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { fit = "write_questions", no_fit = "write_rejection" }
default_outcome = "write_rejection"

[pipe.write_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "Question[]"
prompt = "Questions for $cv"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Rejection"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Anything" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

    # An outcome that is a sequence: its last step's output is the sequence's output, so it moves too.
    SEQUENCE_OUTCOME_MTHDS: ClassVar[str] = """
domain = "dry_condition_sequence_outcome"
description = "A condition whose non-default outcome is a sequence"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Text"
expression = "verdict"
outcomes = { fit = "questions_flow", no_fit = "write_rejection" }
default_outcome = "write_rejection"

[pipe.questions_flow]
type = "PipeSequence"
description = "Draft then finalize the questions"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "draft_questions", result = "question_draft" },
  { pipe = "finalize_questions", result = "questions" },
]

[pipe.draft_questions]
type = "PipeLLM"
description = "Draft the questions"
inputs = { cv = "Text" }
output = "Text"
prompt = "Draft questions for $cv"

[pipe.finalize_questions]
type = "PipeLLM"
description = "Finalize the questions"
inputs = { question_draft = "Text" }
output = "Text"
prompt = "Finalize $question_draft"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Text"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Text" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

    # An outcome that is a batch: the aggregate edge into its output list names that list's digest,
    # which moves onto the condition's.
    BATCH_OUTCOME_MTHDS: ClassVar[str] = """
domain = "dry_condition_batch_outcome"
description = "A condition whose non-default outcome is a batch"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV over topics"
inputs = { cv = "Text", topics = "Text[]" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text", topics = "Text[]" }
output = "Text[]"
expression = "verdict"
outcomes = { fit = "ask_each_topic", no_fit = "write_rejections" }
default_outcome = "write_rejections"

[pipe.ask_each_topic]
type = "PipeBatch"
description = "Ask one question per topic"
inputs = { topics = "Text[]" }
output = "Text[]"
branch_pipe_code = "ask_topic"
input_list_name = "topics"
input_item_name = "topic"

[pipe.ask_topic]
type = "PipeLLM"
description = "Ask a question on one topic"
inputs = { topic = "Text" }
output = "Text"
prompt = "Ask about $topic"

[pipe.write_rejections]
type = "PipeLLM"
description = "Write rejection paragraphs"
inputs = { cv = "Text" }
output = "Text[]"
prompt = "Rejection paragraphs for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Text[]" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

    # An outcome that is itself a condition hands back only its last outcome's stuff, `summarize_cv`'s
    # Text, as does the outer default. Both conditions declare `Anything`, which only the
    # declarations reveal: the outer condition's shared stuff, written by a Number and two Texts,
    # must be typed `Anything`.
    NESTED_CONDITIONS_MTHDS: ClassVar[str] = """
domain = "dry_condition_nested_conditions"
description = "A condition whose non-default outcome is a condition"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "outer", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.outer]
type = "PipeCondition"
description = "Score the CV or write a note"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { scored = "inner" }
default_outcome = "write_note"

[pipe.inner]
type = "PipeCondition"
description = "Score the CV or summarize it"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { numeric = "score_cv" }
default_outcome = "summarize_cv"

[pipe.score_cv]
type = "PipeLLM"
description = "Score the CV"
inputs = { cv = "Text" }
output = "Number"
prompt = "Score $cv"

[pipe.summarize_cv]
type = "PipeLLM"
description = "Summarize the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Summarize $cv"

[pipe.write_note]
type = "PipeLLM"
description = "Write a note"
inputs = { cv = "Text" }
output = "Text"
prompt = "Note on $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Anything" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

    # An outcome that is a parallel: it writes the shared stuff as a controller, combining its
    # branches into it, so it is no producer of it, and the stuff still has two writers.
    PARALLEL_OUTCOME_MTHDS: ClassVar[str] = """
domain = "dry_condition_parallel_outcome"
description = "A condition whose non-default outcome is a parallel"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { fit = "write_both" }
default_outcome = "write_rejection"

[pipe.write_both]
type = "PipeParallel"
description = "Write questions and notes at once"
inputs = { cv = "Text" }
output = "Composite"
add_each_output = true
branches = [
  { pipe = "write_questions", result = "questions" },
  { pipe = "write_notes", result = "notes" },
]

[pipe.write_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "Text"
prompt = "Questions for $cv"

[pipe.write_notes]
type = "PipeLLM"
description = "Write interview notes"
inputs = { cv = "Text" }
output = "Text"
prompt = "Notes for $cv"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Text"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Anything" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

    # A condition run as a batch's branch: the batch gives the branch its stuff code, so both
    # outcomes mint the same digest and nothing is merged, but they write a Number and a Text, so
    # the condition's `Anything` must still type the stuff.
    BATCH_BRANCH_CONDITION_MTHDS: ClassVar[str] = """
domain = "dry_condition_batch_branch"
description = "A batch whose branch is a condition with differing outcomes"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen topics"
inputs = { topics = "Text[]" }
output = "Text"
steps = [
  { pipe = "route_each", result = "follow_ups" },
  { pipe = "assemble", result = "result" },
]

[pipe.route_each]
type = "PipeBatch"
description = "Route each topic"
inputs = { topics = "Text[]" }
output = "Anything[]"
branch_pipe_code = "route"
input_list_name = "topics"
input_item_name = "topic"

[pipe.route]
type = "PipeCondition"
description = "Score or summarize one topic"
inputs = { topic = "Text" }
output = "Anything"
expression = "topic"
outcomes = { numeric = "score_topic" }
default_outcome = "summarize_topic"

[pipe.score_topic]
type = "PipeLLM"
description = "Score the topic"
inputs = { topic = "Text" }
output = "Number"
prompt = "Score $topic"

[pipe.summarize_topic]
type = "PipeLLM"
description = "Summarize the topic"
inputs = { topic = "Text" }
output = "Text"
prompt = "Summarize $topic"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the follow-ups"
inputs = { follow_ups = "Anything[]" }
output = "Text"
prompt = "Assemble $follow_ups"
"""

    # The main sequence ends on the condition, so the sequence's output is the condition's shared
    # stuff, and the sequence comes before the condition in node order: a reader typing a stuff by
    # its first item would see the sequence's item first.
    WRAPPED_CONDITION_MTHDS: ClassVar[str] = """
domain = "dry_condition_wrapped"
description = "A sequence whose last step is a condition with differing outcomes"
main_pipe = "screen_candidate"

[concept.InterviewQuestion]
description = "An interview question"
refines = "Text"

[concept.Email]
description = "An email"
refines = "Text"

[pipe.screen_candidate]
type = "PipeSequence"
description = "Judge a CV, then write questions or a refusal"
inputs = { cv = "Text" }
output = "Anything"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route_on_match", result = "decision_output" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route_on_match]
type = "PipeCondition"
description = "Write questions or a refusal on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { fit = "generate_interview_questions", no_fit = "write_refusal_email" }
default_outcome = "fail"

[pipe.generate_interview_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "InterviewQuestion[]"
prompt = "Questions for $cv"

[pipe.write_refusal_email]
type = "PipeLLM"
description = "Write a refusal"
inputs = { cv = "Text" }
output = "Email"
prompt = "Refusal for $cv"
"""

    # A sequence step batched over a list runs a branch sequence per item, each ending on its own run
    # of the condition, so each branch sequence's output is that run's shared stuff.
    BATCH_BRANCH_SEQUENCE_MTHDS: ClassVar[str] = """
domain = "dry_condition_batch_branch_sequence"
description = "A batch whose branch is a sequence ending on a condition with differing outcomes"
main_pipe = "screen_cvs"

[concept.InterviewQuestion]
description = "An interview question"
refines = "Text"

[pipe.screen_cvs]
type = "PipeSequence"
description = "Screen every CV"
inputs = { cvs = "Text[]" }
output = "Anything[]"
steps = [
  { pipe = "screen_single_cv", batch_over = "cvs", batch_as = "cv", result = "results" },
]

[pipe.screen_single_cv]
type = "PipeSequence"
description = "Judge one CV, then write questions or a refusal"
inputs = { cv = "Text" }
output = "Anything"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route_by_match", result = "output" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route_by_match]
type = "PipeCondition"
description = "Write questions or a refusal on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { yes = "generate_interview_questions", no = "write_refusal_email" }
default_outcome = "fail"

[pipe.generate_interview_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "InterviewQuestion[]"
prompt = "Questions for $cv"

[pipe.write_refusal_email]
type = "PipeLLM"
description = "Write a refusal"
inputs = { cv = "Text" }
output = "Text"
prompt = "Refusal for $cv"
"""
