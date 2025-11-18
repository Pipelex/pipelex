from pipelex.types import StrEnum


class ConsoleTarget(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"
    FILE = "file"
