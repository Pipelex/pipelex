from typing import Optional


class ConceptCodeError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Concept code '{self.code}' must be PascalCase (letters and numbers only, starting with uppercase, without `.`)")


class ConceptStringError(Exception):
    def __init__(self, concept_string: str, message: Optional[str] = None):
        super().__init__(
            f"Concept string '{concept_string}' is invalid. It should contain a domain in snake_case "
            "and a concept code in PascalCase separated by one dot."
            if not message
            else message
        )


class ConceptStringOrConceptCodeError(Exception):
    def __init__(self, concept_string_or_concept_code: str):
        super().__init__(
            f"concept_string_or_concept_code '{concept_string_or_concept_code}' is invalid. "
            "It should either contain a domain in snake_case and a concept code in PascalCase separated by one dot, "
            "or be a concept code in PascalCase."
        )
