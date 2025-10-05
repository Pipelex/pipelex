domain = "concept_library_tests"

[concept]
# Simple concept with no structure - should default to Text
SimpleTextConcept = "A simple concept that should default to Text"

# Concept with explicit structure class
FundamentalsDoc = "A comprehensive overview of the fundamental concepts and principles of software engineering."

# Concept that explicitly refines Text
[concept.ExplicitTextConcept]
description = "A concept that explicitly refines Text"
refines = "Text"

# Concept that refines Image
[concept.ImageBasedConcept]
description = "A concept based on images"
refines = "Image"

# Concept that refines FundamentalsDoc
[concept.DocumentationConcept]
description = "A specialized documentation concept"

# Concept that refines both Text and Image (multiple inheritance)
[concept.MultiMediaConcept]
description = "A concept that combines text and images"

# Concept with custom structure that doesn't refine anything
[concept.IndependentConcept]
description = "An independent concept with custom structure"
structure = "IndependentConcept"

# Concept that refines a native concept (changed from non-native)
[concept.SpecializedDoc]
description = "A specialized document that builds on Text"
refines = "Text"

# Concept that refines a native concept (changed from non-native chain)
[concept.DerivedTextConcept]
description = "A concept derived from Text"
refines = "Text"

