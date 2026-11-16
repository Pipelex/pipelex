"""What every target says about a wire shape, the second type a concept reaching a stored value gets.

The shapes themselves are decided in `pipelex.codegen.resolved_concepts`; this is the note each target puts in the
wire shape's documentation, beside the concept's own description, so a reader of any generated file learns the same
thing about it. It is broken into short lines, because neither formatter rewraps a docstring or a comment and a long
line would trip a consumer's line-length rule.
"""


def wire_shape_note(*, loaded_name: str) -> str:
    """The note documenting the wire shape of the type named `loaded_name`."""
    return (
        f"Wire shape of {loaded_name}: a Text, Html or JSON value the runtime\n"
        "stored arrives as its reference (url, size, mime_type, preview)\n"
        f"instead of its value. A client that loads stored values returns {loaded_name}."
    )
