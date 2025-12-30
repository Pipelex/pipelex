domain = "test_pipe_condition_continue_output_type"
description = "Test PipeCondition with continue outcome and different input/output types"

[concept]
VerifiedLink = "A verified link with a verdict"
Constraint = "A mathematical price constraint"

[pipe]
[pipe.main_sequence]
type = "PipeSequence"
description = "Sequence that verifies a link and then routes it based on verdict."
inputs = { input_text = "Text" }
output = "Constraint[]"
steps = [
    { pipe = "verify_link", result = "verified_link" },
    { pipe = "build_or_skip", result = "constraints" }
]

[pipe.verify_link]
type = "PipeLLM"
description = "Analyzes input text and outputs a verified link with a verdict."
inputs = { input_text = "Text" }
output = "VerifiedLink"
prompt = """
@input_text

Analyze the input and output a verified link with a verdict (approved or rejected).
"""

[pipe.build_or_skip]
type = "PipeCondition"
description = "Routes approved links to builder, rejected links to skip (continue)."
inputs = { verified_link = "VerifiedLink" }
output = "Constraint[]"
expression_template = "{{ verified_link.verdict }}"
default_outcome = "continue"

[pipe.build_or_skip.outcomes]
approved = "build_single_constraint"
rejected = "continue"

[pipe.build_single_constraint]
type = "PipeLLM"
description = "Converts an approved verified link into a mathematical price constraint."
inputs = { verified_link = "VerifiedLink" }
output = "Constraint[]"
prompt = """
@verified_link

Convert to a price constraint.
The math: If A → B, then Price(A) ≤ Price(B).

Output a constraint with:
- expression: "Price({{ verified_link.source }}_Yes) <= Price({{ verified_link.target }}_Yes)"
- description: "{{ verified_link.source }} implies {{ verified_link.target }}"
"""
