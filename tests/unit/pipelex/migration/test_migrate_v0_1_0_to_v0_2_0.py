from pathlib import Path

import pytest

from pipelex.migration.migrate_v0_1_0_to_v0_2_0 import MigrationResult, TOMLMigrator, migrate_concept_syntax


class TestTomlMigrator:
    """Unit tests for TomlMigrator class."""

    @pytest.fixture
    def migrator(self) -> TOMLMigrator:
        """Create a TomlMigrator instance."""
        return TOMLMigrator()

    @pytest.fixture
    def sample_old_syntax_content(self) -> str:
        """Sample TOML content with old Concept = syntax."""
        return """domain = "test"
description = "Test domain"

[concept]
SimpleText = "A simple text concept"
SimpleDoc = "A simple document concept"

[concept.ComplexConcept]
Concept = "A complex concept with old syntax"
refines = "Text"

[concept.AnotherConcept]
Concept = "Another concept to test migration"
structure = "CustomStructure"
refines = ["Text", "Document"]

[concept.AlreadyMigrated]
description = "This one is already migrated"
refines = "Text"
"""

    @pytest.fixture
    def sample_new_syntax_content(self) -> str:
        """Sample TOML content with new description = syntax."""
        return """domain = "test"
description = "Test domain"

[concept]
SimpleText = "A simple text concept"
SimpleDoc = "A simple document concept"

[concept.ComplexConcept]
description = "A complex concept with old syntax"
refines = "Text"

[concept.AnotherConcept]
description = "Another concept to test migration"
structure = "CustomStructure"
refines = ["Text", "Document"]

[concept.AlreadyMigrated]
description = "This one is already migrated"
refines = "Text"
"""

    def test_pattern_matching(self, migrator: TOMLMigrator) -> None:
        """Test that the regex pattern correctly identifies Concept = lines."""
        test_content = """[concept.TestConcept]
Concept = "A test concept"
refines = "Text"

[concept.AnotherConcept]
description = "Already migrated"
Concept = "This should be caught"
"""

        matches = list(migrator.concept_pattern.finditer(test_content))
        assert len(matches) == 2

        # Check first match
        assert matches[0].group(2) == "Concept"
        assert matches[0].group(4) == '"A test concept"'

        # Check second match
        assert matches[1].group(2) == "Concept"
        assert matches[1].group(4) == '"This should be caught"'

    def test_pattern_replacement(self, migrator: TOMLMigrator) -> None:
        """Test that the regex pattern correctly replaces Concept = with description =."""
        test_content = """[concept.TestConcept]
Concept = "A test concept"
refines = "Text"

[concept.IndentedConcept]
    Concept = "Indented concept"
    refines = "Text"
"""

        expected_content = """[concept.TestConcept]
description = "A test concept"
refines = "Text"

[concept.IndentedConcept]
    description = "Indented concept"
    refines = "Text"
"""

        result = migrator.migrate_content(test_content)
        assert result == expected_content

    def test_preserves_formatting(self, migrator: TOMLMigrator) -> None:
        """Test that migration preserves indentation and spacing."""
        test_cases = [
            # No indentation
            ('Concept = "test"', 'description = "test"'),
            # With spaces
            ('  Concept = "test"', '  description = "test"'),
            # With tabs
            ('\tConcept = "test"', '\tdescription = "test"'),
            # Mixed indentation
            ('  \tConcept = "test"', '  \tdescription = "test"'),
            # Various spacing around =
            ('Concept ="test"', 'description ="test"'),
            ('Concept= "test"', 'description= "test"'),
            ('Concept   =   "test"', 'description   =   "test"'),
        ]

        for original, expected in test_cases:
            result = migrator.migrate_content(original)
            assert result == expected, f"Failed for: {original}"

    def test_ignores_non_concept_lines(self, migrator: TOMLMigrator) -> None:
        """Test that migration doesn't affect non-concept Concept = lines."""
        # These should NOT be changed
        test_content = """# This is a comment about Concept = something
description = "This pipe works with Concept = something"
prompt_template = "Define the Concept = whatever"
"""

        result = migrator.migrate_content(test_content)
        # Should be unchanged since none start with Concept =
        assert result == test_content

    def test_ignores_concept_inside_multiline_strings(self, migrator: TOMLMigrator) -> None:
        """Test that migration ignores Concept = inside multiline strings."""
        test_content = '''domain = "test"

[concept.ValidConcept]
Concept = "This should be migrated"
refines = "Text"

[pipe.test_pipe]
prompt_template = """
Transform this:
Concept = "This should NOT be migrated because it's inside a multiline string"
Do something with it.
"""

[concept.AnotherValidConcept]
Concept = "This should also be migrated"
refines = "Document"
'''

        result = migrator.migrate_content(test_content)

        # Valid concept definitions should be migrated
        assert 'description = "This should be migrated"' in result
        assert 'description = "This should also be migrated"' in result

        # Concept inside multiline string should NOT be migrated
        assert 'Concept = "This should NOT be migrated because it\'s inside a multiline string"' in result

        # Should not have the old syntax for valid concepts
        assert 'Concept = "This should be migrated"' not in result
        assert 'Concept = "This should also be migrated"' not in result

    def test_multiline_string_detection_with_single_quotes(self, migrator: TOMLMigrator) -> None:
        """Test that multiline string detection works with both double and single quotes."""
        test_content = """domain = "test"

[concept.ValidConcept]
Concept = "Should be migrated"

[pipe.test_pipe]
prompt_template = '''
This is a single-quote multiline string:
Concept = "Should NOT be migrated"
'''

[concept.AnotherValidConcept]
Concept = "Should also be migrated"
"""

        result = migrator.migrate_content(test_content)

        # Valid concepts should be migrated
        assert 'description = "Should be migrated"' in result
        assert 'description = "Should also be migrated"' in result

        # Concept inside single-quote multiline string should NOT be migrated
        assert 'Concept = "Should NOT be migrated"' in result

    def test_needs_migration_detection(self, migrator: TOMLMigrator, sample_old_syntax_content: str, sample_new_syntax_content: str) -> None:
        """Test needs_migration correctly identifies files that need migration."""
        assert migrator.needs_migration(sample_old_syntax_content) is True
        assert migrator.needs_migration(sample_new_syntax_content) is False

    def test_get_migration_preview(self, migrator: TOMLMigrator) -> None:
        """Test getting preview of migration changes."""
        test_content = """[concept.TestConcept]
Concept = "A test concept"
refines = "Text"

[concept.AnotherConcept]
    Concept = "Another concept"
    refines = "Text"
"""

        changes = migrator.get_migration_preview(test_content)

        assert len(changes) == 2
        assert changes[0]["line_number"] == 2
        assert changes[0]["old_line"] == 'Concept = "A test concept"'
        assert changes[0]["new_line"] == 'description = "A test concept"'

        assert changes[1]["line_number"] == 6
        assert changes[1]["old_line"] == 'Concept = "Another concept"'
        assert changes[1]["new_line"] == 'description = "Another concept"'

    def test_migrate_file_success(
        self,
        migrator: TOMLMigrator,
        tmp_path: Path,
        sample_old_syntax_content: str,
        sample_new_syntax_content: str,
    ) -> None:
        """Test successful file migration."""
        test_file = tmp_path / "test.toml"
        test_file.write_text(sample_old_syntax_content)

        changes_count = migrator.migrate_file(test_file, create_backup=True)

        # Check that file was migrated correctly
        migrated_content = test_file.read_text()
        assert migrated_content == sample_new_syntax_content

        # Check that backup was created
        backup_file = tmp_path / "test.toml.backup"
        assert backup_file.exists()
        backup_content = backup_file.read_text()
        assert backup_content == sample_old_syntax_content

        # Check changes count
        assert changes_count == 2  # Two "Concept =" lines in the sample

    def test_migrate_file_no_changes_needed(self, migrator: TOMLMigrator, tmp_path: Path, sample_new_syntax_content: str) -> None:
        """Test file migration when no changes are needed."""
        test_file = tmp_path / "test.toml"
        test_file.write_text(sample_new_syntax_content)

        changes_count = migrator.migrate_file(test_file, create_backup=True)

        # File should be unchanged
        content = test_file.read_text()
        assert content == sample_new_syntax_content

        # No backup should be created
        backup_file = tmp_path / "test.toml.backup"
        assert not backup_file.exists()

        # No changes should be reported
        assert changes_count == 0

    def test_migrate_file_without_backup(
        self,
        migrator: TOMLMigrator,
        tmp_path: Path,
        sample_old_syntax_content: str,
        sample_new_syntax_content: str,
    ) -> None:
        """Test file migration without creating backup."""
        test_file = tmp_path / "test.toml"
        test_file.write_text(sample_old_syntax_content)

        changes_count = migrator.migrate_file(test_file, create_backup=False)

        # Check that file was migrated correctly
        migrated_content = test_file.read_text()
        assert migrated_content == sample_new_syntax_content

        # Check that no backup was created
        backup_file = tmp_path / "test.toml.backup"
        assert not backup_file.exists()

        # Check changes count
        assert changes_count == 2

    def test_find_toml_files(self, migrator: TOMLMigrator, tmp_path: Path) -> None:
        """Test finding TOML files in directory and subdirectories."""
        # Create some TOML files
        (tmp_path / "file1.toml").write_text("content1")
        (tmp_path / "file2.toml").write_text("content2")

        # Create subdirectory with TOML file
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.toml").write_text("content3")

        # Create non-TOML file (should be ignored)
        (tmp_path / "file.txt").write_text("not toml")

        toml_files = migrator.find_toml_files(tmp_path)
        toml_files.sort()  # Sort for consistent testing

        expected_files = [
            tmp_path / "file1.toml",
            tmp_path / "file2.toml",
            tmp_path / "subdir" / "file3.toml",
        ]
        expected_files.sort()

        assert toml_files == expected_files

    def test_find_toml_files_nonexistent_directory(self, migrator: TOMLMigrator, tmp_path: Path) -> None:
        """Test finding TOML files in nonexistent directory."""
        nonexistent_dir = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError):
            migrator.find_toml_files(nonexistent_dir)

    def test_migrate_directory_success(self, migrator: TOMLMigrator, tmp_path: Path) -> None:
        """Test successful directory migration."""
        # Create files with different states
        file1 = tmp_path / "file1.toml"
        file1.write_text("""[concept.Test1]
Concept = "Old syntax file 1"
""")

        file2 = tmp_path / "file2.toml"
        file2.write_text("""[concept.Test2]
description = "Already migrated file 2"
""")

        file3 = tmp_path / "file3.toml"
        file3.write_text("""[concept.Test3]
Concept = "Old syntax file 3"
[concept.Test4]
Concept = "Another old concept"
""")

        result = migrator.migrate_directory(tmp_path, create_backups=True, dry_run=False)

        # Check results
        assert result.files_processed == 3
        assert result.files_modified == 2  # file1 and file3 needed migration
        assert result.total_changes == 3  # 1 change in file1, 2 changes in file3
        assert len(result.modified_files) == 2
        assert len(result.errors) == 0

        # Check that files were migrated correctly
        assert 'description = "Old syntax file 1"' in file1.read_text()
        assert 'description = "Already migrated file 2"' in file2.read_text()  # Unchanged
        assert 'description = "Old syntax file 3"' in file3.read_text()
        assert 'description = "Another old concept"' in file3.read_text()

        # Check backups exist for modified files only
        assert (tmp_path / "file1.toml.backup").exists()
        assert not (tmp_path / "file2.toml.backup").exists()  # No changes needed
        assert (tmp_path / "file3.toml.backup").exists()

    def test_migrate_directory_dry_run(self, migrator: TOMLMigrator, tmp_path: Path) -> None:
        """Test directory migration in dry-run mode."""
        # Create file with old syntax
        test_file = tmp_path / "test.toml"
        original_content = """[concept.Test]
Concept = "Old syntax"
"""
        test_file.write_text(original_content)

        result = migrator.migrate_directory(tmp_path, create_backups=False, dry_run=True)

        # Check results
        assert result.files_processed == 1
        assert result.files_modified == 1
        assert result.total_changes == 1
        assert len(result.modified_files) == 1
        assert len(result.errors) == 0

        # Check that file was NOT actually modified
        content = test_file.read_text()
        assert content == original_content

        # Check that no backup was created
        backup_file = tmp_path / "test.toml.backup"
        assert not backup_file.exists()

    def test_migrate_directory_no_toml_files(self, migrator: TOMLMigrator, tmp_path: Path) -> None:
        """Test directory migration with no TOML files."""
        # Create non-TOML file
        (tmp_path / "file.txt").write_text("not toml")

        result = migrator.migrate_directory(tmp_path, create_backups=True, dry_run=False)

        assert result.files_processed == 0
        assert result.files_modified == 0
        assert result.total_changes == 0
        assert len(result.modified_files) == 0
        assert len(result.errors) == 0


