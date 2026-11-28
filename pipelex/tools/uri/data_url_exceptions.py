class DataUrlError(ValueError):
    """Raised when a value read as a `data:` URL is not one this runtime reads.

    A value that is not a `data:` URL at all, a `data:` URL with no comma ending its header, and, where a reader needs
    bytes, a `data:` URL that is not base64. The message never quotes the header or the payload, which are a caller's
    content. A low-level parse error: the input boundary turns it into the caller's error, naming the input.
    """
