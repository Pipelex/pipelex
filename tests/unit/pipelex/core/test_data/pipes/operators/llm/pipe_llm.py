# ruff: noqa: E501
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

# Basic PipeLLM with prompt_template
PIPE_LLM_BASIC = (
    "pipe_llm_basic",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.generate_text]
type = "PipeLLM"
description = "Generate text using LLM"
output = "Text"
prompt = "Generate a story about a programmer"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "generate_text": PipeLLMBlueprint(
                type="PipeLLM",
                description="Generate text using LLM",
                output=NativeConceptCode.TEXT,
                prompt="Generate a story about a programmer",
            ),
        },
    ),
)

# PipeLLM with inputs and template variables
PIPE_LLM_WITH_INPUTS = (
    "pipe_llm_with_inputs",
    '''domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.extract_info]
type = "PipeLLM"
description = "Extract information from text"
inputs = { text = "Text", topic = "Text" }
output = "Text"
prompt = """
Extract information about $topic from this text:

@text
"""
''',
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "extract_info": PipeLLMBlueprint(
                type="PipeLLM",
                description="Extract information from text",
                inputs={"text": "Text", "topic": "Text"},
                output=NativeConceptCode.TEXT,
                prompt="Extract information about $topic from this text:\n\n@text\n",
            ),
        },
    ),
)

# PipeLLM with system prompt
PIPE_LLM_WITH_SYSTEM_PROMPT = (
    "pipe_llm_with_system_prompt",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.expert_analysis]
type = "PipeLLM"
description = "Expert analysis with system prompt"
output = "Text"
system_prompt = "You are a data analysis expert with 20 years of experience"
prompt = "Analyze the following data and provide insights"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "expert_analysis": PipeLLMBlueprint(
                type="PipeLLM",
                description="Expert analysis with system prompt",
                output=NativeConceptCode.TEXT,
                system_prompt="You are a data analysis expert with 20 years of experience",
                prompt="Analyze the following data and provide insights",
            ),
        },
    ),
)

# PipeLLM with long prompt
PIPE_LLM_WITH_LONG_PROMPT = (
    "pipe_llm_with_long_prompt",
    '''domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.expert_analysis]
type = "PipeLLM"
description = "Expert analysis with system prompt"
output = "Text"
prompt = """
Extract all articles/items from this invoice text: $extracted_text. For each item find: item name, quantity, unit price, total price, description, and product code if
 available. Return each article as separate structured data.
"""
''',
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "expert_analysis": PipeLLMBlueprint(
                type="PipeLLM",
                description="Expert analysis with system prompt",
                output=NativeConceptCode.TEXT,
                prompt="""Extract all articles/items from this invoice text: $extracted_text. For each item find: item name, quantity, unit price, total price, description, and product code if
 available. Return each article as separate structured data.
""",
            ),
        },
    ),
)
# PipeLLM with multiple outputs (nb_output)
PIPE_LLM_MULTIPLE_OUTPUTS = (
    "pipe_llm_multiple_outputs",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.generate_ideas]
type = "PipeLLM"
description = "Generate multiple ideas"
output = "Text[3]"
prompt = "Generate creative ideas for a mobile app"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "generate_ideas": PipeLLMBlueprint(
                type="PipeLLM",
                description="Generate multiple ideas",
                output="Text[3]",
                prompt="Generate creative ideas for a mobile app",
            ),
        },
    ),
)

# PipeLLM with dynamic multiple outputs
PIPE_LLM_DYNAMIC_MULTIPLE = (
    "pipe_llm_dynamic_multiple",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.brainstorm_solutions]
type = "PipeLLM"
description = "Brainstorm multiple solutions"
inputs = { problem = "Text" }
output = "Text[]"
prompt = "Brainstorm solutions for this problem: $problem"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "brainstorm_solutions": PipeLLMBlueprint(
                type="PipeLLM",
                description="Brainstorm multiple solutions",
                inputs={"problem": "Text"},
                output="Text[]",
                prompt="Brainstorm solutions for this problem: $problem",
            ),
        },
    ),
)

# PipeLLM with vision (Image input)
PIPE_LLM_VISION = (
    "pipe_llm_vision",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.analyze_image]
