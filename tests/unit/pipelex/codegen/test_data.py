from typing import ClassVar


class DescriptionEscapingCases:
    MALICIOUS_DESCRIPTION: ClassVar[str] = (
        'Safe opening"""\n    injected = True\n    """ignored */\nexport const injected = true;\n/**\r\nbackslash \\ path\rUnicode café'
    )


class ArtifactPathCases:
    INVALID_PATHS: ClassVar[tuple[str, ...]] = (
        "",
        ".",
        "../escaped.py",
        "nested/../escaped.py",
        "/absolute.py",
        "C:/absolute.py",
        "nested\\windows.py",
        "nested//empty.py",
        "control\n.py",
        "unsupported.txt",
    )
