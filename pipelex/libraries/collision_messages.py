def duplicate_ref_msg(
    *,
    ref_kind: str,
    ref: str,
    existing_source: str | None,
    incoming_source: str | None,
) -> str:
    """Build the error message for a duplicate concept/pipe declaration in a merged library.

    `ref_kind` is the singular noun ("concept" or "pipe"); the plural is formed by appending
    "s". Whether the two declarations live in the same file or different files is derived from
    the two sources, so callers do not pass a separate flag.

    Args:
        ref_kind: Singular noun for the kind of reference ("concept" or "pipe").
        ref: The fully qualified ref that is declared twice (e.g. "scoring.compute_score").
        existing_source: Source file of the already-seen declaration, or None if unknown.
        incoming_source: Source file of the colliding declaration, or None if unknown.

    Returns:
        A human-readable error message naming the offending ref and source files.
    """
    noun = ref_kind.capitalize()
    if existing_source is not None and existing_source == incoming_source:
        return f"{noun} '{ref}' is declared twice in the same bundle file: '{existing_source}'. Please remove the duplicate declaration."
    return (
        f"{noun} '{ref}' is declared in two different bundle files: "
        f"'{existing_source or 'unknown'}' and '{incoming_source or 'unknown'}'. "
        f"Please remove one of the declarations or rename one of the {ref_kind}s."
    )
