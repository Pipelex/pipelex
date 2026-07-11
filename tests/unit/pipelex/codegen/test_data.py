from typing import ClassVar


class DescriptionEscapingCases:
    MALICIOUS_DESCRIPTION: ClassVar[str] = (
        'Safe opening"""\n'
        "    injected = True\n"
        '    """ignored */\n'
        "export const injected = true;\n"
        "/**\r\n"
        "backslash \\ path\rUnicode café"
    )
