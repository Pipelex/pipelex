from pydantic import ValidationError

from pipelex import log
from pipelex.config import get_config
from pipelex.tools.typing.pydantic_utils import analyze_pydantic_validation_error


def report_validation_error(category: str, validation_error: ValidationError) -> str:
    validation_error_analysis = analyze_pydantic_validation_error(validation_error)

    migration_config = get_config().migration

    migration_reports: list[str] = []
    log.debug(validation_error_analysis.missing_fields, title="Missing fields")
    for missing_field in validation_error_analysis.missing_fields:
        text = missing_field.split(".")[-1]
        if renamings := migration_config.text_in_renaming_values(category=category, text=text):
            renamings_str = "\n".join(f"• '{key}' -> '{value}'" for key, value in renamings)
            migration_reports.append(f"Missing field '{missing_field}' is possibly a new name related to one of these renamings:\n{renamings_str}")

    log.debug(validation_error_analysis.extra_fields, title="Extra fields")
    for extra_field in validation_error_analysis.extra_fields:
        text = extra_field.split(".")[-1]
        if renamings := migration_config.text_in_renaming_keys(category=category, text=text):
            renamings_str = "\n".join(f"• '{key}' -> '{value}'" for key, value in renamings)
            migration_reports.append(
                f"Extra field '{extra_field}' is possibly an old deprecated name related to one of these renamings:\n{renamings_str}"
            )

    report_msg = validation_error_analysis.error_msg
    if migration_reports:
        migration_reports_str = "\n".join(migration_reports)
        report_msg += "\n\nThe following fields have been renamed in the new version of Pipelex:\n\n" + migration_reports_str
    return report_msg
