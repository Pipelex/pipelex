from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint


class TestLLMPromptBlueprintRequiredVariables:
    """Test LLMPromptBlueprint.required_variables method."""

    def test_required_variables_returns_root_names_for_dotted_paths_in_prompt(self):
        """Test that dotted paths like user_profile.department are converted to root names like user_profile."""
        prompt_template = """
Process this marketing business document.
@user_profile.department
@doc_request.language

Output: "MARKETING_BUSINESS_PROCESSED"
"""
        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "user_profile" in required_vars
        assert "doc_request" in required_vars
        # Should NOT contain dotted paths
        assert "user_profile.department" not in required_vars
        assert "doc_request.language" not in required_vars

    def test_required_variables_returns_root_names_for_dotted_paths_in_system_prompt(self):
        """Test that dotted paths in system_prompt are converted to root names."""
        system_prompt_template = """
You are processing documents for @organization.name in @organization.region.
"""
        blueprint = LLMPromptBlueprint(
            system_prompt_blueprint=TemplateBlueprint(
                template=system_prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "organization" in required_vars
        # Should NOT contain dotted paths
        assert "organization.name" not in required_vars
        assert "organization.region" not in required_vars

    def test_required_variables_returns_root_names_for_both_prompts(self):
        """Test that both prompt and system_prompt dotted paths are converted to root names."""
        prompt_template = "@request.content"
        system_prompt_template = "Context: @context.metadata.source"

        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
            system_prompt_blueprint=TemplateBlueprint(
                template=system_prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "request" in required_vars
        assert "context" in required_vars
        # Should NOT contain dotted paths
        assert "request.content" not in required_vars
        assert "context.metadata.source" not in required_vars
        assert "context.metadata" not in required_vars

    def test_required_variables_handles_mix_of_root_and_dotted_paths(self):
        """Test that both root variables and dotted paths are handled correctly."""
        prompt_template = """
Process @simple_var and @complex_object.nested.value
Also use @another_object.field
"""
        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "simple_var" in required_vars
        assert "complex_object" in required_vars
        assert "another_object" in required_vars
        # Should NOT contain dotted paths
        assert "complex_object.nested.value" not in required_vars
        assert "complex_object.nested" not in required_vars
        assert "another_object.field" not in required_vars
        # Should have exactly 3 variables
        assert len(required_vars) == 3

    def test_required_variables_deduplicates_same_root(self):
        """Test that multiple dotted paths with same root are deduplicated."""
        prompt_template = """
Use @user.name and @user.email and @user.address.city
"""
        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "user" in required_vars
        assert len(required_vars) == 1

    def test_required_variables_excludes_internal_variables(self):
        """Test that internal variables starting with _ are excluded."""
        prompt_template = "@public_var and @_internal_var.field"

        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "public_var" in required_vars
        assert "_internal_var" not in required_vars

    def test_required_variables_excludes_special_variables(self):
        """Test that special variables preliminary_text and place_holder are excluded."""
        prompt_template = "@data and @preliminary_text and @place_holder"

        blueprint = LLMPromptBlueprint(
            prompt_blueprint=TemplateBlueprint(
                template=prompt_template,
                category=TemplateCategory.LLM_PROMPT,
            ),
        )

        required_vars = blueprint.required_variables()

        assert "data" in required_vars
        assert "preliminary_text" not in required_vars
        assert "place_holder" not in required_vars
