"""Build a KnowHowGraph from a PackageIndex.

Resolves concept identities, builds pipe nodes with resolved input/output concepts,
and creates data-flow and refinement edges.
"""

from pipelex import log
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.packages.graph.models import (
    NATIVE_PACKAGE_ADDRESS,
    ConceptId,
    ConceptNode,
    EdgeKind,
    GraphEdge,
    KnowHowGraph,
    PipeNode,
)
from pipelex.core.packages.index.models import PackageIndex
from pipelex.core.qualified_ref import QualifiedRef


def build_know_how_graph(index: PackageIndex) -> KnowHowGraph:
    """Build a KnowHowGraph from a PackageIndex.

    Args:
        index: The package index to build the graph from

    Returns:
        A fully populated KnowHowGraph with concept nodes, pipe nodes,
        refinement edges, and data-flow edges

    Note:
        Unresolvable concepts and refines targets are logged as warnings
        and excluded from the graph rather than raising errors.
    """
    graph = KnowHowGraph()

    # Step 1: Build concept nodes + lookup table
    package_concept_lookup: dict[str, dict[str, ConceptId]] = {}
    _build_concept_nodes(index, graph, package_concept_lookup)
    _build_native_concept_nodes(graph)

    # Step 2: Resolve refines targets
    _resolve_refines_targets(index, graph, package_concept_lookup)

    # Step 3: Build pipe nodes
    _build_pipe_nodes(index, graph, package_concept_lookup)

    # Step 4: Build refinement edges
    _build_refinement_edges(graph)

    # Step 5: Build data flow edges
    _build_data_flow_edges(graph)

    return graph


def _build_concept_nodes(
    index: PackageIndex,
    graph: KnowHowGraph,
    package_concept_lookup: dict[str, dict[str, ConceptId]],
) -> None:
    """Create ConceptNodes for all concepts in all packages and populate the lookup table."""
    for address, concept_entry in index.all_concepts():
        concept_id = ConceptId(
            package_address=address,
            concept_ref=concept_entry.concept_ref,
        )
        node = ConceptNode(
            concept_id=concept_id,
            description=concept_entry.description,
            structure_fields=list(concept_entry.structure_fields),
        )
        graph.concept_nodes[concept_id.node_key] = node

        if address not in package_concept_lookup:
            package_concept_lookup[address] = {}
        package_concept_lookup[address][concept_entry.concept_code] = concept_id


def _build_native_concept_nodes(graph: KnowHowGraph) -> None:
    """Create ConceptNodes for all native concepts."""
    for native_code in NativeConceptCode:
        concept_ref = f"native.{native_code}"
        concept_id = ConceptId(
            package_address=NATIVE_PACKAGE_ADDRESS,
            concept_ref=concept_ref,
        )
        if concept_id.node_key not in graph.concept_nodes:
            node = ConceptNode(
                concept_id=concept_id,
                description=f"Native concept: {native_code}",
            )
            graph.concept_nodes[concept_id.node_key] = node


def _resolve_refines_targets(
    index: PackageIndex,
    graph: KnowHowGraph,
    package_concept_lookup: dict[str, dict[str, ConceptId]],
) -> None:
    """Resolve refines strings to ConceptIds and update ConceptNodes."""
    for address, concept_entry in index.all_concepts():
        if concept_entry.refines is None:
            continue

        concept_id = ConceptId(
            package_address=address,
            concept_ref=concept_entry.concept_ref,
        )
        existing_node = graph.concept_nodes.get(concept_id.node_key)
        if existing_node is None:
            continue

        refines_target = _resolve_refines_string(
            refines=concept_entry.refines,
            package_address=address,
            index=index,
            package_concept_lookup=package_concept_lookup,
        )
        if refines_target is None:
            log.warning(f"Could not resolve refines target '{concept_entry.refines}' for concept {concept_id.node_key}")
            continue

        # Replace the node with one that has the resolved refines link
        updated_node = ConceptNode(
            concept_id=existing_node.concept_id,
            description=existing_node.description,
            refines=refines_target,
            structure_fields=list(existing_node.structure_fields),
        )
        graph.concept_nodes[concept_id.node_key] = updated_node


