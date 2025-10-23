from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity

# Test cases format: (nb_output, multiple_output, expected_result, test_description)
MAKE_VARIABLE_MULTIPLICITY_TEST_CASES: list[tuple[int | None, bool | None, VariableMultiplicity | None, str]] = [
    # nb_output, multiple_output, expected_result, description
    # Test cases where nb_output takes precedence
    (3, None, 3, "nb_output=3, multiple_output=None -> returns 3"),
    (5, False, 5, "nb_output=5, multiple_output=False -> returns 5 (nb_output takes precedence)"),
    (1, True, 1, "nb_output=1, multiple_output=True -> returns 1 (nb_output takes precedence)"),
    (10, None, 10, "nb_output=10, multiple_output=None -> returns 10"),
    # Test cases where multiple_output=True is used
    (None, True, True, "nb_output=None, multiple_output=True -> returns True"),
    (0, True, True, "nb_output=0 (falsy), multiple_output=True -> returns True"),
    # Test cases where default (None) is returned
    (None, None, None, "nb_output=None, multiple_output=None -> returns None (default)"),
    (None, False, None, "nb_output=None, multiple_output=False -> returns None"),
    (0, None, None, "nb_output=0 (falsy), multiple_output=None -> returns None"),
    (0, False, None, "nb_output=0 (falsy), multiple_output=False -> returns None"),
    # Edge cases with negative numbers (should still be truthy)
    (-1, None, -1, "nb_output=-1 (truthy), multiple_output=None -> returns -1"),
    (-5, True, -5, "nb_output=-5 (truthy), multiple_output=True -> returns -5 (nb_output takes precedence)"),
    # Edge cases with large numbers
    (1000, None, 1000, "nb_output=1000, multiple_output=None -> returns 1000"),
    (999999, False, 999999, "nb_output=999999, multiple_output=False -> returns 999999"),
]

# Test cases for InputRequirementsFactory.make_from_string
# Format: (domain, requirement_str, expected_concept_string, expected_multiplicity)
SINGLE_ITEM_NO_BRACKETS_TEST_CASES: list[tuple[str, str, str, int | bool | None]] = [
    # Native domain tests with full concept strings
    ("native", "native.Text", "native.Text", None),
    ("native", "native.Image", "native.Image", None),
    ("native", "native.PDF", "native.PDF", None),
    # Implicit concept creation (unknown concept codes become implicit)
    ("my_domain", "MyConcept", "implicit.MyConcept", None),
    ("accounting", "Invoice", "implicit.Invoice", None),
]

# Format: (domain, requirement_str, expected_concept_string)
MULTIPLE_ITEMS_EMPTY_BRACKETS_TEST_CASES: list[tuple[str, str, str]] = [
    # Native domain tests
    ("native", "native.Text[]", "native.Text"),
    ("native", "native.Image[]", "native.Image"),
    # Implicit concept creation with empty brackets
    ("my_domain", "MyConcept[]", "implicit.MyConcept"),
    ("accounting", "Invoice[]", "implicit.Invoice"),
]

# Format: (domain, requirement_str, expected_concept_string, expected_multiplicity)
FIXED_COUNT_TEST_CASES: list[tuple[str, str, str, int]] = [
    # Native domain tests
    ("native", "native.Text[5]", "native.Text", 5),
    ("native", "native.Image[3]", "native.Image", 3),
    ("native", "native.PDF[10]", "native.PDF", 10),
    # Implicit concept creation with fixed counts
    ("my_domain", "MyConcept[7]", "implicit.MyConcept", 7),
    ("accounting", "Invoice[2]", "implicit.Invoice", 2),
    ("hr", "Employee[10]", "implicit.Employee", 10),
]

# Format: (domain, requirement_str, concept_codes_from_same_domain, expected_concept_string, expected_multiplicity, description)
CONCEPT_CODE_RESOLUTION_TEST_CASES: list[tuple[str, str, list[str] | None, str, int | bool | None, str]] = [
    # Native concepts resolved from concept code only (no multiplicity)
    ("native", "Text", None, "native.Text", None, "Native Text without brackets"),
    ("native", "Image[3]", None, "native.Image", 3, "Native Image with fixed count"),
    ("native", "PDF[]", None, "native.PDF", True, "Native PDF with empty brackets"),
    # Native concepts with concept_codes_from_same_domain (native always takes precedence)
    ("native", "Text[5]", ["Text", "Image", "PDF"], "native.Text", 5, "Native Text with concept codes list"),
    # Native concepts take precedence even when used with custom domain parameter
    ("my_domain", "Text", ["Text", "Document"], "native.Text", None, "Native Text takes precedence over custom domain"),
    ("my_domain", "Image[2]", ["Image", "Photo"], "native.Image", 2, "Native Image takes precedence"),
    ("accounting", "Text[3]", ["Invoice", "Receipt"], "native.Text", 3, "Native always wins"),
    # Unknown concepts (not native, not in concept_codes_from_same_domain) create implicit concepts
    ("my_domain", "UnknownConcept[5]", ["KnownConcept"], "implicit.UnknownConcept", 5, "Unknown concept with known list"),
    ("my_domain", "UnknownConcept", None, "implicit.UnknownConcept", None, "Unknown concept without list"),
    ("accounting", "UnknownInvoice[]", ["Invoice"], "implicit.UnknownInvoice", True, "Unknown with empty brackets"),
]

# Format: (domain, requirement_str, expected_concept_string, expected_multiplicity)
EXPLICIT_DOMAIN_IN_STRING_TEST_CASES: list[tuple[str, str, str, int | bool | None]] = [
    # Explicitly specifying native domain in string
    ("my_domain", "native.Text", "native.Text", None),
    ("accounting", "native.Image[3]", "native.Image", 3),
    ("test_domain", "native.PDF[]", "native.PDF", True),
    # Explicitly using implicit domain creates implicit concepts
    ("my_domain", "implicit.OtherConcept[2]", "implicit.OtherConcept", 2),
    ("test_domain", "implicit.LineItem", "implicit.LineItem", None),
]

# Format: (domain, requirement_str, expected_concept_string, expected_multiplicity)
VARIOUS_FIXED_COUNTS_TEST_CASES: list[tuple[str, str, str, int]] = [
    # Native domain with various counts
    ("native", "native.Image[1]", "native.Image", 1),
    ("native", "native.Image[2]", "native.Image", 2),
    ("native", "native.Image[10]", "native.Image", 10),
    ("native", "native.Image[100]", "native.Image", 100),
    ("native", "native.Image[999]", "native.Image", 999),
    # Implicit concepts with various counts (unknown concept codes)
    ("my_domain", "CustomConcept[1]", "implicit.CustomConcept", 1),
    ("accounting", "Transaction[50]", "implicit.Transaction", 50),
]

# Format: (domain, requirement_str, expected_concept_string)
DIFFERENT_CONCEPT_CODES_TEST_CASES: list[tuple[str, str, str]] = [
    # Native concepts
    ("native", "native.Text", "native.Text"),
    ("native", "native.Image", "native.Image"),
    ("native", "native.PDF", "native.PDF"),
    ("native", "native.Number", "native.Number"),
    ("native", "native.Page", "native.Page"),
    # Implicit concepts (unknown concept codes)
    ("my_domain", "CustomConcept", "implicit.CustomConcept"),
    ("accounting", "Invoice", "implicit.Invoice"),
]
