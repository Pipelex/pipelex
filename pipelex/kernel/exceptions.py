class PromptContentError(ValueError):
    """A prompt's image or document reference could not be resolved out of working memory.

    A `ValueError` rather than a `PipelexError` subclass, matching what the prompt-assembly code
    raised before it moved into the kernel: callers that already handle it as a value error keep
    working, and nothing in the error taxonomy changes.
    """
