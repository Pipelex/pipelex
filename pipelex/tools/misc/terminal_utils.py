from pipelex.types import StrEnum

BOLD_FONT = "\033[1m"
RESET_FONT = "\033[0m"


class TerminalColor(StrEnum):
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BLUE = "\033[0;34m"
    WHITE = "\033[0;37m"
    CYAN = "\033[0;36m"
    MAGENTA = "\033[0;35m"
    YELLOW = "\033[0;33m"
