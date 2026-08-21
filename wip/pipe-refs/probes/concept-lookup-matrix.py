# ruff: file-ignore[implicit-namespace-package] - a standalone probe script, deliberately not a package
"""What the concept entry lookup actually does with a bare code.

Originally written against `ConceptLibrary.get_required_concept_from_concept_ref_or_code` and its
`search_domain_codes` list — the reader README §4 documents as broken (the multi-domain walk died
on its first miss and escaped as the wrong exception class). Phase 3 replaced that method with the
entry affordance `get_required_entry_concept(code, search_scope=...)`; this probe now measures the
replacement over the same library shapes, so the §4 table can be re-measured after the change.

Builds a two-domain library in memory and asks for a bare concept code under each shape of
`search_scope`. No bundle files, no runtime boot — the library object is enough, because the
lookup is pure.

    .venv/bin/python wip/pipe-refs/probes/concept-lookup-matrix.py  # needs the venv: this probe imports pipelex

Read the output against the entry-affordance semantics (a hand-supplied code is NOT an in-body
reference): the entry pipe's own scope wins, an unambiguous crate-wide match is served, ambiguity
refuses to guess, and a genuine miss raises the class every caller actually catches.
"""

from pipelex.core.concepts.concept import Concept
from pipelex.libraries.concept.concept_library import ConceptLibrary

STRUCTURE_CLASS_NAME = "TextContent"


def library_declaring(*declarations: tuple[str, str]) -> ConceptLibrary:
    library = ConceptLibrary.make_empty()
    for domain_code, concept_code in declarations:
        library.add_new_concept(
            Concept(
                code=concept_code,
                domain_code=domain_code,
                description="probe concept",
                structure_class_name=STRUCTURE_CLASS_NAME,
            )
        )
    return library


def attempt(*, label: str, library: ConceptLibrary, code: str, search_scope: str | None) -> None:
    try:
        found = library.get_required_entry_concept(code, search_scope=search_scope)
    except BaseException as exc:  # ruff: ignore[blind-except] - naming *which* error escapes IS the measurement here
        print(f"{label:46} -> {type(exc).__name__}: {exc}")
    else:
        print(f"{label:46} -> resolved {found.concept_ref}")


def main() -> None:
    both = library_declaring(("alpha", "Memo"), ("beta", "Memo"))
    only_beta = library_declaring(("beta", "Memo"))

    print("bare code 'Memo'; the entry pipe is in domain 'alpha'\n")
    attempt(label="both declare  | scope=None", library=both, code="Memo", search_scope=None)
    attempt(label="only beta     | scope=None", library=only_beta, code="Memo", search_scope=None)
    attempt(label="both declare  | scope=alpha", library=both, code="Memo", search_scope="alpha")
    attempt(label="only beta     | scope=alpha", library=only_beta, code="Memo", search_scope="alpha")
    attempt(label="only beta     | scope=beta", library=only_beta, code="Memo", search_scope="beta")
    attempt(label="nowhere       | scope=alpha", library=ConceptLibrary.make_empty(), code="Memo", search_scope="alpha")


if __name__ == "__main__":
    main()
