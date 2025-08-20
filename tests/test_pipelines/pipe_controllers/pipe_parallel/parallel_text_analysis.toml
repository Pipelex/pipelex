domain = "test_integration"
definition = "Test pipes for PipeParallel text analysis"

[pipe]

[pipe.analyze_sentiment]
type = "PipeLLM"
definition = "Analyze sentiment of text"
inputs = { input_text = "Text" }
output = "Text"
prompt_template = """Analyze the sentiment of the following text and return only one word: positive, negative, or neutral.

@input_text.text

Sentiment:"""

[pipe.count_words]
type = "PipeLLM"
definition = "Count words in text"
inputs = { input_text = "Text" }
output = "Text"
prompt_template = """Count the number of words in the following text and return only the number:

@input_text.text

Word count:"""

[pipe.extract_keywords]
type = "PipeLLM"
definition = "Extract keywords from text"
inputs = { input_text = "Text" }
output = "Text"
prompt_template = """Extract the top 3 keywords from the following text. Return them as a comma-separated list:

@input_text.text

Keywords:"""

