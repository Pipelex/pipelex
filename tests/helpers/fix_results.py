from typing import Any

from mthds.protocol.problem.registry import CoreCode

from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.pipeline.validation_errors import ValidationItemCode, validation_item_code


def fix_result(**fields: Any) -> FixBundleResult:
    """A fix result as a test states it, each remaining error coded by its type when the test gives no codes.

    The fix loop takes each remaining error's code from the verdict it read; a test that only renders the errors has no
    verdict, so its errors take the code their type gives them, ``method.schema_violation`` for an item with none.
    """
    if "remaining_error_codes" not in fields:
        remaining_errors = fields.get("remaining_errors", [])
        fields["remaining_error_codes"] = [
            ValidationItemCode(code=validation_item_code(item=item, residual_code=CoreCode.METHOD_SCHEMA_VIOLATION)) for item in remaining_errors
        ]
    return FixBundleResult(**fields)
