domain = "concept_library_tests"

[concept]
# Simple concept with no structure - should default to Text
SimpleTextConcept = "A simple concept that should default to Text"

# Concept with explicit structure class
FundamentalsDoc = "A comprehensive overview of the fundamental concepts and principles of software engineering."

# Concept that explicitly refines Text
[concept.ExplicitTextConcept]
definition = "A concept that explicitly refines Text"
refines = "Text"

# Concept that refines Image
[concept.ImageBasedConcept]
definition = "A concept based on images"
refines = "Image"

# Concept that refines FundamentalsDoc
[concept.DocumentationConcept]
definition = "A specialized documentation concept"

# Concept that refines both Text and Image (multiple inheritance)
[concept.MultiMediaConcept]
definition = "A concept that combines text and images"

# Concept with custom structure that doesn't refine anything
[concept.IndependentConcept]
definition = "An independent concept with custom structure"
structure = "IndependentConcept"

# Concept that refines a native concept (changed from non-native)
[concept.SpecializedDoc]
definition = "A specialized document that builds on Text"
refines = "Text"

# Concept that refines a native concept (changed from non-native chain)
[concept.DerivedTextConcept]
definition = "A concept derived from Text"
refines = "Text"

