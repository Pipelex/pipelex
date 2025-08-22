class ConceptDomainError(Exception):
    def __init__(self, domain: str):
        self.domain = domain
        super().__init__(f"Domain must be snake_case (lowercase letters, numbers, and underscores only) for concept with domain '{self.domain}'")


class ConceptCodeError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(
            f"Code must be PascalCase (letters and numbers only, starting with uppercase, without `.`) for concept with code '{self.code}'"
        )


class ConceptStringError(Exception):
    def __init__(self, concept_string: str):
        self.concept_string = concept_string
        super().__init__(f"Concept string '{self.concept_string}' is not valid, it should have at most one dot.")
