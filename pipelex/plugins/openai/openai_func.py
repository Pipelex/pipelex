import inspect
from typing import Any, Callable, Dict, List, Tuple, Type

from instructor import OpenAISchema, openai_schema
from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel, create_model


def create_pydantic_model_from_function(func: Callable[..., Any]) -> Type[BaseModel]:
    """
    Creates a Pydantic BaseModel from a function's signature.

    Parameters:
        func (Callable): The function from which to derive the BaseModel.

    Returns:
        Type[BaseModel]: A dynamically created Pydantic BaseModel class.
    """
    sig = inspect.signature(func)
    fields: Dict[str, Tuple[Type[Any], Any]] = {
        name: (param.annotation, param.default if param.default is not inspect.Parameter.empty else ...) for name, param in sig.parameters.items()
    }
    model_name = func.__name__
    return create_model(__model_name=model_name, **fields)  # type: ignore


def create_openai_schema_from_function(func: Callable[..., Any]) -> Dict[str, Any]:
    """
    Creates an OpenAI schema from a function.

    Parameters:
        func (Callable): The function from which to derive the OpenAI schema.

    Returns:
        Dict[str, Any]: The OpenAI schema as a dictionary.
    """
    model: Type[BaseModel] = create_pydantic_model_from_function(func)
    the_openai_schema: OpenAISchema = openai_schema(model)
    as_openai_schema: Dict[str, Any] = the_openai_schema.openai_schema

    # replace description using first non-empty line of func.__doc__ description
    if func.__doc__:
        description = func.__doc__.strip().split("\n")[0]
    else:
        description = func.__name__
    as_openai_schema["description"] = description
    return as_openai_schema


def list_openai_tools(openai_message: ChatCompletionMessage) -> List[str]:
    if not openai_message.tool_calls:
        return []
    tools: List[str] = []
    for tool_call in openai_message.tool_calls:
        if tool_call.type == "function":
            tools.append(tool_call.function.name)
        else:
            tools.append(tool_call.type)
    return tools
