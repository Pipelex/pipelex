domain = "test_pipe_parallel"
description = "Simple test for PipeParallel functionality"

[concept]
DocumentInput = "Input document with text content"
LengthAnalysis = "Analysis of document length and structure"
ContentAnalysis = "Analysis of document content and themes"
CombinedAnalysis = "Combined analysis results from parallel processing"

[pipe]
[pipe.parallel_document_analysis]
type = "PipeParallel"
description = "Analyze document length and content in parallel"
inputs = { document = "DocumentInput" }
output = "CombinedAnalysis"
add_each_output = true
combined_output = "CombinedAnalysis"
parallels = [
    { pipe = "analyze_length", result = "length_result" },
    { pipe = "analyze_content", result = "content_result" },
]

[pipe.analyze_length]
type = "PipeLLM"
description = "Analyze document length and structure"
inputs = { document = "DocumentInput" }
output = "LengthAnalysis"
model = "llm_for_testing_gen_text"
prompt = """
Analyze the length and structure of this document:

@document.text

Provide a brief analysis focusing on:
- Word count estimation
- Paragraph structure
- Document organization
"""

[pipe.analyze_content]
type = "PipeLLM"
description = "Analyze document content and themes"
inputs = { document = "DocumentInput" }
output = "ContentAnalysis"
model = "llm_for_testing_gen_text"
prompt = """
Analyze the content and themes of this document:

@document.text

Provide a brief analysis focusing on:
- Main themes and topics
- Key concepts discussed
- Overall content summary
"""

