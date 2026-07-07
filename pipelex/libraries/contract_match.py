"""Normalized contract conformance for the library merge.

When a forward-declared header (a ``PipeSignature``) and its concrete definition collide in the
library merge, their contracts must agree. The two declarations may spell the same concept
differently — a header's bare ``Brief`` and a definition's domain-qualified ``thisdomain.Brief``
denote the *same* concept, as do native ``Text`` and ``native.Text``. A raw-string comparison
would reject these as a false mismatch.

``contracts_match`` normalizes each concept reference to a canonical identity *string* before
comparing, so equivalent spellings reconcile. This is normalization for *identity* only — it is NOT
refinement substitutability (covariant output / contravariant inputs); that stays the dry-run's job,
which re-validates the parent against the concrete's real contract.
"""

import re

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.variable_multiplicity import MULTIPLICITY_PATTERN
from pipelex.core.qualified_ref import QualifiedRef


def _canonical_concept_spec(spec: str, *, domain_code: str) -> str:
    """Normalize a raw concept spec to a canonical identity string.

    The multiplicity suffix is preserved *verbatim as text* (``""`` / ``"[]"`` / ``"[N]"``), so
    ``Brief[]`` (variable-length list) and ``Brief[1]`` (exactly one item) stay distinct. Comparing
    the *parsed* multiplicity instead would conflate them: ``parse_concept_with_multiplicity`` maps
    ``[]`` to ``True`` and ``[1]`` to ``int 1``, and Python evaluates ``True == 1`` as true. Keeping
    the suffix as text also means a ``[0]`` spec compares as a literal rather than raising.

    The presence marker (``"?"`` / ``"!"``) is likewise preserved verbatim, so ``Brief`` and
    ``Brief?`` denote different contracts (D5: method-boundary signatures are explicit about
    optionality, so a header and its definition must agree on the marker).

    The concept part is canonicalized so equivalent spellings collapse to one identity:

    - native (``Text`` or ``native.Text``) -> the bare native code (``Text``);
    - external-domain qualified -> kept verbatim (belongs to another domain);
    - bare / same-domain -> qualified to ``domain.Code`` so a header's ``Brief`` and a definition's
      ``thisdomain.Brief`` compare equal.

    A spec the multiplicity pattern does not cover (e.g. a cross-package ``alias->...`` ref, which
    cannot appear in a blueprint's ``inputs``/``output`` but is handled defensively) is returned
    verbatim — it is already unambiguous.
    """
    match = re.match(MULTIPLICITY_PATTERN, spec)
    if match is None:
        return spec
    concept_ref_or_code = match.group(1)
    bracket_content = match.group(2)  # None -> no brackets; "" -> "[]"; digits -> "[N]"
    marker_symbol = match.group(3) or ""  # None -> no marker; "?" / "!" kept verbatim
    suffix = ("" if bracket_content is None else f"[{bracket_content}]") + marker_symbol

    if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code):
        return f"{QualifiedRef.parse(concept_ref_or_code).local_code}{suffix}"
    ref = QualifiedRef.parse(concept_ref_or_code)
    if ref.is_external_to(domain_code):
        return f"{concept_ref_or_code}{suffix}"
    return f"{ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=ref.local_code)}{suffix}"


def contracts_match(*, existing: PipeBlueprint, incoming: PipeBlueprint, domain_code: str) -> bool:
    """True if two declarations of the same pipe denote the same contract after normalization.

    Both declarations share ``domain_code`` (they collided on the same qualified ``pipe_ref``), so
    same-domain bare and qualified spellings of a concept canonicalize to one identity. A missing
    ``inputs`` and an empty ``inputs`` are treated alike. Input *names* must match exactly — they are
    variable names, not concepts.
    """
    existing_inputs = {name: _canonical_concept_spec(spec, domain_code=domain_code) for name, spec in (existing.inputs or {}).items()}
    incoming_inputs = {name: _canonical_concept_spec(spec, domain_code=domain_code) for name, spec in (incoming.inputs or {}).items()}
    if existing_inputs != incoming_inputs:
        return False
    return _canonical_concept_spec(existing.output, domain_code=domain_code) == _canonical_concept_spec(incoming.output, domain_code=domain_code)
