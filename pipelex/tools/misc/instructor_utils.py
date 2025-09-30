from typing import Any

from pipelex import pretty_print


def dump_kwargs(*_: Any, **kwargs: Any) -> None:
    pretty_print(kwargs, title="Instructor about to send to LLM provider")


def dump_response(response: Any) -> None:
    pretty_print(response, title="Instructor response from LLM provider")


def dump_error(error: Exception) -> None:
    pretty_print(error, title="Instructor error from LLM provider")
