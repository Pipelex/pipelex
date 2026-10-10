import pytest

from pipelex.tools.log.log_config import CallerInfoTemplate


class TestLogConfigUtilities:
    @pytest.mark.parametrize(
        ("template_key", "expected_template"),
        [
            (CallerInfoTemplate.FILE_LINE, "{file}:{line}"),
            (CallerInfoTemplate.FILE_LINE_FUNC, "{file}:{line} {func}"),
            (CallerInfoTemplate.FUNC, "{func}"),
            (CallerInfoTemplate.FILE_FUNC, "{file} {func}"),
            (CallerInfoTemplate.FUNC_LINE, "{func} {line}"),
            (CallerInfoTemplate.FUNC_MODULE, "{func} {module}"),
            (CallerInfoTemplate.FUNC_MODULE_LINE, "{func} {module} {line}"),
        ],
    )
    def test_caller_info_template_mapping(self, template_key: CallerInfoTemplate, expected_template: str) -> None:
        assert CallerInfoTemplate.for_template_key(template_key) == expected_template
