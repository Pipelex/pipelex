"""Format pipe chains as human-readable MTHDS composition templates.

Provides a formatter that takes a resolved pipe chain and produces
a multi-line snippet showing how to wire the pipes together.
"""

from pipelex.core.packages.graph.models import ConceptId, PipeNode


def format_chain_as_mthds_snippet(
    chain_pipes: list[PipeNode],
    from_concept: ConceptId,
    to_concept: ConceptId,
) -> str:
    """Format a chain of PipeNodes as a human-readable MTHDS composition template.

    Args:
        chain_pipes: Resolved PipeNode list representing the chain steps.
        from_concept: The source ConceptId (what the user has).
        to_concept: The target ConceptId (what the user needs).

    Returns:
        Multi-line string with the composition template.
        Empty string if chain_pipes is empty.
    """
    if not chain_pipes:
        return ""

    lines: list[str] = []

    # Header: Composition: from -> intermediate(s) -> to
    header_refs: list[str] = [_format_concept_ref(from_concept)]
    for pipe_node in chain_pipes[:-1]:
        header_refs.append(_format_concept_ref(pipe_node.output_concept_id))
    header_refs.append(_format_concept_ref(to_concept))
    lines.append(f"Composition: {' -> '.join(header_refs)}")

    # Steps
    for step_number, pipe_node in enumerate(chain_pipes, start=1):
        lines.append("")
        lines.append(_format_step(step_number, pipe_node))

    # Cross-package note
    if _is_cross_package_chain(chain_pipes):
        lines.append("")
        lines.append(
            "Note: This chain spans multiple packages. Use alias->domain.pipe_code\nsyntax for cross-package references in your .mthds file."
        )

    return "\n".join(lines)


def _format_concept_ref(concept_id: ConceptId) -> str:
    """Return the concept_ref as-is for display.

    Args:
        concept_id: The concept to format.

    Returns:
        The concept_ref string (e.g. 'native.Text', 'pkg_test_legal.PkgTestContractClause').
    """
    return concept_id.concept_ref


def _format_step(step_number: int, pipe_node: PipeNode) -> str:
    """Format one numbered step block.

    Args:
        step_number: The 1-based step number.
        pipe_node: The PipeNode for this step.

    Returns:
        Multi-line string for the step block.
    """
    inputs_str = ", ".join(f"{param_name}: {_format_concept_ref(concept_id)}" for param_name, concept_id in pipe_node.input_concept_ids.items())

    step_lines = [
        f"  Step {step_number}: {pipe_node.pipe_code}",
        f"    Package:  {pipe_node.package_address}",
        f"    Domain:   {pipe_node.domain_code}",
        f"    Input:    {inputs_str}",
        f"    Output:   {_format_concept_ref(pipe_node.output_concept_id)}",
    ]
    return "\n".join(step_lines)


def _is_cross_package_chain(chain_pipes: list[PipeNode]) -> bool:
    """Check if a chain spans multiple packages.

    Args:
        chain_pipes: The list of PipeNodes in the chain.

    Returns:
        True if pipes come from more than one package_address.
    """
    addresses = {pipe_node.package_address for pipe_node in chain_pipes}
    return len(addresses) > 1
