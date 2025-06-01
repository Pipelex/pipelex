from typing import Any, ClassVar, Dict, List

from pydantic import BaseModel

from pipelex.cogt.image.prompt_image import PromptImagePath
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_prompt_template_inputs import LLMPromptTemplateInputs

proto_prompt = LLMPrompt(
    user_text="Some user text in the template",
)

base_template_inputs_1 = LLMPromptTemplateInputs(
    root={"foo": "bar"},
)

my_prompt_template_model_1 = LLMPromptTemplate(
    proto_prompt=proto_prompt,
    base_template_inputs=base_template_inputs_1,
)

base_template_inputs_2 = LLMPromptTemplateInputs(
    root={},
)

my_prompt_template_model_2 = LLMPromptTemplate(
    proto_prompt=proto_prompt,
    base_template_inputs=base_template_inputs_2,
)

dict_1 = {
    "proto_prompt": LLMPrompt(
        system_text=None,
        user_text="Some user text in the template",
        user_images=[],
    ),
    "base_template_inputs": LLMPromptTemplateInputs(root={}),
    "source_system_template_name": None,
    "source_user_template_name": "markdown_reordering_vision_claude3_5_sonnet",
}

prompt_with_image_path = LLMPrompt(
    system_text="Some system text",
    user_text="Some user text",
    user_images=[
        PromptImagePath(file_path="some_file_path"),
    ],
)


class SerDeTestCases:
    PYDANTIC_EXAMPLES: ClassVar[List[BaseModel]] = [
        my_prompt_template_model_1,
        my_prompt_template_model_2,
    ]
    PYDANTIC_EXAMPLES_USING_SUBCLASS: ClassVar[List[BaseModel]] = [
        prompt_with_image_path,
    ]
    PYDANTIC_EXAMPLES_DICT: ClassVar[List[Dict[str, Any]]] = [
        dict_1,
    ]
