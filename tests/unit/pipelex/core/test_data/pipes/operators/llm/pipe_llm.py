from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

# Basic PipeLLM with prompt_template
PIPE_LLM_BASIC = (
    "pipe_llm_basic",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.generate_text]
type = "PipeLLM"
definition = "Generate text using LLM"
output = "Text"
prompt_template = "Generate a story about a programmer"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "generate_text": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Generate text using LLM",
                output=NativeConceptEnum.TEXT,
                prompt_template="Generate a story about a programmer",
            ),
        },
    ),
)

# PipeLLM with inputs and template variables
PIPE_LLM_WITH_INPUTS = (
    "pipe_llm_with_inputs",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.extract_info]
type = "PipeLLM"
definition = "Extract information from text"
inputs = { text = "Text", topic = "Text" }
output = "Text"
prompt_template = "Extract information about $topic from this text:\\n\\n@text"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "extract_info": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Extract information from text",
                inputs={"text": "Text", "topic": "Text"},
                output=NativeConceptEnum.TEXT,
                prompt_template="Extract information about $topic from this text:\n\n@text",
            ),
        },
    ),
)

# PipeLLM with system prompt
PIPE_LLM_WITH_SYSTEM_PROMPT = (
    "pipe_llm_with_system_prompt",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.expert_analysis]
type = "PipeLLM"
definition = "Expert analysis with system prompt"
output = "Text"
system_prompt = "You are a data analysis expert with 20 years of experience"
prompt_template = "Analyze the following data and provide insights"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "expert_analysis": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Expert analysis with system prompt",
                output=NativeConceptEnum.TEXT,
                system_prompt="You are a data analysis expert with 20 years of experience",
                prompt_template="Analyze the following data and provide insights",
            ),
        },
    ),
)

# PipeLLM with multiple outputs (nb_output)
PIPE_LLM_MULTIPLE_OUTPUTS = (
    "pipe_llm_multiple_outputs",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.generate_ideas]
type = "PipeLLM"
definition = "Generate multiple ideas"
output = "Text"
nb_output = 3
prompt_template = "Generate creative ideas for a mobile app"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "generate_ideas": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Generate multiple ideas",
                output=NativeConceptEnum.TEXT,
                nb_output=3,
                prompt_template="Generate creative ideas for a mobile app",
            ),
        },
    ),
)

# PipeLLM with dynamic multiple outputs
PIPE_LLM_DYNAMIC_MULTIPLE = (
    "pipe_llm_dynamic_multiple",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.brainstorm_solutions]
type = "PipeLLM"
definition = "Brainstorm multiple solutions"
inputs = { problem = { concept = "Text" } }
output = "Text"
multiple_output = true
prompt_template = "Brainstorm solutions for this problem: @problem"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "brainstorm_solutions": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Brainstorm multiple solutions",
                inputs={"problem": InputRequirementBlueprint(concept="Text")},
                output=NativeConceptEnum.TEXT,
                multiple_output=True,
                prompt_template="Brainstorm solutions for this problem: @problem",
            ),
        },
    ),
)

# PipeLLM with vision (Image input)
PIPE_LLM_VISION = (
    "pipe_llm_vision",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.analyze_image]
type = "PipeLLM"
definition = "Analyze image content"
inputs = { image = "Image" }
output = "Text"
prompt_template = "Describe what you see in this image in detail"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "analyze_image": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Analyze image content",
                inputs={"image": "Image"},
                output=NativeConceptEnum.TEXT,
                prompt_template="Describe what you see in this image in detail",
            ),
        },
    ),
)

# PipeLLM with template name instead of inline template
PIPE_LLM_TEMPLATE_NAME = (
    "pipe_llm_template_name",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.use_template]
type = "PipeLLM"
definition = "Use named template"
inputs = { data = "Text" }
output = "Text"
template_name = "analysis_template"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "use_template": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Use named template",
                inputs={"data": "Text"},
                output=NativeConceptEnum.TEXT,
                template_name="analysis_template",
            ),
        },
    ),
)

