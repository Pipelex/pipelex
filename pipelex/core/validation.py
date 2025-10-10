from pydantic import ValidationError

from pipelex import log
from pipelex.config import get_config
from pipelex.tools.typing.pydantic_utils import analyze_pydantic_validation_error


def report_validation_error(category: str, validation_error: ValidationError) -> str:
    validation_error_analysis = analyze_pydantic_validation_error(validation_error)

    migration_config = get_config().migration

    migration_reports: list[str] = []

    # Build field-to-renamings mapping for missing fields
    log.debug(validation_error_analysis.missing_fields, title="Missing fields")
    missing_field_renamings: dict[tuple[tuple[str, str], ...], list[str]] = {}
    for missing_field in validation_error_analysis.missing_fields:
        text = missing_field.split(".")[-1]
        if renamings := migration_config.text_in_renaming_values(category=category, text=text):
            # Use tuple of renamings as key for grouping
            renamings_key = tuple(renamings)
            if renamings_key not in missing_field_renamings:
                missing_field_renamings[renamings_key] = []
            missing_field_renamings[renamings_key].append(missing_field)

    # Build field-to-renamings mapping for extra fields
    log.debug(validation_error_analysis.extra_fields, title="Extra fields")
    extra_field_renamings: dict[tuple[tuple[str, str], ...], list[str]] = {}
    for extra_field in validation_error_analysis.extra_fields:
        # Extract field path before the colon (extra fields include ": value")
        field_path = extra_field.split(":")[0].strip()
        text = field_path.split(".")[-1]
        if renamings := migration_config.text_in_renaming_keys(category=category, text=text):
            renamings_key = tuple(renamings)
            if renamings_key not in extra_field_renamings:
                extra_field_renamings[renamings_key] = []
            extra_field_renamings[renamings_key].append(extra_field)

    # Format grouped output for missing fields
    for renamings_tuple, fields in missing_field_renamings.items():
        renamings_str = "\n".join(f"• '{key}' -> '{value}'" for key, value in renamings_tuple)
        if len(fields) == 1:
            msg = f"Missing field '{fields[0]}' is possibly a new name related to one of these renamings:\n{renamings_str}"
        else:
            fields_str = ", ".join(f"'{f}'" for f in fields)
            msg = f"Missing fields [{fields_str}] are possibly new names related to one of these renamings:\n{renamings_str}"
        migration_reports.append(msg)

    # Format grouped output for extra fields
    for renamings_tuple, fields in extra_field_renamings.items():
        renamings_str = "\n".join(f"• '{key}' -> '{value}'" for key, value in renamings_tuple)
        if len(fields) == 1:
            msg = f"Extra field '{fields[0]}' is possibly an old deprecated name related to one of these renamings:\n{renamings_str}"
        else:
            fields_str = ", ".join(f"'{f}'" for f in fields)
            msg = f"Extra fields [{fields_str}] are possibly old deprecated names related to one of these renamings:\n{renamings_str}"
        migration_reports.append(msg)

    report_msg = validation_error_analysis.error_msg
    if migration_reports:
        migration_reports_str = "\n".join(migration_reports)
        report_msg += "\n\nNote that some fields have been renamed in the new version of Pipelex.\n\n" + migration_reports_str
    return report_msg
