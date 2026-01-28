from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.core.pipes.pipe_abstract import PipeAbstract


def render_inputs(the_pipe: PipeAbstract, indent: int = 2) -> str:
    """Render a JSON representation of the pipe's inputs.

    Args:
        the_pipe: The pipe to render inputs for
        indent: Number of spaces for indentation (default: 2)

    Returns:
        Formatted JSON string with the inputs representation

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    if not the_pipe.inputs.root:
        msg = f"No inputs required for pipe '{the_pipe.code}'."
        raise NoInputsRequiredError(msg)

    return the_pipe.inputs.render_inputs(indent=indent)