# PipeLLM with fixed prompt (no template)
PIPE_LLM_FIXED_PROMPT = (
    "pipe_llm_fixed_prompt",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.simple_generation]
type = "PipeLLM"
definition = "Simple text generation with fixed prompt"
output = "Text"
prompt = "Write a haiku about programming"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "simple_generation": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Simple text generation with fixed prompt",
                output=NativeConceptEnum.TEXT,
                prompt="Write a haiku about programming",
            ),
        },
    ),
)

# PipeLLM with system prompt template
PIPE_LLM_SYSTEM_TEMPLATE = (
    "pipe_llm_system_template",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.contextual_analysis]
type = "PipeLLM"
definition = "Analysis with dynamic system prompt"
inputs = { expertise_level = "Text", content = "Text" }
output = "Text"
system_prompt_template = "You are an expert with $expertise_level level knowledge"
prompt_template = "Analyze this content: @content"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "contextual_analysis": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Analysis with dynamic system prompt",
                inputs={"expertise_level": "Text", "content": "Text"},
                output=NativeConceptEnum.TEXT,
                system_prompt_template="You are an expert with $expertise_level level knowledge",
                prompt_template="Analyze this content: @content",
            ),
        },
    ),
)

# PipeLLM with custom structured output (non-native concept)
PIPE_LLM_STRUCTURED_OUTPUT = (
    "pipe_llm_structured_output",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[concept]
PersonInfo = "Information about a person"

[pipe.extract_person_info]
type = "PipeLLM"
definition = "Extract structured person information"
inputs = { text = { concept = "Text", multiplicity = 1 } }
output = "PersonInfo"
prompt_template = "Extract person information from this text: @text"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        concept={"PersonInfo": "Information about a person"},
        pipe={
            "extract_person_info": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Extract structured person information",
                inputs={"text": InputRequirementBlueprint(concept="Text", multiplicity=1)},
                output="PersonInfo",
                prompt_template="Extract person information from this text: @text",
            ),
        },
    ),
)

# PipeLLM with boolean multiplicity values
PIPE_LLM_BOOLEAN_MULTIPLICITY = (
    "pipe_llm_boolean_multiplicity",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[concept]
DocumentSummary = "Summary of a document"

[pipe.analyze_documents]
type = "PipeLLM"
definition = "Analyze multiple documents and single query"
inputs = { documents = { concept = "Text", multiplicity = true }, query = { concept = "Text", multiplicity = false } }
output = "DocumentSummary"
prompt_template = "Analyze these documents based on the query: $query\\n\\nDocuments: @documents"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        concept={"DocumentSummary": "Summary of a document"},
        pipe={
            "analyze_documents": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Analyze multiple documents and single query",
                inputs={
                    "documents": InputRequirementBlueprint(concept="Text", multiplicity=True),
                    "query": InputRequirementBlueprint(concept="Text", multiplicity=False),
                },
                output="DocumentSummary",
                prompt_template="Analyze these documents based on the query: $query\n\nDocuments: @documents",
            ),
        },
    ),
)

# Export all PipeLLM test cases
PIPE_LLM_TEST_CASES = [
    PIPE_LLM_BASIC,
    PIPE_LLM_WITH_INPUTS,
    PIPE_LLM_WITH_SYSTEM_PROMPT,
    PIPE_LLM_MULTIPLE_OUTPUTS,
    PIPE_LLM_DYNAMIC_MULTIPLE,
    PIPE_LLM_VISION,
    PIPE_LLM_TEMPLATE_NAME,
    PIPE_LLM_FIXED_PROMPT,
    PIPE_LLM_SYSTEM_TEMPLATE,
    PIPE_LLM_STRUCTURED_OUTPUT,
    PIPE_LLM_BOOLEAN_MULTIPLICITY,
]
