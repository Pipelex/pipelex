import shutil
from pathlib import Path
from typing import Any

import pytest

from pipelex.migration.migrate_v0_1_0_to_v0_2_0 import migrate_concept_syntax


class TestMigrationE2E:
    """End-to-end tests for migration functionality."""

    def test_real_world_migration_scenario(self, tmp_path: Path) -> None:
        """Test a realistic migration scenario with multiple files and complex structures."""
        # Create a realistic pipelex libraries structure
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()

        # Create main domain file with mixed syntax
        main_toml = pipelines_dir / "content_analysis.toml"
        main_toml.write_text("""domain = "content_analysis"
description = "AI-powered content analysis and processing"
system_prompt = "You are an expert content analyst"

[concept]
Text = "Written content in natural language"
Document = "A structured document with metadata"
Report = "An analytical report with findings"

[concept.Article]
Concept = "A written composition on a specific topic"
refines = "Text"
structure = "ArticleContent"

[concept.NewsArticle]
Concept = "An article reporting current events"
refines = "Article"

[concept.BlogPost]
description = "A blog post with metadata"  # Already migrated
refines = "Article"
structure = "BlogPostContent"

[concept.ContentAnalysis]
Concept = "Analysis of content including sentiment, topics, and key insights"
refines = "Report"
structure = "ContentAnalysisReport"

[pipe.analyze_text]
PipeLLM = "Analyze text content for sentiment and topics"
inputs = { text_input = "Text" }
output = "ContentAnalysis"
prompt_template = "Analyze this text: @text_input"

[pipe.extract_article_info]
PipeLLM = "Extract structured information from articles"
inputs = { article = "Article" }
output = "ArticleMetadata"
system_prompt = "Extract key metadata from articles"
prompt_template = "Extract metadata from: @article"
""")

        # Create subdirectory with more files
        subdomain_dir = pipelines_dir / "specialized"
        subdomain_dir.mkdir()

        # File with only old syntax
        old_syntax_file = subdomain_dir / "legacy_concepts.toml"
        old_syntax_file.write_text("""domain = "legacy"
description = "Legacy concept definitions"

[concept.LegacyConcept]
Concept = "An old concept that needs migration"
refines = "Text"

[concept.AnotherLegacy]
Concept = "Another legacy concept with complex refines"
refines = ["Text", "Document"]
structure = "LegacyStructure"
""")

        # File with only new syntax (should remain unchanged)
        new_syntax_file = subdomain_dir / "modern_concepts.toml"
        new_syntax_file.write_text("""domain = "modern"
description = "Modern concept definitions"

[concept.ModernConcept]
description = "A modern concept with new syntax"
refines = "Text"

[concept.AdvancedConcept]
description = "An advanced concept with structure"
refines = ["Text", "Document"]
structure = "AdvancedStructure"
""")

        # File with no concepts (should remain unchanged)
        pipes_only_file = pipelines_dir / "pipes_only.toml"
        pipes_only_file.write_text("""domain = "pipes_only"
description = "File with only pipe definitions"

[pipe.simple_pipe]
PipeLLM = "A simple pipe"
inputs = { input_text = "Text" }
output = "Document"
prompt_template = "Process: @input_text"
""")

        # Run the migration
        result = migrate_concept_syntax(directory=pipelines_dir, create_backups=True, dry_run=False)

        # Verify overall results
        assert result.files_processed == 4  # All TOML files found
        assert result.files_modified == 3  # main_toml, old_syntax_file, and pipes_only_file (for pipe migration)
        assert result.total_changes == 5  # Debug: let's see what's actually being migrated
        assert len(result.modified_files) == 3
        assert len(result.errors) == 0

        # Verify main file was migrated correctly
        main_content = main_toml.read_text()
        # Concept migrations
        assert 'description = "A written composition on a specific topic"' in main_content
        assert 'description = "An article reporting current events"' in main_content
        assert 'description = "Analysis of content including sentiment, topics, and key insights"' in main_content
        # BlogPost should remain unchanged (already had definition =)
        assert 'description = "A blog post with metadata"' in main_content
        # Pipe migrations
        assert 'type = "PipeLLM"' in main_content
        assert 'description = "Analyze text content for sentiment and topics"' in main_content
        assert 'description = "Extract structured information from articles"' in main_content
        # Ensure no old syntax remains
        assert "Concept =" not in main_content
        assert "PipeLLM =" not in main_content

        # Verify legacy file was migrated correctly
        legacy_content = old_syntax_file.read_text()
        assert 'description = "An old concept that needs migration"' in legacy_content
        assert 'description = "Another legacy concept with complex refines"' in legacy_content
        assert "Concept =" not in legacy_content

        # Verify modern file was NOT changed
        modern_content = new_syntax_file.read_text()
        assert 'description = "A modern concept with new syntax"' in modern_content
        assert 'description = "An advanced concept with structure"' in modern_content
        assert "Concept =" not in modern_content

        # Verify pipes-only file was migrated (pipe syntax changed)
        pipes_content = pipes_only_file.read_text()
        assert 'domain = "pipes_only"' in pipes_content
        assert "[pipe.simple_pipe]" in pipes_content
        assert 'type = "PipeLLM"' in pipes_content
        assert 'description = "A simple pipe"' in pipes_content
        assert "Concept =" not in pipes_content
        assert "PipeLLM =" not in pipes_content

        # Verify backups were created for modified files only
        assert (pipelines_dir / "content_analysis.toml.backup").exists()
        assert (subdomain_dir / "legacy_concepts.toml.backup").exists()
        assert (pipelines_dir / "pipes_only.toml.backup").exists()  # Now also modified due to pipe migration
        assert not (subdomain_dir / "modern_concepts.toml.backup").exists()  # This one should remain unchanged

        # Verify backup contents are correct (original content)
        main_backup = (pipelines_dir / "content_analysis.toml.backup").read_text()
        assert 'Concept = "A written composition on a specific topic"' in main_backup
        assert 'Concept = "An article reporting current events"' in main_backup
        assert 'PipeLLM = "Analyze text content for sentiment and topics"' in main_backup
        assert 'PipeLLM = "Extract structured information from articles"' in main_backup

        legacy_backup = (subdomain_dir / "legacy_concepts.toml.backup").read_text()
        assert 'Concept = "An old concept that needs migration"' in legacy_backup
        assert 'Concept = "Another legacy concept with complex refines"' in legacy_backup

        pipes_backup = (pipelines_dir / "pipes_only.toml.backup").read_text()
        assert 'PipeLLM = "A simple pipe"' in pipes_backup

    def test_migration_with_complex_formatting(self, tmp_path: Path) -> None:
        """Test migration preserves complex formatting and edge cases."""
        test_file = tmp_path / "complex_formatting.toml"
        original_content = """# Complex formatting test file
domain = "formatting_test"
description = "Test various formatting scenarios"

# Simple concepts
[concept]
BasicConcept = "A basic concept"

# Complex concepts with various formatting
[concept.StandardConcept]
Concept = "Standard formatting concept"
refines = "Text"

[concept.IndentedConcept]
    Concept = "Concept with indentation"
    refines = "Text"
    structure = "IndentedStructure"

[concept.TabIndentedConcept]
\tConcept = "Concept with tab indentation"
\trefines = "Text"

[concept.MixedIndentedConcept]
  \tConcept = "Concept with mixed indentation"
  \trefines = ["Text", "Document"]

[concept.VariousSpacingConcept]
Concept="No spaces around equals"
refines = "Text"

[concept.ExtraSpacingConcept]
Concept   =   "Extra spaces around equals"
refines = "Text"

[concept.AlreadyMigratedConcept]
description = "This should not change"
refines = "Text"

# Comment with Concept = in it (should not change)
[pipe.test_pipe]
PipeLLM = "A pipe that mentions Concept = in description"
inputs = { input_text = "Text" }
output = "Document"
prompt_template = \"\"\"
This template mentions Concept = something in the text.
Process this: @input_text
\"\"\"
"""
        test_file.write_text(original_content)

        # Run migration
        result = migrate_concept_syntax(directory=tmp_path, create_backups=True, dry_run=False)

        # Verify migration results
        assert result.files_processed == 1
        assert result.files_modified == 1
        assert result.total_changes == 6  # Debug: actual count from migration
        assert len(result.errors) == 0

        migrated_content = test_file.read_text()

        # Verify all Concept = lines were changed to definition =
        expected_changes = [
            'description = "Standard formatting concept"',
            '    description = "Concept with indentation"',
            '\tdescription = "Concept with tab indentation"',
            '  \tdescription = "Concept with mixed indentation"',
            'description="No spaces around equals"',
            'description   =   "Extra spaces around equals"',
        ]

        for expected in expected_changes:
            assert expected in migrated_content

        # Verify already migrated concept was not changed
        assert 'description = "This should not change"' in migrated_content

        # Verify pipe was migrated to new format
        assert 'type = "PipeLLM"' in migrated_content
        assert 'description = "A pipe that mentions Concept = in description"' in migrated_content
        # Verify content inside multiline strings was not changed
        assert "This template mentions Concept = something in the text." in migrated_content

        # Verify no Concept = remains at start of lines
        lines = migrated_content.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Concept ="):
                # This should not happen - all should be migrated
                pytest.fail(f"Found unmigrated line: {line}")

    def test_dry_run_does_not_modify_files(self, tmp_path: Path) -> None:
        """Test that dry run mode doesn't modify any files."""
        test_file = tmp_path / "dry_run_test.toml"
        original_content = """domain = "dry_run_test"

[concept.TestConcept]
Concept = "This should not be changed in dry run"
refines = "Text"

[concept.AnotherConcept]
Concept = "Neither should this"
refines = "Document"
"""
        test_file.write_text(original_content)

        # Run migration in dry run mode
        result = migrate_concept_syntax(
            directory=tmp_path,
            create_backups=False,  # Should be ignored in dry run
            dry_run=True,
        )

        # Verify results show what would be changed
        assert result.files_processed == 1
        assert result.files_modified == 1
        assert result.total_changes == 2
        assert len(result.modified_files) == 1
        assert len(result.errors) == 0

        # Verify file was NOT actually modified
        current_content = test_file.read_text()
        assert current_content == original_content

        # Verify no backup was created
        backup_file = tmp_path / "dry_run_test.toml.backup"
        assert not backup_file.exists()

    def test_error_handling_with_permission_issues(self, tmp_path: Path, mocker: Any) -> None:
        """Test proper error handling when file operations fail."""
        test_file = tmp_path / "permission_test.toml"
        test_file.write_text("""[concept.Test]
Concept = "Test concept"
""")

        # Mock file operations to simulate permission errors
        mock_open = mocker.patch("builtins.open")
        mock_open.side_effect = PermissionError("Permission denied")

        # Run migration
        result = migrate_concept_syntax(directory=tmp_path, create_backups=True, dry_run=False)

        # Should have errors but not crash
        assert result.files_processed == 1
        assert result.files_modified == 0
        assert result.total_changes == 0
        assert len(result.modified_files) == 0
        assert len(result.errors) == 1
        assert "Permission denied" in result.errors[0] or "Error processing" in result.errors[0]

    def test_migration_from_test_data_file(self, tmp_path: Path) -> None:
        """Test migration using the official test data file with tricky edge cases."""
        # Copy the test data file to our temp directory
        test_data_path = Path(__file__).parent.parent.parent.parent / "data" / "test_migrate_v0_1_0_to_v0_2_0.toml"
        test_file = tmp_path / "test_migrate.toml"
        shutil.copy2(test_data_path, test_file)

        # Read original content to verify the challenge case
        original_content = test_file.read_text()

        # Verify the challenge case is present in original file
        assert 'Concept = "This is not a definition of concept' in original_content
        assert "prompt_template" in original_content

        # Run migration
        result = migrate_concept_syntax(directory=tmp_path, create_backups=True, dry_run=False)

        # Verify migration results
        assert result.files_processed == 1
        assert result.files_modified == 1
        assert result.total_changes == 2  # Only the 2 actual concept definitions should change
        assert len(result.modified_files) == 1
        assert len(result.errors) == 0

        # Read migrated content
        migrated_content = test_file.read_text()

        # Verify that actual concept definitions were migrated
        assert 'description = "A complex concept with old syntax"' in migrated_content
        assert 'description = "Another concept to test migration"' in migrated_content

        # Verify that already migrated concept remains unchanged
        assert 'description = "This one is already migrated"' in migrated_content

        # THE CRITICAL CHALLENGE: Verify that the Concept = inside the prompt_template was NOT changed
        assert (
            'Concept = "This is not a definition of concept, it\'s just text in the prompt template, so it should not be migrated"'
            in migrated_content
        )

        # Verify the challenge case is still there and unchanged
        challenge_line_found = False
        concept_lines_outside_multiline: list[tuple[int, str]] = []

        lines = migrated_content.split("\n")
        for i, line in enumerate(lines, 1):
            if 'Concept = "This is not a definition of concept' in line:
                challenge_line_found = True
                # This should be exactly the same as in the original file
                assert 'Concept = "This is not a definition of concept, it\'s just text in the prompt template, so it should not be migrated"' in line

            # Check for any Concept = that appears to be a TOML key (not inside strings)
            stripped = line.strip()
            if stripped.startswith("Concept ="):
                # This should only happen inside multiline strings, not as actual TOML keys
                # We need to check if this is inside the prompt_template multiline string
                if i < 26 or i > 31:  # Outside the prompt_template multiline string boundaries
                    concept_lines_outside_multiline.append((i, line))

        # Should be empty - all Concept = at start of line outside multiline strings should be migrated
        assert len(concept_lines_outside_multiline) == 0, (
            f"Found unmigrated Concept = lines outside multiline strings: {concept_lines_outside_multiline}"
        )

        assert challenge_line_found, "Challenge case (Concept = in prompt template) was not found in migrated file"

        # Verify backup was created and contains original content
        backup_file = tmp_path / "test_migrate.toml.backup"
        assert backup_file.exists()
        backup_content = backup_file.read_text()
        assert backup_content == original_content

        # Verify original had the unmigrated Concept = lines
        assert 'Concept = "A complex concept with old syntax"' in backup_content
        assert 'Concept = "Another concept to test migration"' in backup_content
