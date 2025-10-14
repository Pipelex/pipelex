def find_span(text: str, begin: str, end: str) -> tuple[int, int] | None:
    """Find the span of text between begin and end markers.

    Args:
        text: Text to search in
        begin: Beginning marker string
        end: Ending marker string

    Returns:
        Tuple of (start, end) indices if both markers found, None otherwise
        The end index includes the end marker itself
    """
    start = text.find(begin)
    if start == -1:
        return None

    end_pos = text.find(end, start)
    if end_pos == -1:
        return None

    end_pos += len(end)
    return (start, end_pos)


def wrap(begin: str, end: str, content: str) -> str:
    """Wrap content with begin and end markers.

    Args:
        begin: Beginning marker
        end: Ending marker
        content: Content to wrap

    Returns:
        Wrapped content with markers and newlines
    """
    return f"{begin}\n{content.rstrip()}\n{end}"


def replace_span(text: str, span: tuple[int, int], replacement: str) -> str:
    """Replace the text at the given span with replacement.

    Args:
        text: Original text
        span: Tuple of (start, end) indices
        replacement: Replacement text

    Returns:
        Text with span replaced by replacement
    """
    start, end = span
    return text[:start] + replacement + text[end:]