def _resolve_refines_string(
    refines: str,
    package_address: str,
    index: PackageIndex,
    package_concept_lookup: dict[str, dict[str, ConceptId]],
) -> ConceptId | None:
    """Resolve a refines string to a ConceptId.

    Handles cross-package refs (alias->domain.Code) and local refs.
    """
    if QualifiedRef.has_cross_package_prefix(refines):
        alias, remainder = QualifiedRef.split_cross_package_ref(refines)
        entry = index.get_entry(package_address)
        if entry is None:
            return None
        resolved_address = entry.dependency_aliases.get(alias)
        if resolved_address is None:
            log.warning(f"Unknown dependency alias '{alias}' in refines '{refines}' for package {package_address}")
            return None
        return ConceptId(
            package_address=resolved_address,
            concept_ref=remainder,
        )

    # Local reference: look up in same package
    local_lookup = package_concept_lookup.get(package_address, {})
    # Try as a bare concept code first
    if refines in local_lookup:
        return local_lookup[refines]
    # Try as a full concept_ref
    for concept_id in local_lookup.values():
        if concept_id.concept_ref == refines:
            return concept_id
    return None


def _resolve_concept_code(
    concept_spec: str,
    package_address: str,
    domain_code: str,
    package_concept_lookup: dict[str, dict[str, ConceptId]],
    index: PackageIndex,
) -> ConceptId | None:
    """Resolve a concept spec string (from pipe input/output) to a ConceptId.

    Handles native concepts, bare concept codes, domain-qualified refs
    (e.g. ``domain.ConceptCode``), and cross-package refs
    (e.g. ``alias->domain.ConceptCode``).

    Args:
        concept_spec: The concept spec string (e.g. "Text", "PkgTestContractClause",
            "domain.ConceptCode", "alias->domain.ConceptCode")
        package_address: The package address containing the pipe
        domain_code: The domain code of the pipe
        package_concept_lookup: The package->code->ConceptId lookup table
        index: The package index (needed for cross-package alias resolution)

    Returns:
        A resolved ConceptId, or None if the concept could not be resolved
    """
    # Check if it's a native concept
    if NativeConceptCode.is_native_concept_ref_or_code(concept_spec):
        native_ref = NativeConceptCode.get_validated_native_concept_ref(concept_spec)
        return ConceptId(
            package_address=NATIVE_PACKAGE_ADDRESS,
            concept_ref=native_ref,
        )

    # Cross-package ref: alias->domain.ConceptCode
    if QualifiedRef.has_cross_package_prefix(concept_spec):
        return _resolve_cross_package_concept(concept_spec, package_address, index, package_concept_lookup)

    # Look up in same package by bare concept code
    local_lookup = package_concept_lookup.get(package_address, {})
    if concept_spec in local_lookup:
        return local_lookup[concept_spec]

    # Domain-qualified ref: domain.ConceptCode
    if "." in concept_spec:
        for concept_id in local_lookup.values():
            if concept_id.concept_ref == concept_spec:
                return concept_id

    # Unresolved: log warning and return None to exclude from the graph
    log.warning(f"Could not resolve concept '{concept_spec}' in package {package_address}, domain {domain_code}")
    return None


def _resolve_cross_package_concept(
    concept_spec: str,
    package_address: str,
    index: PackageIndex,
    package_concept_lookup: dict[str, dict[str, ConceptId]],
) -> ConceptId | None:
    """Resolve a cross-package concept spec (alias->domain.ConceptCode) to a ConceptId.

    Args:
        concept_spec: The cross-package concept spec (e.g. "scoring_dep->pkg_test_scoring.Score")
        package_address: The address of the package containing the reference
        index: The package index for alias resolution
        package_concept_lookup: The package->code->ConceptId lookup table

    Returns:
        A resolved ConceptId, or None if the alias or concept could not be resolved
    """
    alias, remainder = QualifiedRef.split_cross_package_ref(concept_spec)
    entry = index.get_entry(package_address)
    if entry is None:
        log.warning(f"Package '{package_address}' not found in index for cross-package ref '{concept_spec}'")
        return None

    resolved_address = entry.dependency_aliases.get(alias)
    if resolved_address is None:
        log.warning(f"Unknown dependency alias '{alias}' in concept spec '{concept_spec}' for package {package_address}")
        return None

    target_lookup = package_concept_lookup.get(resolved_address, {})

    # Try by bare concept code (last segment of remainder)
    ref = QualifiedRef.parse(remainder)
    if ref.local_code in target_lookup:
        return target_lookup[ref.local_code]

    # Try by full concept_ref
    for concept_id in target_lookup.values():
        if concept_id.concept_ref == remainder:
            return concept_id

    log.warning(f"Could not resolve cross-package concept '{concept_spec}' in target package {resolved_address}")
    return None


