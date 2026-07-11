from enum import StrEnum


class ConsoleTarget(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"
    FILE = "file"
