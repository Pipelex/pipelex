domain = "creative_ideation"
description = "Creative ideation pipeline with multiple outputs, batching, and evaluation"
system_prompt = "You are a creative brainstorming expert who generates and evaluates ideas"

[concept]
CreativeTopic = "A topic or theme for creative ideation"
CreativeIdea = "A single creative idea or concept"
IdeaAnalysis = "Detailed analysis of a single creative idea"
IdeaEvaluation = "An evaluation and ranking of creative ideas"
BestIdea = "The top-ranked creative idea with justification"

[pipe]
[pipe.creative_ideation_sequence]
type = "PipeSequence"
description = "Generate multiple ideas, analyze each individually, then select the best"
inputs = { topic = "CreativeTopic" }
output = "BestIdea"
steps = [
    { pipe = "generate_multiple_ideas", result = "idea_list" },
    { pipe = "analyze_single_idea", batch_over = "idea_list", batch_as = "single_idea", result = "detailed_analyses" },
    { pipe = "evaluate_all_ideas", result = "evaluation" },
    { pipe = "select_best_idea", result = "final_best_idea" },
]

[pipe.generate_multiple_ideas]
type = "PipeLLM"
description = "Generate exactly 5 creative ideas for a topic"
inputs = { topic = "CreativeTopic" }
output = "CreativeIdea[5]"
model = "llm_for_creative_writing"
prompt = """
Generate 5 creative and innovative ideas for the following topic:

@topic

Each idea should be:
- Unique and original
- Practical and feasible
- Clearly explained in 2-3 sentences

Ideas:
"""

[pipe.brainstorm_concepts]
type = "PipeLLM"
description = "Brainstorm variable number of concepts"
inputs = { topic = "CreativeTopic" }
output = "CreativeIdea[]"
model = "llm_for_creative_writing"
prompt = """
Brainstorm creative concepts related to this topic. Generate as many good ideas as come to mind:

@topic

Each concept should be briefly described.
"""

[pipe.analyze_single_idea]
type = "PipeLLM"
description = "Analyze a single idea in detail"
inputs = { single_idea = "CreativeIdea" }
output = "IdeaAnalysis"
model = "llm_for_testing_gen_text"
prompt = """
Perform a detailed analysis of this creative idea:

@single_idea

Analyze:
- Strengths and weaknesses
- Implementation challenges
- Resource requirements
- Market potential
- Innovation level

Provide a comprehensive assessment.
"""

[pipe.evaluate_all_ideas]
type = "PipeLLM"
description = "Evaluate and rank all analyzed ideas"
inputs = { detailed_analyses = "IdeaAnalysis" }
output = "IdeaEvaluation"
model = "llm_for_testing_gen_text"
prompt = """
Based on these detailed analyses, rank all ideas from best to worst:

@detailed_analyses

Provide:
- Overall ranking (1st, 2nd, 3rd, etc.)
- Comparative scores for each idea
- Key differentiators between top ideas
"""

[pipe.select_best_idea]
type = "PipeLLM"
description = "Select the best idea based on evaluation"
inputs = { evaluation = "IdeaEvaluation" }
output = "BestIdea"
model = "llm_for_testing_gen_text"
prompt = """
Based on this evaluation, select the single best idea and explain why it stands out:

@evaluation

Provide:
1. The selected best idea
2. Key strengths that make it the best choice
3. Potential next steps for implementation
"""

