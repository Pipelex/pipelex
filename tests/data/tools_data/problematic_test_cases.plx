domain = "test_validation_failures"   
definition = "Test cases with various validation issues"	

[concept]
TestInput = "A test input concept"

[pipe]
[pipe.test_pipe_with_issues]
type = "PipeLLM"
definition = "Test pipe with trailing whitespace issues"
inputs = { input_data = "TestInput" }
output = "native.Text"
prompt_template = """
This template has trailing whitespace after closing quotes
""" 

[pipe.another_problematic_pipe]
type = "PipeLLM"
definition = "Another pipe with issues"  
output = "native.Text"
prompt_template = """
Multiple issues here
""" 
