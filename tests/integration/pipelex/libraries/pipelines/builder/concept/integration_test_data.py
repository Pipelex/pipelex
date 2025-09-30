from typing import ClassVar


class ConceptSpecGenerationTestCases:
    """Test cases for LLM-based ConceptSpec generation."""

    # Test case: Simple concept without structure or refines
    SIMPLE_CONCEPT_PROMPT = """
Generate a concept specification for a "BlogPost" concept.

Requirements:
- the_concept_code: BlogPost
- definition: A blog post with title, content, and publication date
- structure: None (leave empty)
- refines: None (leave empty)
"""

    # Test case: Concept that refines a native concept
    REFINES_TEXT_PROMPT = """
Generate a concept specification for a "ProductDescription" concept.

Requirements:
- the_concept_code: ProductDescription
- definition: A detailed description of a product for e-commerce
- refines: Text (this concept refines the native Text concept)
- structure: None (leave empty because we're using refines)
"""

    # Test case: Concept with simple structure
    SIMPLE_STRUCTURE_PROMPT = """
Generate a concept specification for a "Person" concept with a simple structure.

Requirements:
- the_concept_code: Person
- definition: A person with basic information
- structure: A dictionary with these fields:
  - name: (type: text, definition: "The person's full name", required: true)
  - age: (type: integer, definition: "The person's age", required: true)
- refines: None (leave empty)
"""

    # Test case: Concept with complex structure
    COMPLEX_STRUCTURE_PROMPT = """
Generate a concept specification for a "Product" concept with a detailed structure.

Requirements:
- the_concept_code: Product
- definition: A product in an e-commerce system
- structure: A dictionary with these fields:
  - name: (type: text, definition: "Product name", required: true)
  - description: (type: text, definition: "Product description", required: true)
  - price: (type: number, definition: "Product price in dollars", required: true)
  - stock_quantity: (type: integer, definition: "Number of items in stock", required: false, default_value: 0)
  - is_available: (type: boolean, definition: "Whether the product is currently available", required: false, default_value: true)
- refines: None (leave empty)
"""

    # Test case: Concept with optional fields and defaults
    OPTIONAL_FIELDS_PROMPT = """
Generate a concept specification for a "UserProfile" concept.

Requirements:
- the_concept_code: UserProfile
- definition: A user profile with optional settings
- structure: A dictionary with these fields:
  - username: (type: text, definition: "User's username", required: true)
  - email: (type: text, definition: "User's email address", required: true)
  - bio: (type: text, definition: "User biography", required: false, default_value: "")
  - notification_enabled: (type: boolean, definition: "Whether notifications are enabled", required: false, default_value: true)
  - login_count: (type: integer, definition: "Number of times user has logged in", required: false, default_value: 0)
- refines: None (leave empty)
"""

    # Test case: Concept with snake_case code (tests conversion)
    SNAKE_CASE_CONCEPT_PROMPT = """
Generate a concept specification for a "customer_order" concept.

Requirements:
- the_concept_code: customer_order
- definition: An order placed by a customer
- structure: A dictionary with these fields:
  - order_number: (type: text, definition: "Unique order identifier", required: true)
  - total_amount: (type: number, definition: "Total order amount", required: true)
  - is_paid: (type: boolean, definition: "Payment status", required: false, default_value: false)
- refines: None (leave empty)
"""

    # Test case: Concept refining Image
    REFINES_IMAGE_PROMPT = """
Generate a concept specification for a "ProductPhoto" concept.

Requirements:
- the_concept_code: ProductPhoto
- definition: A photograph of a product for display in catalog
- refines: Image (this concept refines the native Image concept)
- structure: None (leave empty because we're using refines)
"""

    # Test case: Concept with date field
    DATE_FIELD_PROMPT = """
Generate a concept specification for an "Event" concept with a date field.

Requirements:
- the_concept_code: Event
- definition: An event with scheduling information
- structure: A dictionary with these fields:
  - title: (type: text, definition: "Event title", required: true)
  - description: (type: text, definition: "Event description", required: true)
  - start_date: (type: date, definition: "Event start date and time", required: true)
  - is_public: (type: boolean, definition: "Whether the event is public", required: false, default_value: true)
- refines: None (leave empty)
"""

    TEST_CASES: ClassVar[list[tuple[str, str]]] = [
        # ("simple_concept", SIMPLE_CONCEPT_PROMPT),
        # ("refines_text", REFINES_TEXT_PROMPT),
        # ("simple_structure", SIMPLE_STRUCTURE_PROMPT),
        # ("complex_structure", COMPLEX_STRUCTURE_PROMPT),
        # ("optional_fields", OPTIONAL_FIELDS_PROMPT),
        ("snake_case_concept", SNAKE_CASE_CONCEPT_PROMPT),
        # ("refines_image", REFINES_IMAGE_PROMPT),
        # ("date_field", DATE_FIELD_PROMPT),
    ]
