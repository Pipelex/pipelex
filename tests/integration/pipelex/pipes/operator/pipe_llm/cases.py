class LLMSettingCheckTestData:
    """Bundles whose one step generates with a model setting the model it resolves to may refuse.

    The models are the dev configuration's OpenAI entries, on the Responses SDK: one declares no thinking
    (`thinking_mode = "none"`), so it takes no reasoning setting, and the other thinks under a reasoning
    effort but takes no reasoning budget, which only Anthropic and Gemini take.
    """

    MODEL_WITHOUT_THINKING = "gpt-4o-mini"
    MODEL_WITH_EFFORT = "gpt-5.4-mini"

    @classmethod
    def pipe_llm_bundle(cls, *, output: str, model_fields: str) -> str:
        return f"""
domain = "llm_setting_check"
description = "A step generating with a model setting"

[concept.Verdict]
description = "A verdict on a question"

[concept.Verdict.structure]
answer = {{ type = "text", description = "The answer", required = true }}

[pipe.answer_it]
type = "PipeLLM"
description = "Answer the question"
inputs = {{ question = "Text" }}
output = "{output}"
prompt = "Answer this question: $question"
{model_fields}
"""

    @classmethod
    def pipe_structure_bundle(cls, *, model_fields: str) -> str:
        return f"""
domain = "llm_setting_check"
description = "A step structuring a text with a model setting"

[concept.Verdict]
description = "A verdict on a question"

[concept.Verdict.structure]
answer = {{ type = "text", description = "The answer", required = true }}

[pipe.structure_it]
type = "PipeStructure"
description = "Structure the answer"
inputs = {{ draft = "Text" }}
output = "Verdict"
{model_fields}
"""
