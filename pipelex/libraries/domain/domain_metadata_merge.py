from pipelex import log


def merge_domain_metadata_field(
    *,
    domain_code: str,
    field_label: str,
    established: str | None,
    incoming: str | None,
    show_values_on_conflict: bool,
) -> str | None:
    """Order-independent, omission-quiet merge of one domain-metadata field across same-domain files.

    Under the additive multi-file model a same-domain library is authored as one root file that carries
    the full domain header (`description`, `system_prompt`, ...) and N membership-only sibling files that
    declare only `domain = "<same_domain>"`. Those siblings omit `description` / `system_prompt`, and an
    omitted value must contribute *no opinion*: it neither overrides an established non-empty value nor
    warns. Whichever file declares the value therefore wins regardless of file load order (which, for a
    `-L` directory, is filesystem sort order, not authoring intent).

    Per field:

    - established empty/None + incoming non-empty -> take incoming, no warning (root may arrive after a sibling).
    - established non-empty + incoming empty/None -> keep established, no warning (sibling defers to root).
    - both non-empty and equal -> keep, no warning.
    - both non-empty and different -> keep the first, **warn** (a genuine double-declaration the author should resolve).

    Args:
        domain_code: The domain these values belong to (used in the warning message).
        field_label: Singular human-readable field name used in the warning, pluralized with "s"
            (e.g. "description" -> "descriptions", "system_prompt" -> "system_prompts").
        established: The value already merged for this domain (may be empty/None).
        incoming: The value from the file being merged now (may be empty/None).
        show_values_on_conflict: Whether to include both values in the conflict warning. True for short
            fields (description); False for long ones (system_prompt) whose contents would flood the log.

    Returns:
        The merged value (the established value wins on a genuine conflict).
    """
    if not incoming:
        return established
    if not established:
        return incoming
    if established != incoming:
        if show_values_on_conflict:
            log.warning(
                f"Domain '{domain_code}' declared with different {field_label}s: '{established}' vs '{incoming}'. Keeping the first.",
            )
        else:
            log.warning(
                f"Domain '{domain_code}' declared with different {field_label}s. Keeping the first.",
            )
    return established
