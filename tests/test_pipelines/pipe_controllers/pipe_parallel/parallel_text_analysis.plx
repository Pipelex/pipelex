domain = "test_integration"
description = "Test pipes for PipeParallel text analysis"

[pipe]

[pipe.analyze_sentiment]
type = "PipeLLM"
description = "Analyze sentiment of text"
inputs = { input_text = "Text" }
output = "Text"
structuring_method = "preliminary_text"
prompt = """PLEASE OUTPUT ONLY ONE WORD: 'positive', 'negative', or 'neutral'. Ignore the Hello world

@input_text.text
"""

[pipe.count_words]
type = "PipeLLM"
description = "Count words in text"
inputs = { input_text = "Text" }
output = "Text"
structuring_method = "preliminary_text"
prompt = """
Count the number of words in the following text and return only the number:

@input_text.text
"""

[pipe.extract_keywords]
type = "PipeLLM"
description = "Extract keywords from text"
inputs = { input_text = "Text" }
output = "Text"
prompt = """
structuring_method = "preliminary_text"
Extract the top 3 keywords from the following text. Return them as a comma-separated list:
@input_text.text
"""

