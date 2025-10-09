from typing import Any

from pipelex import pretty_print
from pipelex.cogt.llm.llm_prompt import LLMPrompt


def dump_prompt(llm_prompt: LLMPrompt) -> None:
    prompt_dump = ""
    if user_text := llm_prompt.user_text:
        prompt_dump += f"\n# User text:\n{user_text}\n"
    if system_text := llm_prompt.system_text:
        prompt_dump = f"\n# System text:\n{system_text}\n" + prompt_dump
    if llm_prompt.user_images:
        images_desc = "\n".join([f"-  {image}" for image in llm_prompt.user_images])
        prompt_dump += f"\n# User images:\n{images_desc}\n"
    pretty_print(prompt_dump, title="Prompt sent to LLM provider")


def dump_response_from_text_gen(response: Any) -> None:
    pretty_print(response, title="Response from LLM provider")


def dump_kwargs(*_: Any, **kwargs: Any) -> None:
    pretty_print(kwargs, title="Instructor about to send to LLM provider")


def dump_response_from_structured_gen(response: Any) -> None:
    pretty_print(response, title="Instructor response from LLM provider")


def dump_error(error: Exception) -> None:
    pretty_print(error, title="Instructor error from LLM provider")