def _build_pipe_nodes(
    index: PackageIndex,
    graph: KnowHowGraph,
    package_concept_lookup: dict[str, dict[str, ConceptId]],
) -> None:
    """Create PipeNodes with resolved concept identities.

    Pipes with unresolvable output or input concepts are excluded from the
    graph rather than creating dangling references.
    """
    for address, pipe_sig in index.all_pipes():
        output_concept_id = _resolve_concept_code(
            concept_spec=pipe_sig.output_spec,
            package_address=address,
            domain_code=pipe_sig.domain_code,
            package_concept_lookup=package_concept_lookup,
            index=index,
        )
        if output_concept_id is None:
            log.warning(f"Excluding pipe '{pipe_sig.pipe_code}' from graph: unresolvable output concept '{pipe_sig.output_spec}'")
            continue

        input_concept_ids: dict[str, ConceptId] = {}
        has_unresolvable_input = False
        for param_name, input_spec in pipe_sig.input_specs.items():
            resolved_input = _resolve_concept_code(
                concept_spec=input_spec,
                package_address=address,
                domain_code=pipe_sig.domain_code,
                package_concept_lookup=package_concept_lookup,
                index=index,
            )
            if resolved_input is None:
                log.warning(f"Excluding pipe '{pipe_sig.pipe_code}' from graph: unresolvable input concept '{input_spec}' for param '{param_name}'")
                has_unresolvable_input = True
                break
            input_concept_ids[param_name] = resolved_input

        if has_unresolvable_input:
            continue

        pipe_node = PipeNode(
            package_address=address,
            pipe_code=pipe_sig.pipe_code,
            pipe_type=pipe_sig.pipe_type,
            domain_code=pipe_sig.domain_code,
            description=pipe_sig.description,
            is_exported=pipe_sig.is_exported,
            input_concept_ids=input_concept_ids,
            output_concept_id=output_concept_id,
        )
        graph.pipe_nodes[pipe_node.node_key] = pipe_node


def _build_refinement_edges(graph: KnowHowGraph) -> None:
    """Create REFINEMENT edges for each concept that refines another."""
    for concept_node in graph.concept_nodes.values():
        if concept_node.refines is not None:
            edge = GraphEdge(
                kind=EdgeKind.REFINEMENT,
                source_concept_id=concept_node.concept_id,
                target_concept_id=concept_node.refines,
            )
            graph.refinement_edges.append(edge)


def _build_data_flow_edges(graph: KnowHowGraph) -> None:
    """Build data flow edges connecting pipes whose outputs feed other pipes' inputs.

    A pipe's output is compatible with another pipe's input if:
    - The output concept is exactly the input concept, OR
    - The output concept is a refinement (descendant) of the input concept
    """
    # Build a reverse index: concept_node_key -> list of pipe_keys that produce it
    producers_by_concept: dict[str, list[str]] = {}

    for pipe_key, pipe_node in graph.pipe_nodes.items():
        # Walk up the refinement chain from output concept, collecting all ancestor keys
        ancestor_keys = _collect_refinement_ancestors(pipe_node.output_concept_id, graph)
        for ancestor_key in ancestor_keys:
            if ancestor_key not in producers_by_concept:
                producers_by_concept[ancestor_key] = []
            producers_by_concept[ancestor_key].append(pipe_key)

    # For each pipe's each input, look up compatible producers
    for target_key, target_pipe in graph.pipe_nodes.items():
        for param_name, input_concept_id in target_pipe.input_concept_ids.items():
            producer_keys = producers_by_concept.get(input_concept_id.node_key, [])
            for source_key in producer_keys:
                if source_key == target_key:
                    continue  # Skip self-loops
                edge = GraphEdge(
                    kind=EdgeKind.DATA_FLOW,
                    source_pipe_key=source_key,
                    target_pipe_key=target_key,
                    input_param=param_name,
                )
                graph.data_flow_edges.append(edge)


def _collect_refinement_ancestors(concept_id: ConceptId, graph: KnowHowGraph) -> list[str]:
    """Walk up the refinement chain from a concept, collecting all ancestor node_keys.

    Returns the concept itself plus all its ancestors via refines links.
    Used for data flow: if A refines B, then a producer of A can also
    satisfy inputs expecting B.
    """
    result: list[str] = []
    visited: set[str] = set()
    current: ConceptId | None = concept_id

    while current is not None:
        node_key = current.node_key
        if node_key in visited:
            break  # Cycle detection
        visited.add(node_key)
        result.append(node_key)

        concept_node = graph.concept_nodes.get(node_key)
        if concept_node is None:
            break
        current = concept_node.refines

    return result
