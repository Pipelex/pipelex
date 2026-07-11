from typing import ClassVar


class DescriptionEscapingCases:
    MALICIOUS_DESCRIPTION: ClassVar[str] = (
        'Safe opening"""\n    injected = True\n    """ignored */\nexport const injected = true;\n/**\r\nbackslash \\ path\rUnicode café'
    )