class TestMigrateConceptSyntax:
    """Test the convenience function."""

    def test_migrate_concept_syntax_function(self, tmp_path: Path) -> None:
        """Test the convenience function works correctly."""
        # Create test file
        test_file = tmp_path / "test.toml"
        test_file.write_text("""[concept.Test]
Concept = "Test concept"
""")

        result = migrate_concept_syntax(tmp_path, create_backups=True, dry_run=False)

        assert result.files_processed == 1
        assert result.files_modified == 1
        assert result.total_changes == 1
        assert len(result.modified_files) == 1
        assert len(result.errors) == 0

        # Check migration worked
        assert 'description = "Test concept"' in test_file.read_text()
        assert (tmp_path / "test.toml.backup").exists()


class TestMigrationResult:
    """Test the MigrationResult NamedTuple."""

    def test_migration_result_creation(self) -> None:
        """Test creating MigrationResult."""
        result = MigrationResult(
            files_processed=5,
            files_modified=3,
            total_changes=7,
            modified_files=[Path("file1.toml"), Path("file2.toml")],
            errors=["Error 1", "Error 2"],
        )

        assert result.files_processed == 5
        assert result.files_modified == 3
        assert result.total_changes == 7
        assert len(result.modified_files) == 2
        assert len(result.errors) == 2
