import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.interpreter import PipelexInterpreter


class TestPipelexInterpreterConceptPLX:
    @pytest.mark.parametrize(
        "concepts,expected_plx",
        [
            # Simple string concepts
            (
                {"ProcessedData": "Data that has been processed", "UserInfo": "Information about a user"},
                """[concept]
ProcessedData = "Data that has been processed"
UserInfo = "Information about a user\"""",
            ),
            # Single concept
            (
                {"Document": "A text document"},
                """[concept]
Document = "A text document\"""",
            ),
            # ConceptBlueprint objects
            (
                {
                    "ProcessedData": ConceptBlueprint(definition="Data that has been processed"),
                    "UserInfo": ConceptBlueprint(definition="Information about a user"),
                },
                """[concept]
ProcessedData = "Data that has been processed"
UserInfo = "Information about a user\"""",
            ),
            # Complex ConceptBlueprint with structure
            (
                {
                    "FeatureAnalysis": ConceptBlueprint(
                        definition="Analysis of a photo's visual content and key features",
                        structure={
                            "dominant_feature": ConceptStructureBlueprint(
                                definition="The most important or dominant feature in the image",
                                type=ConceptStructureBlueprintFieldType.TEXT,
                                required=True,
                            ),
                            "visual_elements": ConceptStructureBlueprint(
                                definition="Description of key visual elements present",
                                type=ConceptStructureBlueprintFieldType.TEXT,
                                required=True,
                            ),
                            "composition": "Analysis of the image composition",
                            "color_palette": "Description of the main colors in the image",
                            "mood_atmosphere": "The overall mood or atmosphere of the image",
                        },
                    ),
                },
                """[concept.FeatureAnalysis]
definition = "Analysis of a photo's visual content and key features"

[concept.FeatureAnalysis.structure]
dominant_feature = { type = "text", definition = "The most important or dominant feature in the image", required = true }
visual_elements = { type = "text", definition = "Description of key visual elements present", required = true }
composition = "Analysis of the image composition"
color_palette = "Description of the main colors in the image"
mood_atmosphere = "The overall mood or atmosphere of the image\"""",
            ),
            # ConceptBlueprint with refines
            (
                {
                    "EnhancedText": ConceptBlueprint(
                        definition="Enhanced text content with additional metadata",
                        refines="Text",
                    ),
                },
                """[concept.EnhancedText]
definition = "Enhanced text content with additional metadata"
refines = "Text\"""",
            ),
            # ConceptBlueprint with structure name
            (
                {
                    "ProductInfo": ConceptBlueprint(
                        definition="Detailed information about a product",
                        structure="ProductStructure",
                    ),
                },
                """[concept.ProductInfo]
definition = "Detailed information about a product"
structure = "ProductStructure\"""",
            ),
        ],
    )
    def test_concepts_to_plx_string(self, concepts: dict[str, ConceptBlueprint | str], expected_plx: str):
        """Test converting concepts dict to PLX string."""
        result = PipelexInterpreter.concepts_to_plx_string(concepts)
        assert result == expected_plx
