# ruff: noqa: INP001 - a standalone probe script, deliberately not a package
"""What `ConceptLibrary.get_required_concept_from_concept_ref_or_code` actually does with a bare code.

Builds a two-domain library in memory and asks for a bare concept code under each shape of
`search_domain_codes`. No bundle files, no runtime boot — the library object is enough, because the
lookup is pure.

    .venv/bin/python wip/pipe-refs/probes/concept-lookup-matrix.py  # needs the venv: this probe imports pipelex

Read the output against `mthds/docs/spec/namespace-resolution.md`
§ "Resolution Order for Bare Concept References": current bundle, then same domain in other
bundles, then error — and explicitly no fall-through to another domain.
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


def attempt(*, label: str, library: ConceptLibrary, code: str, search_domain_codes: list[str] | None) -> None:
    try:
        found = library.get_required_concept_from_concept_ref_or_code(code, search_domain_codes=search_domain_codes)
    except BaseException as exc:  # noqa: BLE001 - naming *which* error escapes IS the measurement here
        print(f"{label:46} -> {type(exc).__name__}: {exc}")
    else:
        print(f"{label:46} -> resolved {found.concept_ref}")


def main() -> None:
    both = library_declaring(("alpha", "Memo"), ("beta", "Memo"))
    only_beta = library_declaring(("beta", "Memo"))

    print("bare code 'Memo'; the caller is in domain 'alpha'\n")
    attempt(label="both declare  | search=None", library=both, code="Memo", search_domain_codes=None)
    attempt(label="only beta     | search=None", library=only_beta, code="Memo", search_domain_codes=None)
    attempt(label="both declare  | search=[alpha, beta]", library=both, code="Memo", search_domain_codes=["alpha", "beta"])
    attempt(label="only beta     | search=[alpha, beta]", library=only_beta, code="Memo", search_domain_codes=["alpha", "beta"])
    attempt(label="only beta     | search=[beta, alpha]", library=only_beta, code="Memo", search_domain_codes=["beta", "alpha"])
    attempt(label="both declare  | search=[alpha]", library=both, code="Memo", search_domain_codes=["alpha"])


if __name__ == "__main__":
    main()
