"""Migration from version 0.1.0 to 0.2.0 - Concept = to definition = syntax change."""

import re
import shutil
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Match

from pipelex.migration.migration_result import MigrationResult


class TOMLMigrator:
    """Handles migration from Concept = to definition = and PipeClassName = to type/definition syntax in TOML files."""

    # Known pipe class names based on the factory classes in the codebase
    PIPE_CLASS_NAMES: ClassVar[set[str]] = {
        "PipeLLM",
        "PipeOcr",
        "PipeImgGen",
        "PipeFunc",
        "PipeJinja2",
        "PipeLLMPrompt",
        "PipeSequence",
        "PipeBatch",
        "PipeCondition",
        "PipeParallel",
    }

    def __init__(self):
        # Pattern to match "Concept = " within concept sections
        self.concept_pattern = re.compile(r"^(\s*)(Concept)(\s*=\s*)(.*)$", re.MULTILINE)

        # Pattern to match pipe class name assignments: PipeClassName = "description"
        pipe_classes = "|".join(self.PIPE_CLASS_NAMES)
        self.pipe_pattern = re.compile(
            rf"^(\s*)({pipe_classes})(\s*=\s*)(\"[^\"]*\"|'[^']*')(\s*)$",
            re.MULTILINE,
        )

    def find_toml_files(self, directory: Path) -> List[Path]:
        """Find all TOML files in directory and subdirectories."""
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        return list(directory.glob("**/*.toml"))

    def _is_line_inside_multiline_string(self, content: str, line_start_pos: int) -> bool:
        """Check if a line position is inside a multiline string (triple quotes)."""
        # Count triple quotes before this position
        content_before = content[:line_start_pos]

        # Count both """ and ''' (TOML supports both)
        triple_double_quotes = content_before.count('"""')
        triple_single_quotes = content_before.count("'''")

        # If odd number of triple quotes before this line, we're inside a multiline string
        return (triple_double_quotes % 2 == 1) or (triple_single_quotes % 2 == 1)

    def needs_migration(self, content: str) -> bool:
        """Check if content contains old Concept = or PipeClassName = syntax that should be migrated."""
        # Check concept patterns
        concept_matches = list(self.concept_pattern.finditer(content))
        for match in concept_matches:
            if not self._is_line_inside_multiline_string(content, match.start()):
                return True

        # Check pipe patterns
        pipe_matches = list(self.pipe_pattern.finditer(content))
        for match in pipe_matches:
            if not self._is_line_inside_multiline_string(content, match.start()):
                return True

        return False

    def get_migration_preview(self, content: str) -> List[Dict[str, Any]]:
        """Get preview of changes that would be made."""
        changes: List[Dict[str, Any]] = []

        # Handle concept migrations
        concept_matches = list(self.concept_pattern.finditer(content))
        for match in concept_matches:
            # Skip if this match is inside a multiline string
            if self._is_line_inside_multiline_string(content, match.start()):
                continue

            line_num = content[: match.start()].count("\n") + 1
            old_line = match.group(0)
            new_line = self.concept_pattern.sub(r"\1definition\3\4", old_line)

            changes.append({"line_number": line_num, "old_line": old_line.strip(), "new_line": new_line.strip()})

        # Handle pipe migrations
        pipe_matches = list(self.pipe_pattern.finditer(content))
        for match in pipe_matches:
            # Skip if this match is inside a multiline string
            if self._is_line_inside_multiline_string(content, match.start()):
                continue

            line_num = content[: match.start()].count("\n") + 1
            leading_whitespace = match.group(1)
            pipe_class_name = match.group(2)
            definition_value = match.group(4)

            old_line = match.group(0)
            type_line = f'{leading_whitespace}type = "{pipe_class_name}"'
            definition_line = f"{leading_whitespace}definition = {definition_value}"
            new_line = f"{type_line}\\n{definition_line}"

            changes.append({"line_number": line_num, "old_line": old_line.strip(), "new_line": new_line})

        return changes

    def migrate_content(self, content: str) -> str:
        """Migrate content from old to new syntax."""

        def concept_replacement_function(match: Match[str]) -> str:
            # Check if this match is inside a multiline string
            if self._is_line_inside_multiline_string(content, match.start()):
                # Return the original text unchanged
                return match.group(0)
            else:
                # Apply the normal replacement: Concept = -> definition =
                return f"{match.group(1)}definition{match.group(3)}{match.group(4)}"

        def pipe_replacement_function(match: Match[str]) -> str:
            # Check if this match is inside a multiline string
            if self._is_line_inside_multiline_string(content, match.start()):
                # Return the original text unchanged
                return match.group(0)
            else:
                # Apply pipe replacement: PipeClassName = "desc" -> type = "PipeClassName"\ndefinition = "desc"
                leading_whitespace = match.group(1)
                pipe_class_name = match.group(2)
                definition_value = match.group(4)
                trailing_whitespace = match.group(5)

                type_line = f'{leading_whitespace}type = "{pipe_class_name}"'
                definition_line = f"{leading_whitespace}definition = {definition_value}"

                return f"{type_line}\n{definition_line}{trailing_whitespace}"

        # Apply concept migrations first
        migrated_content = self.concept_pattern.sub(concept_replacement_function, content)
        # Then apply pipe migrations
        migrated_content = self.pipe_pattern.sub(pipe_replacement_function, migrated_content)

        return migrated_content

    def migrate_file(self, file_path: Path, create_backup: bool = True) -> int:
        """
        Migrate a single file from old to new syntax.

        Returns:
            Number of changes made in the file
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:
            raise IOError(f"Failed to read file {file_path}: {e}")

        if not self.needs_migration(original_content):
            return 0

        migrated_content = self.migrate_content(original_content)

        # Count only the changes that are NOT inside multiline strings
        matches = list(self.concept_pattern.finditer(original_content))
        changes_count = 0
        for match in matches:
            if not self._is_line_inside_multiline_string(original_content, match.start()):
                changes_count += 1

        if create_backup:
            backup_path = file_path.with_suffix(".toml.backup")
            try:
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                raise IOError(f"Failed to create backup for {file_path}: {e}")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(migrated_content)
        except Exception as e:
            raise IOError(f"Failed to write migrated content to {file_path}: {e}")

        return changes_count

    def migrate_directory(self, directory: Path, create_backups: bool = True, dry_run: bool = False) -> MigrationResult:
        """
        Migrate all TOML files in a directory.

        Args:
            directory: Directory containing TOML files
            create_backups: Whether to create backup files
            dry_run: If True, only preview changes without applying them

        Returns:
            MigrationResult with statistics and details
        """
        toml_files = self.find_toml_files(directory)
        files_processed = len(toml_files)
        files_modified = 0
        total_changes = 0
        modified_files: List[Path] = []
        errors: List[str] = []

        for toml_file in toml_files:
            try:
                with open(toml_file, "r", encoding="utf-8") as f:
                    content = f.read()

                if not self.needs_migration(content):
                    continue

                # Count only changes that are NOT inside multiline strings
                matches = list(self.concept_pattern.finditer(content))
                changes_count = 0
                for match in matches:
                    if not self._is_line_inside_multiline_string(content, match.start()):
                        changes_count += 1

                if dry_run:
                    # Just count the changes for dry run
                    files_modified += 1
                    total_changes += changes_count
                    modified_files.append(toml_file)
                else:
                    # Actually perform the migration
                    actual_changes = self.migrate_file(toml_file, create_backup=create_backups)
                    files_modified += 1
                    total_changes += actual_changes
                    modified_files.append(toml_file)

            except Exception as e:
                errors.append(f"Error processing {toml_file}: {e}")

        result = MigrationResult()
        result.files_processed = files_processed
        result.files_modified = files_modified
        result.total_changes = total_changes
        result.modified_files = modified_files
        result.errors = errors
        return result


def migrate_concept_syntax(directory: Path, create_backups: bool = True, dry_run: bool = False) -> MigrationResult:
    """
    Convenience function to migrate TOML files from Concept = to definition = syntax.

    This function accepts either a directory (the historical behavior) or a path to a single TOML file.

    Args:
        directory: Path to a directory containing TOML files to migrate, or a single TOML file
        create_backups: Whether to create backup files before migration (ignored in dry-run)
        dry_run: If True, only preview changes without applying them

    Returns:
        MigrationResult with migration statistics
    """
    migrator = TOMLMigrator()

    # Support passing a single TOML file path in addition to a directory
    input_path = directory
    if input_path.is_file():
        result = MigrationResult()
        result.files_processed = 1

        if input_path.suffix.lower() != ".toml":
            result.errors.append(f"Provided file is not a .toml file: {input_path}")
            return result

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            result.errors.append(f"Failed to read file {input_path}: {e}")
            return result

        if not migrator.needs_migration(content):
            return result

        # Count only concept changes for consistency with directory migration statistics
        def _is_inside_multiline_string(text: str, position: int) -> bool:
            """Local helper to check if a position is inside a TOML multiline string."""
            text_before = text[:position]
            triple_double_quotes = text_before.count('"""')
            triple_single_quotes = text_before.count("'''")
            return (triple_double_quotes % 2 == 1) or (triple_single_quotes % 2 == 1)

        matches = list(migrator.concept_pattern.finditer(content))
        changes_count = 0
        for match in matches:
            if not _is_inside_multiline_string(content, match.start()):
                changes_count += 1

        if dry_run:
            result.files_modified = 1
            result.total_changes = changes_count
            result.modified_files.append(input_path)
            return result

        # Perform actual migration
        try:
            actual_changes = migrator.migrate_file(input_path, create_backup=create_backups)
            result.files_modified = 1
            result.total_changes = actual_changes
            result.modified_files.append(input_path)
        except Exception as e:
            result.errors.append(f"Error processing {input_path}: {e}")

        return result

    # Default: treat as directory (existing behavior)
    return migrator.migrate_directory(input_path, create_backups, dry_run)