type = "PipeLLM"
description = "Analyze image content"
inputs = { image = "Image" }
output = "Text"
prompt = "Describe what you see in this image in detail"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "analyze_image": PipeLLMBlueprint(
                type="PipeLLM",
                description="Analyze image content",
                inputs={"image": "Image"},
                output=NativeConceptCode.TEXT,
                prompt="Describe what you see in this image in detail",
            ),
        },
    ),
)

# PipeLLM with fixed prompt (not an actual template)
PIPE_LLM_FIXED_PROMPT = (
    "pipe_llm_fixed_prompt",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.simple_generation]
type = "PipeLLM"
description = "Simple text generation with fixed prompt"
output = "Text"
prompt = "Write a haiku about programming"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "simple_generation": PipeLLMBlueprint(
                type="PipeLLM",
                description="Simple text generation with fixed prompt",
                output=NativeConceptCode.TEXT,
                prompt="Write a haiku about programming",
            ),
        },
    ),
)

# PipeLLM with system prompt template
PIPE_LLM_SYSTEM_TEMPLATE = (
    "pipe_llm_system_template",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[pipe.contextual_analysis]
type = "PipeLLM"
description = "Analysis with dynamic system prompt"
inputs = { expertise_level = "Text", content = "Text" }
output = "Text"
system_prompt = "You are an expert with $expertise_level level knowledge"
prompt = "Analyze this content: @content"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        pipe={
            "contextual_analysis": PipeLLMBlueprint(
                type="PipeLLM",
                description="Analysis with dynamic system prompt",
                inputs={"expertise_level": "Text", "content": "Text"},
                output=NativeConceptCode.TEXT,
                system_prompt="You are an expert with $expertise_level level knowledge",
                prompt="Analyze this content: @content",
            ),
        },
    ),
)

# PipeLLM with custom structured output (non-native concept)
PIPE_LLM_STRUCTURED_OUTPUT = (
    "pipe_llm_structured_output",
    """domain = "test_pipes"
description = "Domain with pipe definitions"

[concept]
PersonInfo = "Information about a person"

[pipe.extract_person_info]
type = "PipeLLM"
description = "Extract structured person information"
inputs = { text = "Text[1]" }
output = "PersonInfo"
prompt = "Extract person information from this text: @text"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        concept={"PersonInfo": "Information about a person"},
        pipe={
            "extract_person_info": PipeLLMBlueprint(
                type="PipeLLM",
                description="Extract structured person information",
                inputs={"text": "Text[1]"},
                output="PersonInfo",
                prompt="Extract person information from this text: @text",
            ),
        },
    ),
)

# PipeLLM with boolean multiplicity values
PIPE_LLM_BOOLEAN_MULTIPLICITY = (
    "pipe_llm_boolean_multiplicity",
    '''domain = "test_pipes"
description = "Domain with pipe definitions"

[concept]
DocumentSummary = "Summary of a document"

[pipe.analyze_documents]
type = "PipeLLM"
description = "Analyze multiple documents and single query"
inputs = { documents = "Text[]", query = "Text" }
output = "DocumentSummary"
prompt = """
Analyze these documents based on the query: $query

Documents: @documents
"""
''',
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with pipe definitions",
        concept={"DocumentSummary": "Summary of a document"},
        pipe={
            "analyze_documents": PipeLLMBlueprint(
                type="PipeLLM",
                description="Analyze multiple documents and single query",
                inputs={
                    "documents": "Text[]",
                    "query": "Text",
                },
                output="DocumentSummary",
                prompt="""Analyze these documents based on the query: $query

Documents: @documents
""",
            ),
        },
    ),
)

# Export all PipeLLM test cases
PIPE_LLM_TEST_CASES = [
    PIPE_LLM_BASIC,
    PIPE_LLM_WITH_INPUTS,
    PIPE_LLM_WITH_SYSTEM_PROMPT,
    PIPE_LLM_WITH_LONG_PROMPT,
    PIPE_LLM_MULTIPLE_OUTPUTS,
    PIPE_LLM_DYNAMIC_MULTIPLE,
    PIPE_LLM_VISION,
    PIPE_LLM_FIXED_PROMPT,
    PIPE_LLM_SYSTEM_TEMPLATE,
    PIPE_LLM_STRUCTURED_OUTPUT,
    PIPE_LLM_BOOLEAN_MULTIPLICITY,
]
