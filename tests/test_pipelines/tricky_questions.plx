domain = "test_tricky_questions"
description = "Domain for testing tricky questions"

[concept]
AnswerToAQuestion = "Answer to a question"
Question = "A question"
QuestionAnalysis = "Analysis of a question"
ThoughtfulAnswerConclusion = "Conclusion of a thoughtful answer"

[concept.ThoughtfulAnswer]
description = "A thoughtful answer to a question"

[pipe]
[pipe.analyse_question_tricky]
type = "PipeLLM"
description = "Analyze a question to determine whether it's straightforward or tricky"
inputs = { question = "Question" }
output = "QuestionAnalysis"
model = "llm_to_engineer"
prompt = """
Here is a question for an LLM:
@question
Do you think it's tricky, or maybe even a deceptive trap?
Does it assume things that are not necessarily true?
Does it suggest patterns that aren't applicable?
Please explain what you think and then give a rating between 0 to 100 of trickiness and another rating between 0 to 100 of deceptiveness.
If there's an obvious trap, state it without getting into details.
"""

[pipe.answer_after_analysis]
type = "PipeLLM"
description = "Answer knowingly after analyzing a question"
inputs = { question = "Question", question_analysis = "QuestionAnalysis" }
output = "ThoughtfulAnswer"
model = "llm_to_engineer"
prompt = """
A question was asked:
@question
A thoughtful analysis was given:
@question_analysis
If the question was tricky or deceptive, don't get fooled!
Answer in 4 parts:
1- the_trap: Explain the trap in a 1 sentence
2- the_counter: Counter by stating the right way to think about the question and avoid the trap
3- the_lesson: Did we learn anything?
4- the_answer: Then give a good answer expressed without mentioning the trap
"""

[pipe.conclude_thoughtful_answer]
type = "PipeCompose"
description = "Conclude a thoughtful answer"
inputs = { thoughtful_answer = "ThoughtfulAnswer" }
output = "ThoughtfulAnswerConclusion"
template = "After analyzing the question, here is my answer: $thoughtful_answer.the_answer"


[pipe.conclude_tricky_question_by_steps]
type = "PipeSequence"
description = "Answer a tricky question by first analyzing its trickiness and then concluding"
inputs = { question = "Question" }
output = "ThoughtfulAnswerConclusion"
steps = [
    { pipe = "analyse_question_tricky", result = "question_analysis" },
    { pipe = "answer_after_analysis", result = "thoughtful_answer" },
    { pipe = "conclude_thoughtful_answer", result = "thoughtful_answer_conclusion" },
]

